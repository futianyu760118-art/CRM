"""M5 邮件接口：账号配置 / 收件箱 / 发送 / 同步 / 人工关联。"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select

from app.core import response as resp
from app.core.deps import CurrentUser, DbSession, require_permission
from app.core.exceptions import ConflictError
from app.models.business import Company
from app.models.email import EmailAccount, EmailAttachment, EmailMessage, EmailThread
from app.models.user import User
from app.schemas.email import (
    EmailAccountCreate,
    EmailAccountOut,
    EmailAccountUpdate,
    EmailAttachmentOut,
    EmailLinkIn,
    EmailMessageOut,
    EmailSendIn,
    EmailSyncIn,
    EmailSyncOut,
)
from app.services import email_service
from app.services.query import apply_sort, get_or_404, paginate, soft_delete

router = APIRouter(tags=["M5-邮件"])

MASK = "********"


def _mask_account(account: EmailAccount) -> dict[str, Any]:
    data = EmailAccountOut.model_validate(account).model_dump(mode="json")
    data["has_smtp_password"] = bool(account.smtp_password)
    data["has_imap_password"] = bool(account.imap_password)
    data["simulated"] = email_service.is_simulated(account)
    return data


# ------------------------------------------------------------------ 账号配置
account_router = APIRouter(prefix="/email-accounts", tags=["M5-邮件"])


@account_router.get("", summary="邮件账号列表")
async def list_accounts(
    db: DbSession,
    current: CurrentUser,
    _: User = Depends(require_permission("email:view")),
) -> dict[str, Any]:
    stmt = select(EmailAccount).where(EmailAccount.deleted_at.is_(None))
    if not current.is_superuser:
        stmt = stmt.where(or_(EmailAccount.user_id == current.id, EmailAccount.user_id.is_(None)))
    rows = (await db.execute(stmt.order_by(EmailAccount.is_default.desc()))).scalars().all()
    return resp.ok([_mask_account(r) for r in rows])


@account_router.post("", summary="新增邮件账号", status_code=201)
async def create_account(
    payload: EmailAccountCreate,
    db: DbSession,
    current: CurrentUser,
    _: User = Depends(require_permission("email:send")),
) -> dict[str, Any]:
    data = payload.model_dump(exclude_unset=True)
    account = EmailAccount(**data, user_id=current.id)
    db.add(account)
    if payload.is_default:
        others = (await db.execute(select(EmailAccount).where(EmailAccount.deleted_at.is_(None)))).scalars().all()
        for other in others:
            other.is_default = False
    await db.commit()
    await db.refresh(account)
    return resp.ok(_mask_account(account))


@account_router.put("/{account_id}", summary="更新邮件账号")
async def update_account(
    account_id: uuid.UUID,
    payload: EmailAccountUpdate,
    db: DbSession,
    _: User = Depends(require_permission("email:send")),
) -> dict[str, Any]:
    account = await get_or_404(db, EmailAccount, account_id, "邮件账号")
    data = payload.model_dump(exclude_unset=True)
    if data.get("smtp_password") in ("", MASK):
        data.pop("smtp_password", None)
    if data.get("imap_password") in ("", MASK):
        data.pop("imap_password", None)
    for key, value in data.items():
        setattr(account, key, value)
    await db.commit()
    await db.refresh(account)
    return resp.ok(_mask_account(account))


@account_router.delete("/{account_id}", summary="删除邮件账号")
async def delete_account(
    account_id: uuid.UUID,
    db: DbSession,
    _: User = Depends(require_permission("email:send")),
) -> dict[str, Any]:
    account = await get_or_404(db, EmailAccount, account_id, "邮件账号")
    soft_delete(account)
    await db.commit()
    return resp.ok({"deleted": True})


# ------------------------------------------------------------------ 邮件
mail_router = APIRouter(prefix="/emails", tags=["M5-邮件"])


async def _serialize_message(db: DbSession, message: EmailMessage, *, with_thread: bool = True) -> dict[str, Any]:
    data = EmailMessageOut.model_validate(message).model_dump(mode="json")
    thread = None
    if message.thread_id:
        thread = (await db.execute(select(EmailThread).where(EmailThread.id == message.thread_id))).scalar_one_or_none()
    if thread is not None:
        data["company_id"] = str(thread.company_id) if thread.company_id else None
        data["opportunity_id"] = str(thread.opportunity_id) if thread.opportunity_id else None
        if thread.company_id:
            name = (await db.execute(select(Company.name).where(Company.id == thread.company_id))).scalar_one_or_none()
            data["company_name"] = name
        if with_thread:
            data["thread"] = {
                "id": str(thread.id),
                "subject": thread.subject,
                "message_count": thread.message_count,
                "last_message_at": thread.last_message_at.isoformat() if thread.last_message_at else None,
            }
    attachments = (
        (
            await db.execute(
                select(EmailAttachment).where(
                    EmailAttachment.message_id == message.id, EmailAttachment.deleted_at.is_(None)
                )
            )
        )
        .scalars()
        .all()
    )
    data["attachments"] = [EmailAttachmentOut.model_validate(a).model_dump(mode="json") for a in attachments]
    return data


@mail_router.get("", summary="邮件列表")
async def list_messages(
    db: DbSession,
    _: User = Depends(require_permission("email:view")),
    keyword: str | None = None,
    direction: str | None = None,
    is_read: bool | None = None,
    matched: bool | None = Query(None, description="是否已关联客户"),
    company_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    sort: str = "created_at",
    order: str = Query("desc", pattern="^(asc|desc)$"),
) -> dict[str, Any]:
    stmt = select(EmailMessage).where(EmailMessage.deleted_at.is_(None))
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(
            or_(
                EmailMessage.subject.ilike(like),
                EmailMessage.from_addr.ilike(like),
                EmailMessage.body_text.ilike(like),
            )
        )
    if direction:
        stmt = stmt.where(EmailMessage.direction == direction)
    if is_read is not None:
        stmt = stmt.where(EmailMessage.is_read.is_(is_read))
    if company_id:
        thread_ids = select(EmailThread.id).where(EmailThread.company_id == company_id)
        stmt = stmt.where(EmailMessage.thread_id.in_(thread_ids))
    if matched is not None:
        matched_threads = select(EmailThread.id).where(
            EmailThread.company_id.isnot(None) if matched else EmailThread.company_id.is_(None)
        )
        if matched:
            stmt = stmt.where(EmailMessage.thread_id.in_(matched_threads))
        else:
            stmt = stmt.where(
                or_(
                    EmailMessage.thread_id.is_(None),
                    EmailMessage.thread_id.in_(matched_threads),
                )
            )

    stmt = apply_sort(stmt, EmailMessage, sort, order)
    rows, total = await paginate(db, stmt, page, page_size)
    items = [await _serialize_message(db, r, with_thread=False) for r in rows]
    return resp.page(items, total, page, page_size)


@mail_router.post("/send", summary="发送邮件")
async def send_message(
    payload: EmailSendIn,
    db: DbSession,
    current: CurrentUser,
    _: User = Depends(require_permission("email:send")),
) -> dict[str, Any]:
    account = await email_service.get_account(db, payload.account_id, current.id)

    attachments: list[tuple[str, bytes, str]] = []
    if payload.quotation_id and payload.attach_pdf:
        from app.models.email import File
        from app.models.pricing import Quotation
        from app.services import storage

        quotation = await get_or_404(db, Quotation, payload.quotation_id, "报价单")
        if quotation.pdf_file_id:
            record = (await db.execute(select(File).where(File.id == quotation.pdf_file_id))).scalar_one_or_none()
            if record is not None:
                attachments.append(
                    (
                        f"{quotation.quotation_no}.pdf",
                        storage.read_bytes(record),
                        "application/pdf",
                    )
                )

    message = await email_service.send(
        db,
        account=account,
        to_addrs=payload.to_addrs,
        cc_addrs=payload.cc_addrs,
        subject=payload.subject,
        body=payload.body,
        body_html=payload.body_html,
        attachments=attachments,
        company_id=payload.company_id,
        contact_id=payload.contact_id,
        opportunity_id=payload.opportunity_id,
        user_id=current.id,
        sender_name=current.name,
    )
    await db.commit()
    return resp.ok(
        {
            "message_id": str(message.id),
            "send_status": message.send_status,
            "simulated": email_service.is_simulated(account),
            "to": payload.to_addrs,
        }
    )


@mail_router.post("/sync", summary="手动同步 IMAP")
async def sync_messages(
    payload: EmailSyncIn,
    db: DbSession,
    current: CurrentUser,
    _: User = Depends(require_permission("email:sync")),
) -> dict[str, Any]:
    account = await email_service.get_account(db, payload.account_id, current.id)
    result = await email_service.sync(db, account=account, limit=payload.limit)
    await db.commit()
    return resp.ok(EmailSyncOut(**result).model_dump(mode="json"))


@mail_router.post("/inject-inbound", summary="注入演示收件（验证关联流程）")
async def inject_inbound(
    db: DbSession,
    current: CurrentUser,
    from_addr: str = Query(..., description="发件人邮箱，可用已知联系人邮箱验证自动关联"),
    subject: str = Query("Re: Quotation inquiry"),
    body: str = Query("Thanks for your quotation, we are reviewing internally."),
    account_id: uuid.UUID | None = Query(None),
    _: User = Depends(require_permission("email:sync")),
) -> dict[str, Any]:
    account = await email_service.get_account(db, account_id, current.id)
    result = await email_service.inject_inbound(
        db,
        account=account,
        from_addr=from_addr,
        from_name=None,
        subject=subject,
        body=body,
    )
    await db.commit()
    return resp.ok({**result, "message_id": str(result["message_id"])})


@mail_router.get("/{message_id}", summary="邮件详情")
async def get_message(
    message_id: uuid.UUID,
    db: DbSession,
    _: User = Depends(require_permission("email:view")),
) -> dict[str, Any]:
    message = await get_or_404(db, EmailMessage, message_id, "邮件")
    return resp.ok(await _serialize_message(db, message))


@mail_router.post("/{message_id}/read", summary="标记已读")
async def mark_read(
    message_id: uuid.UUID,
    db: DbSession,
    _: User = Depends(require_permission("email:view")),
) -> dict[str, Any]:
    message = await get_or_404(db, EmailMessage, message_id, "邮件")
    message.is_read = True
    await db.commit()
    return resp.ok({"is_read": True})


@mail_router.post("/{message_id}/link", summary="人工确认/修改邮件关联")
async def link_message(
    message_id: uuid.UUID,
    payload: EmailLinkIn,
    db: DbSession,
    _: User = Depends(require_permission("email:view")),
) -> dict[str, Any]:
    message = await get_or_404(db, EmailMessage, message_id, "邮件")
    if not message.thread_id:
        raise ConflictError("该邮件没有线程，无法关联")
    thread = (await db.execute(select(EmailThread).where(EmailThread.id == message.thread_id))).scalar_one_or_none()
    if thread is None:
        raise ConflictError("邮件线程不存在")

    if payload.company_id is not None:
        company = (await db.execute(select(Company).where(Company.id == payload.company_id))).scalar_one_or_none()
        if company is None:
            raise ConflictError("客户不存在")
        thread.company_id = company.id
        thread.match_type = "MANUAL"
    if payload.contact_id is not None:
        thread.contact_id = payload.contact_id
    if payload.opportunity_id is not None:
        thread.opportunity_id = payload.opportunity_id
    await db.commit()
    return resp.ok(await _serialize_message(db, message))
