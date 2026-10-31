"""销售中心 6 模块新增数据模型（PAND-249：订单 / 样品 / 报价库 / 问题反馈 / 同步冲突 / 询价状态日志）。

契约依据：PAND-248 契约冻结版 §3（数据模型）与 §4.2（取值域）。类型约定沿用既有：
``MONEY=Numeric(18,4)``、主键 UUID、软删 ``deleted_at``、归属 ``owner_id/department_id``（``BusinessModel``）。
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel, BusinessModel

MONEY = Numeric(18, 4)
QTY = Numeric(18, 2)


class SalesOrder(BusinessModel):
    """订单行（业务键 = order_no + line_no；规避 SQL 保留字 ``order``，表名 ``sales_order``）。"""

    __tablename__ = "sales_order"
    __table_args__ = (UniqueConstraint("order_no", "line_no", name="uq_sales_order_key"),)

    order_no: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    line_no: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("company.id"), nullable=True, index=True
    )
    customer_name: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    customer_code: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    product_code: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    product_name: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    project_no: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    quantity: Mapped[float] = mapped_column(QTY, default=0, nullable=False)
    completed_qty: Mapped[float] = mapped_column(QTY, default=0, nullable=False)
    order_amount: Mapped[float] = mapped_column(MONEY, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="open", nullable=False, index=True)
    risk_level: Mapped[str] = mapped_column(String(20), default="blue", nullable=False, index=True)
    promised_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    plan_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    online_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    user_status_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    user_status_modified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user_status_modified_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    sync_status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False, index=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Sample(BusinessModel):
    """样品（业务键 = sample_no）。"""

    __tablename__ = "sample"

    sample_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    external_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("company.id"), nullable=True, index=True
    )
    customer_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    inquiry_no: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    inquiry_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("inquiry.id"), nullable=True)
    product_name: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    product_code: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    quantity: Mapped[float] = mapped_column(QTY, default=0, nullable=False)
    sample_type: Mapped[str] = mapped_column(String(50), default="常规", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    send_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    confirm_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    sync_status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False, index=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class QuoteLibrary(BaseModel):
    """报价库（独立于 Quotation；业务键 = external_model + certificate_level 复合）。"""

    __tablename__ = "quote_library"
    __table_args__ = (UniqueConstraint("external_model", "certificate_level", name="uq_quote_library_key"),)

    external_model: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    certificate_level: Mapped[str] = mapped_column(String(50), default="", nullable=False, index=True)
    external_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    internal_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    product_name: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    power: Mapped[str | None] = mapped_column(String(100), nullable=True)
    configuration: Mapped[str | None] = mapped_column(Text, nullable=True)
    specs: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_rmb: Mapped[float | None] = mapped_column(MONEY, nullable=True)
    price_usd: Mapped[float | None] = mapped_column(MONEY, nullable=True)
    unit_price: Mapped[float | None] = mapped_column(MONEY, nullable=True)
    min_price: Mapped[float | None] = mapped_column(MONEY, nullable=True)
    validity_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_inquiry_no: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    source_inquiry_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    source_pricing_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    creator: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sync_status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False, index=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Feedback(BusinessModel):
    """问题反馈（业务键 = feedback_no，EBMS 未就绪前用三元组指纹）。"""

    __tablename__ = "feedback"

    feedback_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    external_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    type: Mapped[str] = mapped_column(String(20), default="bug", nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(20), default="medium", nullable=False, index=True)
    module: Mapped[str | None] = mapped_column(String(100), nullable=True)
    submitter: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    submitter_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    assignee: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    screenshots: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="page", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False, index=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False, index=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    followups: Mapped[list[FeedbackFollowup]] = relationship(
        back_populates="feedback", lazy="selectin", cascade="all, delete-orphan"
    )


class FeedbackFollowup(BaseModel):
    """反馈跟进记录（删除反馈级联删跟进，AC-M6.6）。"""

    __tablename__ = "feedback_followup"

    feedback_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("feedback.id"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    status_from: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status_to: Mapped[str | None] = mapped_column(String(20), nullable=True)
    assignee: Mapped[str | None] = mapped_column(String(100), nullable=True)
    operator: Mapped[str | None] = mapped_column(String(100), nullable=True)
    operator_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)

    feedback: Mapped[Feedback] = relationship(back_populates="followups", lazy="noload")


class SyncConflict(BaseModel):
    """同步冲突留痕（AC-S7/S8）。"""

    __tablename__ = "sync_conflict"

    object_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    object_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    field: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_system: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    incoming_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    local_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    resolution: Mapped[str] = mapped_column(String(20), default="SKIPPED", nullable=False, index=True)
    event_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class InquiryStatusLog(BaseModel):
    """询价状态变更历史（AC-M2.7 / F2.10）。"""

    __tablename__ = "inquiry_status_log"

    inquiry_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("inquiry.id"), nullable=False, index=True
    )
    from_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str] = mapped_column(String(30), nullable=False)
    operator_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
