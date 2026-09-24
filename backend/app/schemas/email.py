"""M5 邮件 Schema。"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class EmailAccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=200)
    display_name: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 465
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_ssl: bool = True
    imap_host: str | None = None
    imap_port: int = 993
    imap_user: str | None = None
    imap_password: str | None = None
    imap_ssl: bool = True
    imap_folder: str = "INBOX"
    is_default: bool = False


class EmailAccountUpdate(BaseModel):
    name: str | None = None
    display_name: str | None = None
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_ssl: bool | None = None
    imap_host: str | None = None
    imap_port: int | None = None
    imap_user: str | None = None
    imap_password: str | None = None
    imap_ssl: bool | None = None
    imap_folder: str | None = None
    is_default: bool | None = None
    status: str | None = None


class EmailAccountOut(ORMModel):
    id: uuid.UUID
    name: str
    email: str
    display_name: str | None = None
    smtp_host: str | None = None
    smtp_port: int
    smtp_user: str | None = None
    smtp_ssl: bool
    imap_host: str | None = None
    imap_port: int
    imap_user: str | None = None
    imap_ssl: bool
    imap_folder: str
    is_default: bool
    status: str
    last_sync_at: datetime | None = None
    created_at: datetime


class EmailAttachmentOut(ORMModel):
    id: uuid.UUID
    filename: str
    size: int
    mime: str | None = None
    file_id: uuid.UUID | None = None


class EmailMessageOut(ORMModel):
    id: uuid.UUID
    thread_id: uuid.UUID | None = None
    account_id: uuid.UUID | None = None
    direction: str
    from_addr: str | None = None
    from_name: str | None = None
    to_addrs: str | None = None
    cc_addrs: str | None = None
    subject: str | None = None
    body_text: str | None = None
    sent_at: datetime | None = None
    received_at: datetime | None = None
    is_read: bool
    has_attachment: bool
    matched_by: str | None = None
    send_status: str | None = None
    error_message: str | None = None
    created_at: datetime
    company_id: uuid.UUID | None = None
    company_name: str | None = None
    opportunity_id: uuid.UUID | None = None
    attachments: list[EmailAttachmentOut] = Field(default_factory=list)


class EmailSendIn(BaseModel):
    account_id: uuid.UUID | None = None
    to_addrs: list[str] = Field(min_length=1)
    cc_addrs: list[str] = Field(default_factory=list)
    subject: str = Field(min_length=1)
    body: str = ""
    body_html: str | None = None
    company_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    opportunity_id: uuid.UUID | None = None
    quotation_id: uuid.UUID | None = None
    attach_pdf: bool = False


class EmailSyncIn(BaseModel):
    account_id: uuid.UUID | None = None
    limit: int = 20


class EmailSyncOut(BaseModel):
    fetched: int
    created: int
    matched: int
    unmatched: int
    detail: str


class EmailLinkIn(BaseModel):
    company_id: uuid.UUID | None = None
    opportunity_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
