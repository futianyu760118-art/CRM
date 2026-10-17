"""M4 核价 / 报价 / 审批 数据模型。"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel, BusinessModel

MONEY = Numeric(18, 4)


class PricingRecord(BusinessModel):
    """核价记录（一询价多版本，版本不允许覆盖）。"""

    __tablename__ = "pricing_record"

    inquiry_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("inquiry.id"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", nullable=False, index=True)
    currency: Mapped[str] = mapped_column(String(10), default="USD", nullable=False)

    material_cost: Mapped[float | None] = mapped_column(MONEY, nullable=True)
    labor_cost: Mapped[float | None] = mapped_column(MONEY, nullable=True)
    packaging_cost: Mapped[float | None] = mapped_column(MONEY, nullable=True)
    freight_cost: Mapped[float | None] = mapped_column(MONEY, nullable=True)
    tooling_cost: Mapped[float | None] = mapped_column(MONEY, nullable=True)
    customization_cost: Mapped[float | None] = mapped_column(MONEY, nullable=True)
    moq_cost: Mapped[float | None] = mapped_column(MONEY, nullable=True)
    other_cost: Mapped[float | None] = mapped_column(MONEY, nullable=True)
    loss_cost: Mapped[float | None] = mapped_column(MONEY, default=0, nullable=True)
    total_cost: Mapped[float | None] = mapped_column(MONEY, nullable=True)
    base_cost: Mapped[float | None] = mapped_column(MONEY, nullable=True)

    target_margin: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    discount_rate: Mapped[float] = mapped_column(Numeric(10, 4), default=1, nullable=False)
    floor_price: Mapped[float | None] = mapped_column(MONEY, nullable=True)
    suggested_price: Mapped[float | None] = mapped_column(MONEY, nullable=True)
    final_price: Mapped[float | None] = mapped_column(MONEY, nullable=True)

    created_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)


class PricingRule(BaseModel):
    """核价规则（JSON 条件 + 动作），M4 的 P1 能力。"""

    __tablename__ = "pricing_rule"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    conditions: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    actions: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class Quotation(BusinessModel):
    """报价单。"""

    __tablename__ = "quotation"

    quotation_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("company.id"), nullable=False, index=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    inquiry_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("inquiry.id"), nullable=True, index=True
    )
    pricing_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("pricing_record.id"), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    currency: Mapped[str] = mapped_column(String(10), default="RMB", nullable=False)
    exchange_rate: Mapped[float] = mapped_column(Numeric(18, 6), default=7.25, nullable=False)
    discount_rate: Mapped[float] = mapped_column(Numeric(10, 4), default=1, nullable=False)
    incoterm: Mapped[str | None] = mapped_column(String(20), nullable=True)
    payment_terms: Mapped[str | None] = mapped_column(String(200), nullable=True)
    warranty: Mapped[str | None] = mapped_column(String(200), nullable=True)
    valid_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)

    # ---- 对外价格表版式（对齐《星耀内置混动》报价单）----
    title: Mapped[str | None] = mapped_column(String(200), nullable=True, comment="如 Work Light offer")
    buyer_attn: Mapped[str | None] = mapped_column(String(100), nullable=True)
    seller_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    seller_address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    seller_contact: Mapped[str | None] = mapped_column(String(300), nullable=True)
    terms: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True, comment="▲ 条款列表")
    notes_cn: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes_en: Mapped[str | None] = mapped_column(Text, nullable=True)

    subtotal: Mapped[float | None] = mapped_column(MONEY, nullable=True)
    additional_fee: Mapped[float | None] = mapped_column(MONEY, nullable=True)
    discount: Mapped[float | None] = mapped_column(MONEY, nullable=True)
    tax_amount: Mapped[float | None] = mapped_column(MONEY, nullable=True)
    total_amount: Mapped[float | None] = mapped_column(MONEY, nullable=True)

    status: Mapped[str] = mapped_column(String(30), default="DRAFT", nullable=False, index=True)
    pdf_file_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)

    items: Mapped[list[QuotationItem]] = relationship(
        back_populates="quotation", lazy="selectin", cascade="all, delete-orphan"
    )


class QuotationItem(BaseModel):
    """报价明细（对齐对外价格表列）。"""

    __tablename__ = "quotation_item"

    quotation_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("quotation.id"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    sku_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    spec: Mapped[str | None] = mapped_column(String(500), nullable=True)
    quantity: Mapped[float] = mapped_column(Numeric(18, 2), default=1, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), default="PCS", nullable=False)
    unit_price: Mapped[float] = mapped_column(MONEY, default=0, nullable=False)
    amount: Mapped[float] = mapped_column(MONEY, default=0, nullable=False)
    remark: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sort: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # ---- 价格表列 ----
    item_no: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="Item No.")
    image_file_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Description of Goods")
    moq: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="MOQ")
    power: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="Power (W)")
    ip: Mapped[str | None] = mapped_column(String(30), nullable=True, comment="IP")
    lumen: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="Lumen (lm)")
    color_temp: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="Color TEMP.")
    color_rendering: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="Color Rendering (Ra)")
    price_valid: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="Price Valid")

    quotation: Mapped[Quotation] = relationship(back_populates="items", lazy="noload")


class ApprovalInstance(BaseModel):
    """审批实例。"""

    __tablename__ = "approval_instance"

    biz_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    biz_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    biz_no: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False, index=True)
    current_step: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    total_steps: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    applicant_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    amount: Mapped[float | None] = mapped_column(MONEY, nullable=True)
    discount_rate: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="USD", nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tasks: Mapped[list[ApprovalTask]] = relationship(
        back_populates="instance", lazy="selectin", cascade="all, delete-orphan"
    )


class ApprovalTask(BaseModel):
    """审批任务（每一步一条）。"""

    __tablename__ = "approval_task"

    instance_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("approval_instance.id"), nullable=False, index=True
    )
    step: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    approver_role: Mapped[str | None] = mapped_column(String(50), nullable=True)
    approver_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False, index=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    acted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    instance: Mapped[ApprovalInstance] = relationship(back_populates="tasks", lazy="noload")


class ApprovalLog(BaseModel):
    """审批操作日志。"""

    __tablename__ = "approval_log"

    instance_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("approval_instance.id"), nullable=False, index=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    operator_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    operator_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
