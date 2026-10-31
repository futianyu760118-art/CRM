"""M4 核价 / 报价 / 审批 Schema。"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


# ------------------------------------------------------------------ 核价
class CostInput(BaseModel):
    material_cost: float = 0
    labor_cost: float = 0
    packaging_cost: float = 0
    freight_cost: float = 0
    tooling_cost: float = 0
    customization_cost: float = 0
    moq_cost: float = 0
    other_cost: float = 0
    loss_cost: float = 0


class PricingCreate(BaseModel):
    inquiry_id: uuid.UUID
    currency: str = "USD"
    target_margin: float | None = None
    discount_rate: float = Field(default=1, gt=0, le=1, description="折扣率 ∈(0,1]")
    costs: CostInput = Field(default_factory=CostInput)
    remark: str | None = None


class PricingUpdate(BaseModel):
    currency: str | None = None
    target_margin: float | None = None
    discount_rate: float | None = Field(default=None, gt=0, le=1)
    costs: CostInput | None = None
    remark: str | None = None


class PricingOut(ORMModel):
    id: uuid.UUID
    inquiry_id: uuid.UUID
    inquiry_no: str | None = None
    company_name: str | None = None
    version: int
    status: str
    currency: str
    material_cost: float | None = None
    labor_cost: float | None = None
    packaging_cost: float | None = None
    freight_cost: float | None = None
    tooling_cost: float | None = None
    customization_cost: float | None = None
    moq_cost: float | None = None
    other_cost: float | None = None
    loss_cost: float | None = None
    total_cost: float | None = None
    base_cost: float | None = None
    target_margin: float | None = None
    discount_rate: float | None = None
    floor_price: float | None = None
    suggested_price: float | None = None
    final_price: float | None = None
    can_view_cost: bool = True
    can_view_floor: bool = True
    remark: str | None = None
    created_by: uuid.UUID | None = None
    approved_by: uuid.UUID | None = None
    approved_at: datetime | None = None
    created_at: datetime


class PricingCalcIn(CostInput):
    target_margin: float = 0.2
    discount_rate: float = Field(default=1, gt=0, le=1)
    quantity: float = 1
    exchange_rate: float = 1


class PricingCalcOut(BaseModel):
    base_cost: float
    total_cost: float
    unit_cost: float
    floor_price: float
    final_price: float
    suggested_price: float
    target_margin: float
    discount_rate: float
    breakdown: dict[str, float]


class PricingApproveIn(BaseModel):
    approved: bool = True
    comment: str | None = None


class PricingRuleCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=200)
    conditions: dict[str, Any] | None = None
    actions: dict[str, Any] | None = None
    priority: int = 0
    enabled: bool = True
    description: str | None = None


class PricingRuleUpdate(BaseModel):
    name: str | None = None
    conditions: dict[str, Any] | None = None
    actions: dict[str, Any] | None = None
    priority: int | None = None
    enabled: bool | None = None
    description: str | None = None


class PricingRuleOut(ORMModel):
    id: uuid.UUID
    code: str
    name: str
    conditions: dict[str, Any] | None = None
    actions: dict[str, Any] | None = None
    priority: int
    enabled: bool
    description: str | None = None
    created_at: datetime


# ------------------------------------------------------------------ 报价
class QuotationItemIn(BaseModel):
    product_id: uuid.UUID | None = None
    sku_id: uuid.UUID | None = None
    product_name: str = ""
    spec: str | None = None
    quantity: float = 1
    unit: str = "PCS"
    unit_price: float = 0
    remark: str | None = None
    sort: int = 0
    # 价格表列
    item_no: str | None = None
    image_file_id: uuid.UUID | None = None
    description: str | None = None
    moq: str | None = None
    power: str | None = None
    ip: str | None = None
    lumen: str | None = None
    color_temp: str | None = None
    color_rendering: str | None = None
    price_valid: str | None = None


class QuotationCreate(BaseModel):
    company_id: uuid.UUID
    contact_id: uuid.UUID | None = None
    opportunity_id: uuid.UUID | None = None
    inquiry_id: uuid.UUID | None = None
    pricing_id: uuid.UUID | None = None
    currency: str = "RMB"
    # 未填时由 ``system_config.pricing.exchange_rate`` 取值快照（默认 7.25）。
    exchange_rate: float | None = None
    discount_rate: float = Field(default=1, gt=0, le=1)
    incoterm: str | None = None
    payment_terms: str | None = None
    warranty: str | None = None
    valid_days: int = 30
    additional_fee: float = 0
    discount: float = 0
    tax_amount: float = 0
    remark: str | None = None
    # 价格表版式
    title: str | None = None
    buyer_attn: str | None = None
    seller_name: str | None = None
    seller_address: str | None = None
    seller_contact: str | None = None
    terms: list[str] | None = None
    notes_cn: str | None = None
    notes_en: str | None = None
    items: list[QuotationItemIn] = Field(default_factory=list)


class QuotationUpdate(BaseModel):
    contact_id: uuid.UUID | None = None
    currency: str | None = None
    exchange_rate: float | None = None
    discount_rate: float | None = Field(default=None, gt=0, le=1)
    incoterm: str | None = None
    payment_terms: str | None = None
    warranty: str | None = None
    valid_days: int | None = None
    additional_fee: float | None = None
    discount: float | None = None
    tax_amount: float | None = None
    remark: str | None = None
    title: str | None = None
    buyer_attn: str | None = None
    seller_name: str | None = None
    seller_address: str | None = None
    seller_contact: str | None = None
    terms: list[str] | None = None
    notes_cn: str | None = None
    notes_en: str | None = None
    items: list[QuotationItemIn] | None = None


class QuotationFromPricingIn(BaseModel):
    pricing_id: uuid.UUID
    margin_over_floor: float = 0.0
    incoterm: str | None = "FOB"
    payment_terms: str | None = "30% T/T, 70% before shipment"
    valid_days: int = 30


class QuotationItemOut(ORMModel):
    id: uuid.UUID
    product_id: uuid.UUID | None = None
    sku_id: uuid.UUID | None = None
    product_name: str
    spec: str | None = None
    quantity: float
    unit: str
    unit_price: float
    amount: float
    remark: str | None = None
    sort: int
    item_no: str | None = None
    image_file_id: uuid.UUID | None = None
    description: str | None = None
    moq: str | None = None
    power: str | None = None
    ip: str | None = None
    lumen: str | None = None
    color_temp: str | None = None
    color_rendering: str | None = None
    price_valid: str | None = None


class QuotationOut(ORMModel):
    id: uuid.UUID
    quotation_no: str
    company_id: uuid.UUID
    company_name: str | None = None
    contact_id: uuid.UUID | None = None
    contact_name: str | None = None
    opportunity_id: uuid.UUID | None = None
    inquiry_id: uuid.UUID | None = None
    pricing_id: uuid.UUID | None = None
    version: int
    currency: str
    exchange_rate: float
    discount_rate: float | None = None
    incoterm: str | None = None
    payment_terms: str | None = None
    warranty: str | None = None
    valid_days: int
    valid_until: date | None = None
    subtotal: float | None = None
    additional_fee: float | None = None
    discount: float | None = None
    tax_amount: float | None = None
    total_amount: float | None = None
    status: str
    pdf_file_id: uuid.UUID | None = None
    approval_id: uuid.UUID | None = None
    remark: str | None = None
    title: str | None = None
    buyer_attn: str | None = None
    seller_name: str | None = None
    seller_address: str | None = None
    seller_contact: str | None = None
    terms: list[str] | None = None
    notes_cn: str | None = None
    notes_en: str | None = None
    created_by: uuid.UUID | None = None
    approved_by: uuid.UUID | None = None
    approved_at: datetime | None = None
    sent_at: datetime | None = None
    created_at: datetime
    items: list[QuotationItemOut] = Field(default_factory=list)


class QuotationSendIn(BaseModel):
    account_id: uuid.UUID | None = None
    to_addrs: list[str] = Field(default_factory=list)
    cc_addrs: list[str] = Field(default_factory=list)
    subject: str | None = None
    body: str | None = None
    attach_pdf: bool = True


class PublishResultOut(BaseModel):
    ok: bool
    detail: str
    file_id: uuid.UUID | None = None
    filename: str | None = None


# ------------------------------------------------------------------ 审批
class ApprovalTaskOut(ORMModel):
    id: uuid.UUID
    step: int
    approver_role: str | None = None
    approver_id: uuid.UUID | None = None
    status: str
    comment: str | None = None
    acted_at: datetime | None = None


class ApprovalOut(ORMModel):
    id: uuid.UUID
    biz_type: str
    biz_id: uuid.UUID
    biz_no: str | None = None
    title: str
    status: str
    current_step: int
    total_steps: int
    applicant_id: uuid.UUID | None = None
    applicant_name: str | None = None
    amount: float | None = None
    discount_rate: float | None = None
    currency: str
    finished_at: datetime | None = None
    created_at: datetime
    tasks: list[ApprovalTaskOut] = Field(default_factory=list)


class ApprovalActionIn(BaseModel):
    comment: str | None = None
