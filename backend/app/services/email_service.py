"""M5 邮件服务：SMTP 发送 / IMAP 接收 / 自动关联。

未配置真实邮箱服务器时（smtp_host 为空或 `demo`）走模拟模式，
保证业务流程可完整演示；配置真实服务器后自动切换为真实收发。
"""

from __future__ import annotations

import asyncio
import contextlib
import email
import imaplib
import smtplib
import uuid
from datetime import UTC, datetime
from email.header import decode_header, make_header
from email.message import EmailMessage as PyEmailMessage
from email.utils import parseaddr, parsedate_to_datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ApiError, NotFoundError
from app.models.business import Company, Contact
from app.models.email import EmailAccount, EmailAttachment, EmailMessage, EmailThread
from app.services import storage

SIMULATED_HOSTS = {"", "demo", "simulate", "mock", None}


def is_simulated(account: EmailAccount) -> bool:
    return (account.smtp_host or "").strip().lower() in SIMULATED_HOSTS and (
        account.imap_host or ""
    ).strip().lower() in SIMULATED_HOSTS


def _decode(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:  # noqa: BLE001
        return value


def _body_of(msg: email.message.Message) -> tuple[str, str | None]:
    text_parts: list[str] = []
    html_parts: list[str] = []
    for part in msg.walk():
        ctype = part.get_content_type()
        if part.get_content_maintype() == "multipart":
            continue
        if ctype not in {"text/plain", "text/html"}:
            continue
        try:
            payload = part.get_payload(decode=True)
            if not isinstance(payload, bytes):
                continue
            charset = part.get_content_charset() or "utf-8"
            content = payload.decode(charset, errors="replace")
        except Exception:  # noqa: BLE001
            continue
        if ctype == "text/plain":
            text_parts.append(content)
        else:
            html_parts.append(content)
    return "\n".join(text_parts), ("\n".join(html_parts) or None)


def _attachments_of(msg: email.message.Message) -> list[tuple[str, bytes, str]]:
    result: list[tuple[str, bytes, str]] = []
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        disposition = (part.get("Content-Disposition") or "").lower()
        if "attachment" not in disposition and "inline" not in disposition:
            continue
        filename = _decode(part.get_filename())
        if not filename:
            continue
        raw = part.get_payload(decode=True)
        data = raw if isinstance(raw, bytes) else b""
        result.append((filename, data, part.get_content_type()))
    return result


# ------------------------------------------------------------------ 关联匹配


async def match_company(db: AsyncSession, *, from_addr: str) -> tuple[uuid.UUID | None, uuid.UUID | None, str | None]:
    """返回 (company_id, contact_id, match_type)。"""
    addr = (from_addr or "").strip().lower()
    if not addr or "@" not in addr:
        return None, None, None

    contact = (
        await db.execute(select(Contact).where(Contact.email == addr, Contact.deleted_at.is_(None)))
    ).scalar_one_or_none()
    if contact is not None:
        return contact.company_id, contact.id, "CONTACT_EMAIL"

    domain = addr.split("@", 1)[1]
    company = (
        await db.execute(
            select(Company)
            .where(
                Company.deleted_at.is_(None),
                or_(Company.website.ilike(f"%{domain}%"), Company.name_en.ilike(f"%{domain}%")),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if company is not None:
        return company.id, None, "DOMAIN"

    contact = (
        await db.execute(
            select(Contact).where(Contact.email.ilike(f"%@{domain}"), Contact.deleted_at.is_(None)).limit(1)
        )
    ).scalar_one_or_none()
    if contact is not None:
        return contact.company_id, contact.id, "DOMAIN_CONTACT"

    return None, None, None


async def _thread_for(
    db: AsyncSession,
    *,
    subject: str | None,
    in_reply_to: str | None,
    company_id: uuid.UUID | None,
) -> EmailThread:
    if in_reply_to:
        found = (
            await db.execute(
                select(EmailThread)
                .join(EmailMessage, EmailMessage.thread_id == EmailThread.id)
                .where(EmailMessage.message_id == in_reply_to, EmailThread.deleted_at.is_(None))
                .limit(1)
            )
        ).scalar_one_or_none()
        if found is not None:
            return found

    key = (subject or "").strip().lower() or "no-subject"
    thread = (
        await db.execute(select(EmailThread).where(EmailThread.thread_key == key, EmailThread.deleted_at.is_(None)))
    ).scalar_one_or_none()
    if thread is None:
        thread = EmailThread(
            thread_key=key,
            subject=subject,
            company_id=company_id,
            match_type="AUTO" if company_id else None,
        )
        db.add(thread)
        await db.flush()
    return thread


# ------------------------------------------------------------------ 发送


async def send(
    db: AsyncSession,
    *,
    account: EmailAccount,
    to_addrs: list[str],
    cc_addrs: list[str],
    subject: str,
    body: str,
    body_html: str | None = None,
    attachments: list[tuple[str, bytes, str]] | None = None,
    company_id: uuid.UUID | None = None,
    contact_id: uuid.UUID | None = None,
    opportunity_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    sender_name: str | None = None,
) -> EmailMessage:
    attachments = attachments or []
    message_id = f"<{uuid.uuid4().hex}@crm.local>"
    now = datetime.now(UTC)

    thread = await _thread_for(db, subject=subject, in_reply_to=None, company_id=company_id)

    msg = EmailMessage(
        thread_id=thread.id,
        account_id=account.id,
        direction="SENT",
        message_id=message_id,
        from_addr=account.email,
        from_name=sender_name or account.display_name or account.name,
        to_addrs=", ".join(to_addrs),
        cc_addrs=", ".join(cc_addrs) or None,
        subject=subject,
        body_text=body,
        body_html=body_html,
        sent_at=now,
        is_read=True,
        has_attachment=bool(attachments),
        matched_by="MANUAL",
        send_status="PENDING",
    )
    db.add(msg)
    await db.flush()

    for filename, data, mime in attachments:
        record = await storage.save_bytes(
            db,
            filename=filename,
            data=data,
            mime=mime,
            module="email",
            biz_id=msg.id,
            uploader_id=user_id,
        )
        db.add(EmailAttachment(message_id=msg.id, file_id=record.id, filename=filename, size=len(data), mime=mime))

    if is_simulated(account):
        msg.send_status = "SIMULATED"
        msg.error_message = None
    else:
        try:
            await asyncio.to_thread(_smtp_send, account, to_addrs, cc_addrs, subject, body, body_html, attachments)
            msg.send_status = "SENT"
        except Exception as exc:  # noqa: BLE001
            msg.send_status = "FAILED"
            msg.error_message = str(exc)
            await db.flush()
            raise ApiError(message=f"邮件发送失败：{exc}", http_status=502) from exc

    thread.message_count += 1
    thread.last_message_at = now
    if company_id and thread.company_id is None:
        thread.company_id = company_id
    if contact_id and thread.contact_id is None:
        thread.contact_id = contact_id
    if opportunity_id and thread.opportunity_id is None:
        thread.opportunity_id = opportunity_id
    await db.flush()
    return msg


def _smtp_send(
    account: EmailAccount,
    to_addrs: list[str],
    cc_addrs: list[str],
    subject: str,
    body: str,
    body_html: str | None,
    attachments: list[tuple[str, bytes, str]],
) -> None:
    msg = PyEmailMessage()
    msg["From"] = f"{account.display_name or account.name} <{account.email}>"
    msg["To"] = ", ".join(to_addrs)
    if cc_addrs:
        msg["Cc"] = ", ".join(cc_addrs)
    msg["Subject"] = subject
    msg.set_content(body or "")
    if body_html:
        msg.add_alternative(body_html, subtype="html")
    for filename, data, mime in attachments:
        maintype, _, subtype = (mime or "application/octet-stream").partition("/")
        msg.add_attachment(data, maintype=maintype, subtype=subtype or "octet-stream", filename=filename)

    targets = to_addrs + cc_addrs
    host = account.smtp_host or ""
    if account.smtp_ssl:
        with smtplib.SMTP_SSL(host, account.smtp_port, timeout=30) as server:
            if account.smtp_user:
                server.login(account.smtp_user, account.smtp_password or "")
            server.send_message(msg, to_addrs=targets)
    else:
        with smtplib.SMTP(host, account.smtp_port, timeout=30) as server:
            server.starttls()
            if account.smtp_user:
                server.login(account.smtp_user, account.smtp_password or "")
            server.send_message(msg, to_addrs=targets)


# ------------------------------------------------------------------ 接收


async def sync(
    db: AsyncSession,
    *,
    account: EmailAccount,
    limit: int = 20,
) -> dict[str, Any]:
    if (account.imap_host or "").strip().lower() in {"", "demo", "simulate", "mock"}:
        return {
            "fetched": 0,
            "created": 0,
            "matched": 0,
            "unmatched": 0,
            "detail": "未配置 IMAP 服务器（imap_host 为空或 demo），跳过真实拉取；"
            "可使用「注入演示邮件」接口验证关联流程。",
        }

    try:
        raw_list = await asyncio.to_thread(_imap_fetch, account, limit)
    except Exception as exc:  # noqa: BLE001
        raise ApiError(message=f"IMAP 拉取失败：{exc}", http_status=502) from exc

    created = matched = 0
    for raw in raw_list:
        msg = email.message_from_bytes(raw)
        message_id = _decode(msg.get("Message-ID")) or None
        if message_id:
            dup = (
                await db.execute(select(EmailMessage.id).where(EmailMessage.message_id == message_id))
            ).scalar_one_or_none()
            if dup:
                continue

        from_name, from_addr = parseaddr(_decode(msg.get("From")))
        raw_date = msg.get("Date")
        sent_at = None
        if raw_date:
            try:
                sent_at = parsedate_to_datetime(str(raw_date))
            except Exception:  # noqa: BLE001
                sent_at = None
        text, html = _body_of(msg)
        atts = _attachments_of(msg)

        company_id, contact_id, match_type = await match_company(db, from_addr=from_addr)
        subject = _decode(msg.get("Subject"))
        thread = await _thread_for(
            db,
            subject=subject,
            in_reply_to=_decode(msg.get("In-Reply-To")) or None,
            company_id=company_id,
        )

        record = EmailMessage(
            thread_id=thread.id,
            account_id=account.id,
            direction="RECEIVED",
            message_id=message_id,
            in_reply_to=_decode(msg.get("In-Reply-To")) or None,
            from_addr=from_addr,
            from_name=from_name or None,
            to_addrs=_decode(msg.get("To")),
            cc_addrs=_decode(msg.get("Cc")) or None,
            subject=subject,
            body_text=text,
            body_html=html,
            sent_at=sent_at,
            received_at=datetime.now(UTC),
            has_attachment=bool(atts),
            matched_by=match_type,
        )
        db.add(record)
        await db.flush()
        created += 1
        if company_id:
            matched += 1

        for filename, data, mime in atts:
            file_record = await storage.save_bytes(
                db, filename=filename, data=data, mime=mime, module="email", biz_id=record.id
            )
            db.add(
                EmailAttachment(
                    message_id=record.id, file_id=file_record.id, filename=filename, size=len(data), mime=mime
                )
            )

        thread.message_count += 1
        thread.last_message_at = record.received_at

    account.last_sync_at = datetime.now(UTC)
    await db.flush()
    return {
        "fetched": len(raw_list),
        "created": created,
        "matched": matched,
        "unmatched": created - matched,
        "detail": "IMAP 同步完成",
    }


def _imap_fetch(account: EmailAccount, limit: int) -> list[bytes]:
    host = account.imap_host or ""
    client: imaplib.IMAP4 = (
        imaplib.IMAP4_SSL(host, account.imap_port) if account.imap_ssl else imaplib.IMAP4(host, account.imap_port)
    )
    try:
        client.login(account.imap_user or account.email, account.imap_password or "")
        client.select(account.imap_folder or "INBOX")
        status, data = client.search(None, "ALL")
        if status != "OK":
            return []
        ids = data[0].split()[-limit:]
        result: list[bytes] = []
        for msg_id in ids:
            status, payload = client.fetch(msg_id, "(RFC822)")
            if status != "OK" or not payload:
                continue
            part = payload[0]
            if isinstance(part, tuple):
                result.append(part[1])
        return result
    finally:
        with contextlib.suppress(Exception):
            client.logout()


async def get_account(db: AsyncSession, account_id: uuid.UUID | None, user_id: uuid.UUID | None) -> EmailAccount:
    stmt = select(EmailAccount).where(EmailAccount.deleted_at.is_(None))
    if account_id:
        stmt = stmt.where(EmailAccount.id == account_id)
    elif user_id:
        stmt = stmt.where(or_(EmailAccount.user_id == user_id, EmailAccount.user_id.is_(None))).order_by(
            EmailAccount.is_default.desc()
        )
    else:
        stmt = stmt.order_by(EmailAccount.is_default.desc())
    account = (await db.execute(stmt)).scalars().first()
    if account is None:
        if account_id:
            raise NotFoundError("邮件账号不存在")
        raise ApiError(message="尚未配置邮件账号，请先在「邮件-账号配置」中新增", http_status=400)
    return account


async def inject_inbound(
    db: AsyncSession,
    *,
    account: EmailAccount,
    from_addr: str,
    from_name: str | None,
    subject: str,
    body: str,
    in_reply_to: str | None = None,
) -> dict[str, Any]:
    """演示用：注入一封（模拟）收件，用于验证关联流程。"""
    company_id, contact_id, match_type = await match_company(db, from_addr=from_addr)
    thread = await _thread_for(db, subject=subject, in_reply_to=in_reply_to, company_id=company_id)
    now = datetime.now(UTC)
    record = EmailMessage(
        thread_id=thread.id,
        account_id=account.id,
        direction="RECEIVED",
        message_id=f"<{uuid.uuid4().hex}@crm.local>",
        in_reply_to=in_reply_to,
        from_addr=from_addr,
        from_name=from_name,
        to_addrs=account.email,
        subject=subject,
        body_text=body,
        received_at=now,
        matched_by=match_type,
    )
    db.add(record)
    thread.message_count += 1
    thread.last_message_at = now
    await db.flush()
    return {
        "message_id": record.id,
        "company_id": company_id,
        "contact_id": contact_id,
        "match_type": match_type,
        "auto_matched": company_id is not None,
    }
