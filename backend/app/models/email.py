"""M5 邮件闭环 / 通用文件 数据模型。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class File(BaseModel):
    """文件（MinIO 对象元数据）。"""

    __tablename__ = "file"

    name: Mapped[str] = mapped_column(String(300), nullable=False)
    bucket: Mapped[str] = mapped_column(String(100), nullable=False)
    object_key: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    size: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    mime: Mapped[str | None] = mapped_column(String(150), nullable=True)
    module: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    biz_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    uploader_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    # 本地落盘路径（未启用 MinIO 时使用）
    local_path: Mapped[str | None] = mapped_column(String(500), nullable=True)


class EmailAccount(BaseModel):
    """邮件账号（SMTP 发送 / IMAP 接收）。"""

    __tablename__ = "email_account"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("user.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    smtp_host: Mapped[str | None] = mapped_column(String(200), nullable=True)
    smtp_port: Mapped[int] = mapped_column(Integer, default=465, nullable=False)
    smtp_user: Mapped[str | None] = mapped_column(String(200), nullable=True)
    smtp_password: Mapped[str | None] = mapped_column(String(500), nullable=True)
    smtp_ssl: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    imap_host: Mapped[str | None] = mapped_column(String(200), nullable=True)
    imap_port: Mapped[int] = mapped_column(Integer, default=993, nullable=False)
    imap_user: Mapped[str | None] = mapped_column(String(200), nullable=True)
    imap_password: Mapped[str | None] = mapped_column(String(500), nullable=True)
    imap_ssl: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    imap_folder: Mapped[str] = mapped_column(String(100), default="INBOX", nullable=False)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", nullable=False)


class EmailThread(BaseModel):
    """邮件线程（同一话题聚合）。"""

    __tablename__ = "email_thread"

    thread_key: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("company.id"), nullable=True, index=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    match_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    message_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EmailMessage(BaseModel):
    """邮件消息。"""

    __tablename__ = "email_message"

    thread_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("email_thread.id"), nullable=True, index=True
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("email_account.id"), nullable=True, index=True
    )
    direction: Mapped[str] = mapped_column(String(10), default="RECEIVED", nullable=False, index=True)
    message_id: Mapped[str | None] = mapped_column(String(300), nullable=True, index=True)
    in_reply_to: Mapped[str | None] = mapped_column(String(300), nullable=True)
    from_addr: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    from_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    to_addrs: Mapped[str | None] = mapped_column(Text, nullable=True)
    cc_addrs: Mapped[str | None] = mapped_column(Text, nullable=True)
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    has_attachment: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    matched_by: Mapped[str | None] = mapped_column(String(20), nullable=True)
    send_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_headers: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class EmailAttachment(BaseModel):
    """邮件附件。"""

    __tablename__ = "email_attachment"

    message_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("email_message.id"), nullable=False, index=True
    )
    file_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    filename: Mapped[str] = mapped_column(String(300), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    mime: Mapped[str | None] = mapped_column(String(150), nullable=True)
