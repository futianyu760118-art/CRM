"""M2/M3 业务 Schema。"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.domain import dictionaries as dic
from app.schemas.common import ORMModel

_WHATSAPP_PATTERN = re.compile(r"^[+0-9\s-]*$")


def _check_enum(value: str | None, options: dict[str, str]) -> str | None:
    if value is None:
        return None
    if value not in options:
        raise ValueError(f"仅可选 {dic.labels_text(options)}")
    return value


# ------------------------------------------------------------------ 线索
class LeadCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    contact_name: str | None = None
    email: str | None = None
    phone: str | None = None
    country: str | None = None
    industry: str | None = None
    source: str = "EXHIBITION"
    requirement_text: str | None = Field(default=None, max_length=5000)
    lead_level: str = dic.LEAD_LEVEL_DEFAULT
    background: str | None = Field(default=None, max_length=5000)
    channel: str = dic.LEAD_CHANNEL_DEFAULT
    owner_id: uuid.UUID | None = None
    remark: str | None = None
    force: bool = False
    dedup_note: str | None = Field(default=None, max_length=200)

    @field_validator("lead_level")
    @classmethod
    def _lead_level(cls, value: str | None) -> str | None:
        return _check_enum(value, dic.LEAD_LEVELS)

    @field_validator("channel")
    @classmethod
    def _channel(cls, value: str | None) -> str | None:
        return _check_enum(value, dic.LEAD_CHANNELS)


class LeadUpdate(BaseModel):
    name: str | None = None
    contact_name: str | None = None
    email: str | None = None
    phone: str | None = None
    country: str | None = None
    industry: str | None = None
    source: str | None = None
    status: str | None = None
    requirement_text: str | None = Field(default=None, max_length=5000)
    lead_level: str | None = None
    background: str | None = Field(default=None, max_length=5000)
    channel: str | None = None
    owner_id: uuid.UUID | None = None
    remark: str | None = None
    force: bool = False
    dedup_note: str | None = Field(default=None, max_length=200)

    @field_validator("lead_level")
    @classmethod
    def _lead_level(cls, value: str | None) -> str | None:
        return _check_enum(value, dic.LEAD_LEVELS)

    @field_validator("channel")
    @classmethod
    def _channel(cls, value: str | None) -> str | None:
        return _check_enum(value, dic.LEAD_CHANNELS)


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
    requirement_text: str | None = None
    lead_level: str | None = None
    background: str | None = None
    channel: str | None = None
    status: str
    owner_id: uuid.UUID | None = None
    owner_name: str | None = None
    department_id: uuid.UUID | None = None
    assigned_at: datetime | None = None
    converted_company_id: uuid.UUID | None = None
    converted_company_name: str | None = None
    converted_company_code: str | None = None
    converted_at: datetime | None = None
    last_followup_at: datetime | None = None
    next_due_date: datetime | None = None
    remark: str | None = None
    created_at: datetime


class LeadAssignIn(BaseModel):
    owner_id: uuid.UUID


class LeadDuplicateCheckIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: str | None = None
    phone: str | None = None
    exclude_lead_id: uuid.UUID | None = None


class LeadConvertIn(BaseModel):
    customer_level: str | None = None
    create_contact: bool = True
    link_company_id: uuid.UUID | None = None
    non_duplicate_reason: str | None = Field(default=None, min_length=1, max_length=200)
    relation_type: str = dic.CONTACT_RELATION_DEFAULT

    @field_validator("relation_type")
    @classmethod
    def _relation_type(cls, value: str | None) -> str | None:
        return _check_enum(value, dic.CONTACT_RELATION_TYPES)


class LeadConvertOut(BaseModel):
    lead_id: uuid.UUID
    company_id: uuid.UUID
    company_code: str
    contact_id: uuid.UUID | None = None
    linked_existing: bool = False


# ------------------------------------------------------------------ 客户
def _check_website(value: str | None) -> str | None:
    if value is None or value == "":
        return value
    if not value.startswith(("http://", "https://")):
        raise ValueError("请输入以 http:// 或 https:// 开头的网址")
    return value


class CompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    name_en: str | None = None
    country: str | None = None
    currency: str = "USD"
    industry: str | None = None
    customer_level: str | None = None
    source: str | None = dic.CUSTOMER_SOURCE_DEFAULT
    customer_type: str | None = dic.CUSTOMER_TYPE_DEFAULT
    status: str = "ACTIVE"
    website: str | None = Field(default=None, max_length=200)
    address: str | None = Field(default=None, max_length=500)
    company_background: str | None = Field(default=None, max_length=5000)
    main_products: str | None = Field(default=None, max_length=500)
    brand: str | None = Field(default=None, max_length=300)
    sales_channel_market: str | None = Field(default=None, max_length=1000)
    payment_method: str | None = None
    remark: str | None = None
    owner_id: uuid.UUID | None = None

    @field_validator("source")
    @classmethod
    def _source(cls, value: str | None) -> str | None:
        return _check_enum(value, dic.CUSTOMER_SOURCES)

    @field_validator("customer_type")
    @classmethod
    def _customer_type(cls, value: str | None) -> str | None:
        return _check_enum(value, dic.CUSTOMER_TYPES)

    @field_validator("payment_method")
    @classmethod
    def _payment_method(cls, value: str | None) -> str | None:
        return _check_enum(value, dic.PAYMENT_METHODS)

    @field_validator("website")
    @classmethod
    def _website(cls, value: str | None) -> str | None:
        return _check_website(value)


class CompanyUpdate(BaseModel):
    name: str | None = None
    name_en: str | None = None
    country: str | None = None
    currency: str | None = None
    industry: str | None = None
    customer_level: str | None = None
    source: str | None = None
    customer_type: str | None = None
    status: str | None = None
    website: str | None = Field(default=None, max_length=200)
    address: str | None = Field(default=None, max_length=500)
    company_background: str | None = Field(default=None, max_length=5000)
    main_products: str | None = Field(default=None, max_length=500)
    brand: str | None = Field(default=None, max_length=300)
    sales_channel_market: str | None = Field(default=None, max_length=1000)
    payment_method: str | None = None
    remark: str | None = None
    owner_id: uuid.UUID | None = None

    @field_validator("source")
    @classmethod
    def _source(cls, value: str | None) -> str | None:
        return _check_enum(value, dic.CUSTOMER_SOURCES)

    @field_validator("customer_type")
    @classmethod
    def _customer_type(cls, value: str | None) -> str | None:
        return _check_enum(value, dic.CUSTOMER_TYPES)

    @field_validator("payment_method")
    @classmethod
    def _payment_method(cls, value: str | None) -> str | None:
        return _check_enum(value, dic.PAYMENT_METHODS)

    @field_validator("website")
    @classmethod
    def _website(cls, value: str | None) -> str | None:
        return _check_website(value)


class PrimaryContactOut(BaseModel):
    name: str
    contact_value: str | None = None


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
    customer_type: str | None = None
    status: str
    website: str | None = None
    address: str | None = None
    company_background: str | None = None
    main_products: str | None = None
    brand: str | None = None
    sales_channel_market: str | None = None
    payment_method: str | None = None
    remark: str | None = None
    external_id: str | None = None
    sync_status: str | None = None
    owner_id: uuid.UUID | None = None
    owner_name: str | None = None
    department_id: uuid.UUID | None = None
    owner_seq: int | None = None
    global_seq: int | None = None
    code_rule: str | None = None
    customer_group: str | None = None
    group_reason: str | None = None
    primary_contact: PrimaryContactOut | None = None
    created_at: datetime


class CustomerGroupSummary(BaseModel):
    all: int = 0
    new: int = 0
    active: int = 0
    dormant: int = 0


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
def _check_whatsapp(value: str | None) -> str | None:
    if value is None or value == "":
        return value
    if not _WHATSAPP_PATTERN.match(value):
        raise ValueError("仅可包含数字、空格、+ 和 -")
    return value


class ContactCreate(BaseModel):
    company_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=100)
    position: str | None = Field(default=None, max_length=100)
    email: str | None = None
    phone: str | None = None
    mobile: str | None = None
    wechat: str | None = Field(default=None, max_length=100)
    whatsapp: str | None = Field(default=None, max_length=100)
    relation_type: str | None = dic.CONTACT_RELATION_DEFAULT
    is_primary: bool = False
    remark: str | None = None
    link_to_existing_id: uuid.UUID | None = None
    force_independent: bool = False

    @field_validator("whatsapp")
    @classmethod
    def _whatsapp(cls, value: str | None) -> str | None:
        return _check_whatsapp(value)

    @field_validator("relation_type")
    @classmethod
    def _relation_type(cls, value: str | None) -> str | None:
        return _check_enum(value, dic.CONTACT_RELATION_TYPES)


class ContactUpdate(BaseModel):
    company_id: uuid.UUID | None = None
    name: str | None = None
    position: str | None = Field(default=None, max_length=100)
    email: str | None = None
    phone: str | None = None
    mobile: str | None = None
    wechat: str | None = Field(default=None, max_length=100)
    whatsapp: str | None = Field(default=None, max_length=100)
    relation_type: str | None = None
    is_primary: bool | None = None
    remark: str | None = None

    @field_validator("whatsapp")
    @classmethod
    def _whatsapp(cls, value: str | None) -> str | None:
        return _check_whatsapp(value)

    @field_validator("relation_type")
    @classmethod
    def _relation_type(cls, value: str | None) -> str | None:
        return _check_enum(value, dic.CONTACT_RELATION_TYPES)


class ContactCompanyOut(BaseModel):
    company_id: uuid.UUID
    company_code: str | None = None
    company_name: str
    relation_type: str
    relation_label: str
    is_primary: bool


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
    whatsapp: str | None = None
    relation_type: str | None = None
    relation_label: str | None = None
    is_primary: bool
    remark: str | None = None
    owner_id: uuid.UUID | None = None
    companies: list[ContactCompanyOut] = Field(default_factory=list)
    created_at: datetime


class ContactLinkIn(BaseModel):
    company_id: uuid.UUID
    relation_type: str = dic.CONTACT_RELATION_DEFAULT
    is_primary: bool = False

    @field_validator("relation_type")
    @classmethod
    def _relation_type(cls, value: str) -> str:
        return _check_enum(value, dic.CONTACT_RELATION_TYPES) or dic.CONTACT_RELATION_DEFAULT


class ContactPrimaryIn(BaseModel):
    company_id: uuid.UUID | None = None


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
