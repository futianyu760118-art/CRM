"""M2/M3 业务 Schema。"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


# ------------------------------------------------------------------ 线索
class LeadCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    contact_name: str | None = None
    email: str | None = None
    phone: str | None = None
    country: str | None = None
    industry: str | None = None
    source: str = "EXHIBITION"
    owner_id: uuid.UUID | None = None
    remark: str | None = None


class LeadUpdate(BaseModel):
    name: str | None = None
    contact_name: str | None = None
    email: str | None = None
    phone: str | None = None
    country: str | None = None
    industry: str | None = None
    source: str | None = None
    status: str | None = None
    owner_id: uuid.UUID | None = None
    remark: str | None = None


class LeadOut(ORMModel):
    id: uuid.UUID
    lead_no: str
    name: str
    contact_name: str | None = None
    email: str | None = None
    phone: str | None = None
    country: str | None = None
    industry: str | None = None
    source: str
    status: str
    owner_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    assigned_at: datetime | None = None
    converted_company_id: uuid.UUID | None = None
    converted_at: datetime | None = None
    remark: str | None = None
    created_at: datetime


class LeadAssignIn(BaseModel):
    owner_id: uuid.UUID


class LeadConvertIn(BaseModel):
    customer_level: str | None = None
    create_contact: bool = True


class LeadConvertOut(BaseModel):
    lead_id: uuid.UUID
    company_id: uuid.UUID
    company_code: str
    contact_id: uuid.UUID | None = None


# ------------------------------------------------------------------ 客户
class CompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    name_en: str | None = None
    country: str | None = None
    currency: str = "USD"
    industry: str | None = None
    customer_level: str | None = None
    source: str | None = None
    status: str = "ACTIVE"
    website: str | None = None
    address: str | None = None
    remark: str | None = None
    owner_id: uuid.UUID | None = None


class CompanyUpdate(BaseModel):
    name: str | None = None
    name_en: str | None = None
    country: str | None = None
    currency: str | None = None
    industry: str | None = None
    customer_level: str | None = None
    source: str | None = None
    status: str | None = None
    website: str | None = None
    address: str | None = None
    remark: str | None = None
    owner_id: uuid.UUID | None = None


class CompanyOut(ORMModel):
    id: uuid.UUID
    code: str
    name: str
    name_en: str | None = None
    country: str | None = None
    currency: str = "USD"
    industry: str | None = None
    customer_level: str | None = None
    source: str | None = None
    status: str
    website: str | None = None
    address: str | None = None
    remark: str | None = None
    external_id: str | None = None
    sync_status: str | None = None
    owner_id: uuid.UUID | None = None
    owner_name: str | None = None
    department_id: uuid.UUID | None = None
    owner_seq: int | None = None
    global_seq: int | None = None
    code_rule: str | None = None
    created_at: datetime


class BusinessCodeOut(ORMModel):
    id: uuid.UUID
    code: str
    code_type: str
    currency: str | None = None
    is_primary: bool


class CurrencyCodeIn(BaseModel):
    currency: str = Field(min_length=2, max_length=10)


class CurrencyCodeOut(BaseModel):
    id: uuid.UUID
    code: str
    currency: str | None = None
    created: bool


class CustomerCodePreview(BaseModel):
    code: str
    owner_code: str | None = None
    owner_seq: int = 0
    global_seq: int = 0
    rule: str = ""


class CompanyMergeIn(BaseModel):
    source_ids: list[uuid.UUID] = Field(min_length=1)
    keep_id: uuid.UUID


class CompanyMergeOut(BaseModel):
    target_id: uuid.UUID
    merged: int
    moved_contacts: int
    moved_opportunities: int


class CompanyBatchUpdateIn(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1)
    fields: dict[str, Any] = Field(min_length=1)


class CompanyBatchDeleteIn(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1)


class DuplicateGroup(BaseModel):
    key: str
    companies: list[CompanyOut]


# ------------------------------------------------------------------ 联系人
class ContactCreate(BaseModel):
    company_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=100)
    position: str | None = None
    email: str | None = None
    phone: str | None = None
    mobile: str | None = None
    wechat: str | None = None
    is_primary: bool = False
    remark: str | None = None


class ContactUpdate(BaseModel):
    company_id: uuid.UUID | None = None
    name: str | None = None
    position: str | None = None
    email: str | None = None
    phone: str | None = None
    mobile: str | None = None
    wechat: str | None = None
    is_primary: bool | None = None
    remark: str | None = None


class ContactOut(ORMModel):
    id: uuid.UUID
    company_id: uuid.UUID | None = None
    company_name: str | None = None
    name: str
    position: str | None = None
    email: str | None = None
    phone: str | None = None
    mobile: str | None = None
    wechat: str | None = None
    is_primary: bool
    remark: str | None = None
    owner_id: uuid.UUID | None = None
    created_at: datetime


# ------------------------------------------------------------------ 商机
class OpportunityCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    company_id: uuid.UUID
    primary_contact_id: uuid.UUID | None = None
    estimated_amount: float | None = None
    currency: str = "USD"
    expected_close_date: date | None = None
    probability: int | None = None
    product_category: str | None = None
    quantity: int | None = None
    requirement: str | None = None
    competitor: str | None = None
    next_action: str | None = None
    owner_id: uuid.UUID | None = None


class OpportunityUpdate(BaseModel):
    name: str | None = None
    primary_contact_id: uuid.UUID | None = None
    estimated_amount: float | None = None
    currency: str | None = None
    expected_close_date: date | None = None
    probability: int | None = None
    product_category: str | None = None
    quantity: int | None = None
    requirement: str | None = None
    competitor: str | None = None
    next_action: str | None = None
    lost_reason: str | None = None
    won_amount: float | None = None
    sample_record: str | None = None
    negotiation_record: str | None = None
    status: str | None = None
    owner_id: uuid.UUID | None = None


class OpportunityStageIn(BaseModel):
    stage: str
    lost_reason: str | None = None
    won_amount: float | None = None
    sample_record: str | None = None
    negotiation_record: str | None = None
    requirement: str | None = None
    estimated_amount: float | None = None
    product_category: str | None = None
    quantity: int | None = None
    inquiry_id: uuid.UUID | None = None
    pricing_id: uuid.UUID | None = None
    quotation_amount: float | None = None


class OpportunityOut(ORMModel):
    id: uuid.UUID
    opportunity_no: str
    name: str
    company_id: uuid.UUID
    company_name: str | None = None
    primary_contact_id: uuid.UUID | None = None
    stage: str
    stage_label: str | None = None
    estimated_amount: float | None = None
    won_amount: float | None = None
    currency: str
    expected_close_date: date | None = None
    probability: int | None = None
    product_category: str | None = None
    quantity: int | None = None
    requirement: str | None = None
    competitor: str | None = None
    next_action: str | None = None
    last_followup_at: datetime | None = None
    lost_reason: str | None = None
    inquiry_id: uuid.UUID | None = None
    quotation_amount: float | None = None
    status: str
    owner_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    created_at: datetime


class StageCatalogOut(BaseModel):
    value: str
    label: str
    next_stages: list[str]
    required_fields: list[str]
    roles: list[str]


# ------------------------------------------------------------------ 产品 / SKU
class ProductCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=200)
    name_en: str | None = None
    category: str | None = None
    unit: str = "PCS"
    description: str | None = None
    status: str = "ACTIVE"


class ProductUpdate(BaseModel):
    name: str | None = None
    name_en: str | None = None
    category: str | None = None
    unit: str | None = None
    description: str | None = None
    status: str | None = None


class SkuOut(ORMModel):
    id: uuid.UUID
    product_id: uuid.UUID
    code: str
    spec: str | None = None
    unit: str
    price: float | None = None
    cost: float | None = None
    currency: str
    status: str


class ProductOut(ORMModel):
    id: uuid.UUID
    code: str
    name: str
    name_en: str | None = None
    category: str | None = None
    unit: str
    description: str | None = None
    status: str
    created_at: datetime
    skus: list[SkuOut] = Field(default_factory=list)


class SkuCreate(BaseModel):
    product_id: uuid.UUID
    code: str = Field(min_length=1, max_length=50)
    spec: str | None = None
    unit: str = "PCS"
    price: float | None = None
    cost: float | None = None
    currency: str = "USD"
    status: str = "ACTIVE"


class SkuUpdate(BaseModel):
    spec: str | None = None
    unit: str | None = None
    price: float | None = None
    cost: float | None = None
    currency: str | None = None
    status: str | None = None


# ------------------------------------------------------------------ 询价
LED_FIELDS = (
    "product_model",
    "power",
    "voltage",
    "battery",
    "color_temp",
    "lumen",
    "light_source",
    "main_body",
    "lamp_shade",
    "reflector",
    "frame",
    "cable",
    "switch",
    "usb",
    "waterproof",
    "sensor",
    "certification",
    "quote_lead_time",
    "other_requirement",
    "other_requirement2",
)


class InquiryItemIn(BaseModel):
    product_id: uuid.UUID | None = None
    sku_id: uuid.UUID | None = None
    product_name: str = ""
    spec: str | None = None
    quantity: float = 0
    unit: str = "PCS"
    target_price: float | None = None
    remark: str | None = None
    sort: int = 0
    # 询价单模板列
    group_type: str = "EXISTING"
    image_file_id: uuid.UUID | None = None
    product_model: str | None = None
    power: str | None = None
    voltage: str | None = None
    size: str | None = None
    cri: str | None = None
    led_count: str | None = None
    feature: str | None = None
    plug: str | None = None
    battery: str | None = None
    color_temp: str | None = None
    lumen: str | None = None
    light_source: str | None = None
    main_body: str | None = None
    lamp_shade: str | None = None
    reflector: str | None = None
    frame: str | None = None
    cable: str | None = None
    switch: str | None = None
    usb: str | None = None
    waterproof: str | None = None
    sensor: str | None = None
    certification: str | None = None
    quote_price: float | None = None
    quote_lead_time: str | None = None
    other_requirement: str | None = None
    other_requirement2: str | None = None


class InquiryCreate(BaseModel):
    company_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    opportunity_id: uuid.UUID | None = None
    source: str = "MANUAL"
    requirement_text: str | None = None
    currency: str = "RMB"
    target_price: float | None = None
    delivery_date: date | None = None
    trade_terms: str | None = None
    payment_terms: str | None = None
    owner_id: uuid.UUID | None = None
    # 单据头（询价单模板）
    customer_code: str | None = None
    customer_name: str | None = None
    customer_type: str | None = None
    market: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    sample_date: datetime | None = None
    order_date: datetime | None = None
    shipment_date: datetime | None = None
    first_order_amount: float | None = None
    quantity_total: float | None = None
    annual_amount: float | None = None
    sample_lead_time: str | None = None
    version_no: str | None = None
    owner_name_text: str | None = None
    department_name_text: str | None = None
    spec_rows: list[dict[str, Any]] | None = None
    items: list[InquiryItemIn] = Field(default_factory=list)


class InquiryUpdate(BaseModel):
    contact_id: uuid.UUID | None = None
    requirement_text: str | None = None
    currency: str | None = None
    target_price: float | None = None
    delivery_date: date | None = None
    trade_terms: str | None = None
    payment_terms: str | None = None
    customer_code: str | None = None
    customer_name: str | None = None
    customer_type: str | None = None
    market: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    sample_date: datetime | None = None
    order_date: datetime | None = None
    shipment_date: datetime | None = None
    first_order_amount: float | None = None
    quantity_total: float | None = None
    annual_amount: float | None = None
    sample_lead_time: str | None = None
    spec_rows: list[dict[str, Any]] | None = None
    items: list[InquiryItemIn] | None = None


class InquiryItemOut(ORMModel):
    id: uuid.UUID
    product_id: uuid.UUID | None = None
    sku_id: uuid.UUID | None = None
    product_name: str
    spec: str | None = None
    quantity: float
    unit: str
    target_price: float | None = None
    remark: str | None = None
    sort: int
    group_type: str
    image_file_id: uuid.UUID | None = None
    product_model: str | None = None
    power: str | None = None
    voltage: str | None = None
    size: str | None = None
    cri: str | None = None
    led_count: str | None = None
    feature: str | None = None
    plug: str | None = None
    battery: str | None = None
    color_temp: str | None = None
    lumen: str | None = None
    light_source: str | None = None
    main_body: str | None = None
    lamp_shade: str | None = None
    reflector: str | None = None
    frame: str | None = None
    cable: str | None = None
    switch: str | None = None
    usb: str | None = None
    waterproof: str | None = None
    sensor: str | None = None
    certification: str | None = None
    quote_price: float | None = None
    quote_lead_time: str | None = None
    other_requirement: str | None = None
    other_requirement2: str | None = None


class InquiryOut(ORMModel):
    id: uuid.UUID
    inquiry_no: str
    company_id: uuid.UUID | None = None
    company_name: str | None = None
    contact_id: uuid.UUID | None = None
    contact_name: str | None = None
    opportunity_id: uuid.UUID | None = None
    source: str
    requirement_text: str | None = None
    currency: str
    target_price: float | None = None
    delivery_date: date | None = None
    trade_terms: str | None = None
    payment_terms: str | None = None
    status: str
    owner_id: uuid.UUID | None = None
    owner_name: str | None = None
    department_id: uuid.UUID | None = None
    department_name: str | None = None
    created_at: datetime
    # 单据头
    customer_code: str | None = None
    customer_name: str | None = None
    customer_type: str | None = None
    market: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    sample_date: datetime | None = None
    order_date: datetime | None = None
    shipment_date: datetime | None = None
    first_order_amount: float | None = None
    quantity_total: float | None = None
    annual_amount: float | None = None
    sample_lead_time: str | None = None
    version_no: str | None = None
    owner_name_text: str | None = None
    department_name_text: str | None = None
    spec_rows: list[dict[str, Any]] | None = None
    items: list[InquiryItemOut] = Field(default_factory=list)
    pricing_versions: int = 0


# ------------------------------------------------------------------ 跟进 / 任务
class ActivityCreate(BaseModel):
    biz_type: str = "COMPANY"
    biz_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    opportunity_id: uuid.UUID | None = None
    type: str = "NOTE"
    content: str = Field(min_length=1)
    happened_at: datetime | None = None


class ActivityUpdate(BaseModel):
    type: str | None = None
    content: str | None = None
    happened_at: datetime | None = None


class ActivityOut(ORMModel):
    id: uuid.UUID
    biz_type: str
    biz_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None
    opportunity_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    type: str
    content: str
    happened_at: datetime | None = None
    owner_id: uuid.UUID | None = None
    created_at: datetime


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str | None = None
    biz_type: str | None = None
    biz_id: uuid.UUID | None = None
    assignee_id: uuid.UUID | None = None
    due_date: datetime | None = None
    priority: str = "MEDIUM"


class TaskUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    assignee_id: uuid.UUID | None = None
    due_date: datetime | None = None
    priority: str | None = None
    status: str | None = None


class TaskOut(ORMModel):
    id: uuid.UUID
    title: str
    content: str | None = None
    biz_type: str | None = None
    biz_id: uuid.UUID | None = None
    assignee_id: uuid.UUID | None = None
    due_date: datetime | None = None
    priority: str
    status: str
    completed_at: datetime | None = None
    owner_id: uuid.UUID | None = None
    created_at: datetime
