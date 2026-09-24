"""M2 客户中心 / M3 销售主链路 数据模型。"""

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
RATE = Numeric(18, 6)


# ------------------------------------------------------------------ M2 线索
class Lead(BusinessModel):
    """线索（外部获客入口）。"""

    __tablename__ = "lead"

    lead_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    contact_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    country: Mapped[str | None] = mapped_column(String(50), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="EXHIBITION", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="NEW", nullable=False, index=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    converted_company_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    converted_contact_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    converted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)


# ------------------------------------------------------------------ M2 客户
class Company(BusinessModel):
    """客户主表。"""

    __tablename__ = "company"

    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    # 三段式编码：{业务员编号}-{业务员第N个客户}-{公司第N个客户}
    owner_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    global_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    name_en: Mapped[str | None] = mapped_column(String(200), nullable=True)
    country: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    currency: Mapped[str] = mapped_column(String(10), default="USD", nullable=False)
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    customer_level: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", nullable=False, index=True)
    website: Mapped[str | None] = mapped_column(String(200), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    sync_status: Mapped[str | None] = mapped_column(String(20), default="PENDING", nullable=True)

    contacts: Mapped[list[Contact]] = relationship(
        back_populates="company", lazy="noload", cascade="all, delete-orphan"
    )


class Contact(BusinessModel):
    """联系人。"""

    __tablename__ = "contact"

    company_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("company.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    position: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    mobile: Mapped[str | None] = mapped_column(String(50), nullable=True)
    wechat: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)

    company: Mapped[Company | None] = relationship(back_populates="contacts", lazy="joined")


class BusinessCode(BaseModel):
    """客户业务编码（一客多码：内部主码 / 币别码 / K3 编码等）。"""

    __tablename__ = "business_code"

    company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("company.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    code_type: Mapped[str] = mapped_column(String(30), default="INTERNAL", nullable=False)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    remark: Mapped[str | None] = mapped_column(String(200), nullable=True)


# ------------------------------------------------------------------ M3 商机
class Opportunity(BusinessModel):
    """商机（阶段由状态机约束）。"""

    __tablename__ = "opportunity"

    opportunity_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("company.id"), nullable=False, index=True
    )
    primary_contact_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String(30), default="NEW", nullable=False, index=True)
    estimated_amount: Mapped[float | None] = mapped_column(MONEY, nullable=True)
    won_amount: Mapped[float | None] = mapped_column(MONEY, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="USD", nullable=False)
    expected_close_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    probability: Mapped[int | None] = mapped_column(Integer, nullable=True)
    product_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requirement: Mapped[str | None] = mapped_column(Text, nullable=True)
    competitor: Mapped[str | None] = mapped_column(String(200), nullable=True)
    next_action: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_followup_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lost_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # 阶段流转产生的关联引用
    inquiry_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    pricing_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    quotation_amount: Mapped[float | None] = mapped_column(MONEY, nullable=True)
    sample_record: Mapped[str | None] = mapped_column(Text, nullable=True)
    negotiation_record: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="OPEN", nullable=False, index=True)


# ------------------------------------------------------------------ M3 产品
class Product(BaseModel):
    """产品。"""

    __tablename__ = "product"

    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    name_en: Mapped[str | None] = mapped_column(String(200), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    unit: Mapped[str] = mapped_column(String(20), default="PCS", nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", nullable=False)

    skus: Mapped[list[Sku]] = relationship(back_populates="product", lazy="selectin")


class Sku(BaseModel):
    """SKU。"""

    __tablename__ = "sku"

    product_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("product.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    spec: Mapped[str | None] = mapped_column(String(300), nullable=True)
    unit: Mapped[str] = mapped_column(String(20), default="PCS", nullable=False)
    price: Mapped[float | None] = mapped_column(MONEY, nullable=True)
    cost: Mapped[float | None] = mapped_column(MONEY, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="USD", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", nullable=False)

    product: Mapped[Product] = relationship(back_populates="skus", lazy="joined")


# ------------------------------------------------------------------ M3 询价
class Inquiry(BusinessModel):
    """询价单（单据头，字段对齐客户询价单模板）。"""

    __tablename__ = "inquiry"

    inquiry_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("company.id"), nullable=True, index=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(30), default="MANUAL", nullable=False)
    requirement_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="RMB", nullable=False)
    target_price: Mapped[float | None] = mapped_column(MONEY, nullable=True)
    delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    trade_terms: Mapped[str | None] = mapped_column(String(100), nullable=True)
    payment_terms: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", nullable=False, index=True)

    # ---- 单据头快照字段（对齐《客户询价单》模板）----
    customer_code: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    customer_name: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    customer_type: Mapped[str | None] = mapped_column(String(10), nullable=True, comment="NEW/OLD")
    market: Mapped[str | None] = mapped_column(String(50), nullable=True)
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sample_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    order_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    shipment_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_order_amount: Mapped[float | None] = mapped_column(MONEY, nullable=True)
    quantity_total: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    annual_amount: Mapped[float | None] = mapped_column(MONEY, nullable=True)
    sample_lead_time: Mapped[str | None] = mapped_column(String(50), nullable=True)
    version_no: Mapped[str | None] = mapped_column(String(30), nullable=True, comment="模板版本号")
    owner_name_text: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    department_name_text: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # 客户标准纵向块（字段为行、产品为列），原样保留用于展示与导出
    spec_rows: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)

    items: Mapped[list[InquiryItem]] = relationship(
        back_populates="inquiry", lazy="selectin", cascade="all, delete-orphan"
    )


class InquiryItem(BaseModel):
    """询价明细（字段对齐 LED 规格列）。"""

    __tablename__ = "inquiry_item"

    inquiry_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("inquiry.id"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    sku_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    product_name: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    spec: Mapped[str | None] = mapped_column(String(500), nullable=True)
    quantity: Mapped[float] = mapped_column(Numeric(18, 2), default=1, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), default="PCS", nullable=False)
    target_price: Mapped[float | None] = mapped_column(MONEY, nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # ---- 询价单模板列 ----
    group_type: Mapped[str] = mapped_column(
        String(20), default="EXISTING", nullable=False, comment="EXISTING 已有产品 / NEW 需开发产品"
    )
    image_file_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    product_model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    power: Mapped[str | None] = mapped_column(String(100), nullable=True)
    voltage: Mapped[str | None] = mapped_column(String(100), nullable=True)
    battery: Mapped[str | None] = mapped_column(String(300), nullable=True)
    color_temp: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lumen: Mapped[str | None] = mapped_column(String(100), nullable=True)
    light_source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="产品尺寸")
    cri: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="显色指数")
    led_count: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="灯珠数量")
    feature: Mapped[str | None] = mapped_column(Text, nullable=True, comment="功能")
    plug: Mapped[str | None] = mapped_column(Text, nullable=True, comment="电线插头")
    main_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    lamp_shade: Mapped[str | None] = mapped_column(Text, nullable=True)
    reflector: Mapped[str | None] = mapped_column(Text, nullable=True)
    frame: Mapped[str | None] = mapped_column(Text, nullable=True, comment="压框")
    cable: Mapped[str | None] = mapped_column(Text, nullable=True)
    switch: Mapped[str | None] = mapped_column(Text, nullable=True)
    usb: Mapped[str | None] = mapped_column(Text, nullable=True)
    waterproof: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sensor: Mapped[str | None] = mapped_column(Text, nullable=True)
    certification: Mapped[str | None] = mapped_column(Text, nullable=True)
    quote_price: Mapped[float | None] = mapped_column(MONEY, nullable=True, comment="报价")
    quote_lead_time: Mapped[str | None] = mapped_column(String(100), nullable=True)
    other_requirement: Mapped[str | None] = mapped_column(Text, nullable=True)
    other_requirement2: Mapped[str | None] = mapped_column(Text, nullable=True)

    inquiry: Mapped[Inquiry] = relationship(back_populates="items", lazy="noload")


# ------------------------------------------------------------------ M3 跟进 / 任务
class Activity(BusinessModel):
    """跟进记录。"""

    __tablename__ = "activity"

    biz_type: Mapped[str] = mapped_column(String(30), default="COMPANY", nullable=False, index=True)
    biz_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    company_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    type: Mapped[str] = mapped_column(String(20), default="NOTE", nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    happened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class Task(BusinessModel):
    """任务。"""

    __tablename__ = "task"

    title: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    biz_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    biz_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    priority: Mapped[str] = mapped_column(String(10), default="MEDIUM", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
