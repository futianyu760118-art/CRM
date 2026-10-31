"""销售中心 6 模块 Schema（订单 / 样品 / 报价库 / 问题反馈）。"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain import dictionaries as dic
from app.schemas.common import ORMModel


# ------------------------------------------------------------------ 订单
class SalesOrderCreate(BaseModel):
    order_no: str = Field(min_length=1, max_length=50)
    line_no: str = ""
    customer_name: str | None = None
    customer_code: str | None = None
    product_code: str | None = None
    product_name: str | None = None
    project_no: str | None = None
    quantity: float = 0
    completed_qty: float = 0
    order_amount: float = 0
    risk_level: str = "blue"
    promised_date: date | None = None
    plan_date: date | None = None
    online_date: date | None = None
    remark: str | None = None
    owner_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _require_customer(self) -> SalesOrderCreate:
        if not self.customer_name and not self.customer_code:
            raise ValueError("订单号与客户名称/客户代码至少填一项")
        return self


class SalesOrderUpdate(BaseModel):
    customer_name: str | None = None
    customer_code: str | None = None
    product_code: str | None = None
    product_name: str | None = None
    project_no: str | None = None
    quantity: float | None = None
    completed_qty: float | None = None
    order_amount: float | None = None
    risk_level: str | None = None
    promised_date: date | None = None
    plan_date: date | None = None
    online_date: date | None = None
    user_status_locked: bool | None = None
    remark: str | None = None
    owner_id: uuid.UUID | None = None


class SalesOrderStatusIn(BaseModel):
    status: str = Field(min_length=1, max_length=30)
    reason: str | None = None


class SalesOrderOut(ORMModel):
    id: uuid.UUID
    order_no: str
    line_no: str
    external_id: str | None = None
    company_id: uuid.UUID | None = None
    customer_name: str | None = None
    customer_code: str | None = None
    product_code: str | None = None
    product_name: str | None = None
    project_no: str | None = None
    quantity: float
    completed_qty: float
    order_amount: float
    status: str
    risk_level: str
    promised_date: date | None = None
    plan_date: date | None = None
    online_date: date | None = None
    user_status_locked: bool
    user_status_modified_at: datetime | None = None
    user_status_modified_by: uuid.UUID | None = None
    remark: str | None = None
    sync_status: str
    last_sync_at: datetime | None = None
    owner_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


# ------------------------------------------------------------------ 样品
_TRACKING_PATTERN = re.compile(r"^[A-Za-z0-9-]{6,40}$")


def _check_quantity(value: float | None) -> float | None:
    if value is None:
        return None
    if value <= 0:
        raise ValueError("必须大于 0")
    if abs(value * 100 - round(value * 100)) > 1e-9:
        raise ValueError("最多 2 位小数")
    return value


def _check_tracking(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if not _TRACKING_PATTERN.fullmatch(value):
        raise ValueError("应为 6–40 位字母、数字或连字符")
    return value


def _check_courier(value: str | None) -> str | None:
    if value is None:
        return None
    if value not in dic.COURIERS:
        raise ValueError(f"仅可选 {dic.labels_text(dic.COURIERS)}")
    return value


class SampleCreate(BaseModel):
    sample_no: str | None = None
    customer_name: str = Field(min_length=1, max_length=200)
    inquiry_no: str | None = None
    product_name: str | None = None
    product_code: str | None = None
    product_model: str = Field(min_length=1, max_length=100)
    quantity: float = Field(default=1, gt=0)
    sample_type: str = "常规"
    sample_requirement: str | None = Field(default=None, max_length=2000)
    plan_date: date | None = None
    send_date: date | None = None
    confirm_date: date | None = None
    courier: str | None = None
    tracking_no: str | None = Field(default=None, max_length=40)
    opportunity_id: uuid.UUID | None = None
    remark: str | None = None
    owner_id: uuid.UUID | None = None

    @field_validator("quantity")
    @classmethod
    def _quantity(cls, value: float | None) -> float | None:
        return _check_quantity(value)

    @field_validator("courier")
    @classmethod
    def _courier(cls, value: str | None) -> str | None:
        return _check_courier(value)

    @field_validator("tracking_no")
    @classmethod
    def _tracking(cls, value: str | None) -> str | None:
        return _check_tracking(value)


class SampleUpdate(BaseModel):
    customer_name: str | None = Field(default=None, max_length=200)
    inquiry_no: str | None = None
    product_name: str | None = None
    product_code: str | None = None
    product_model: str | None = Field(default=None, min_length=1, max_length=100)
    quantity: float | None = Field(default=None, gt=0)
    sample_type: str | None = None
    sample_requirement: str | None = Field(default=None, max_length=2000)
    plan_date: date | None = None
    send_date: date | None = None
    confirm_date: date | None = None
    courier: str | None = None
    tracking_no: str | None = Field(default=None, max_length=40)
    feedback: str | None = Field(default=None, max_length=2000)
    feedback_date: date | None = None
    opportunity_id: uuid.UUID | None = None
    remark: str | None = None
    owner_id: uuid.UUID | None = None

    @field_validator("quantity")
    @classmethod
    def _quantity(cls, value: float | None) -> float | None:
        return _check_quantity(value)

    @field_validator("courier")
    @classmethod
    def _courier(cls, value: str | None) -> str | None:
        return _check_courier(value)

    @field_validator("tracking_no")
    @classmethod
    def _tracking(cls, value: str | None) -> str | None:
        return _check_tracking(value)


class SampleStatusIn(BaseModel):
    status: str = Field(min_length=1, max_length=20)
    courier: str | None = None
    tracking_no: str | None = Field(default=None, max_length=40)
    send_date: date | None = None
    feedback: str | None = Field(default=None, max_length=2000)
    feedback_date: date | None = None

    @field_validator("courier")
    @classmethod
    def _courier(cls, value: str | None) -> str | None:
        return _check_courier(value)

    @field_validator("tracking_no")
    @classmethod
    def _tracking(cls, value: str | None) -> str | None:
        return _check_tracking(value)


class SampleOut(ORMModel):
    id: uuid.UUID
    sample_no: str
    external_id: str | None = None
    company_id: uuid.UUID | None = None
    customer_name: str
    inquiry_no: str | None = None
    inquiry_id: uuid.UUID | None = None
    product_name: str | None = None
    product_code: str | None = None
    product_model: str | None = None
    quantity: float
    sample_type: str
    sample_requirement: str | None = None
    status: str
    plan_date: date | None = None
    overdue_days: int | None = None
    send_date: date | None = None
    confirm_date: date | None = None
    courier: str | None = None
    tracking_no: str | None = None
    feedback: str | None = None
    feedback_date: date | None = None
    opportunity_id: uuid.UUID | None = None
    remark: str | None = None
    sync_status: str
    last_sync_at: datetime | None = None
    owner_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


# ------------------------------------------------------------------ 报价库
class QuoteLibraryCreate(BaseModel):
    external_model: str = Field(min_length=1, max_length=200)
    certificate_level: str = ""
    internal_model: str | None = None
    product_name: str | None = None
    category: str | None = None
    power: str | None = None
    configuration: str | None = None
    specs: str | None = None
    price_rmb: float | None = None
    price_usd: float | None = None
    unit_price: float | None = None
    min_price: float | None = None
    validity_days: int = 30
    source_inquiry_no: str | None = None
    remark: str | None = None

    @model_validator(mode="after")
    def _require_price(self) -> QuoteLibraryCreate:
        if self.price_rmb is None and self.price_usd is None:
            raise ValueError("价格 RMB/USD 至少填一项")
        return self


class QuoteLibraryUpdate(BaseModel):
    certificate_level: str | None = None
    internal_model: str | None = None
    product_name: str | None = None
    category: str | None = None
    power: str | None = None
    configuration: str | None = None
    specs: str | None = None
    price_rmb: float | None = None
    price_usd: float | None = None
    unit_price: float | None = None
    min_price: float | None = None
    validity_days: int | None = None
    remark: str | None = None


class QuoteLibraryOut(ORMModel):
    id: uuid.UUID
    external_model: str
    certificate_level: str
    external_id: str | None = None
    internal_model: str | None = None
    product_name: str | None = None
    category: str | None = None
    power: str | None = None
    configuration: str | None = None
    specs: str | None = None
    price_rmb: float | None = None
    price_usd: float | None = None
    unit_price: float | None = None
    min_price: float | None = None
    validity_days: int
    usage_count: int
    source_inquiry_no: str | None = None
    source_inquiry_id: uuid.UUID | None = None
    source_pricing_id: str | None = None
    remark: str | None = None
    creator: str | None = None
    sync_status: str
    last_sync_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


# ------------------------------------------------------------------ 问题反馈
class FeedbackCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    type: str = "bug"
    priority: str = "medium"
    module: str | None = None
    screenshots: list[str] | None = None
    source: str = "page"


class FeedbackUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    type: str | None = None
    priority: str | None = None
    module: str | None = None
    screenshots: list[str] | None = None


class FeedbackStatusIn(BaseModel):
    status: str = Field(min_length=1, max_length=20)
    content: str | None = None
    resolution: str | None = None


class FeedbackAssignIn(BaseModel):
    assignee: str | None = None
    assignee_id: uuid.UUID | None = None


class FeedbackCommentIn(BaseModel):
    content: str = Field(min_length=1)


class FeedbackFollowupOut(ORMModel):
    id: uuid.UUID
    feedback_id: uuid.UUID
    action: str
    content: str | None = None
    status_from: str | None = None
    status_to: str | None = None
    assignee: str | None = None
    operator: str | None = None
    operator_id: uuid.UUID | None = None
    created_at: datetime


class FeedbackOut(ORMModel):
    id: uuid.UUID
    feedback_no: str
    external_id: str | None = None
    title: str
    description: str | None = None
    type: str
    priority: str
    module: str | None = None
    submitter: str | None = None
    submitter_id: uuid.UUID | None = None
    assignee: str | None = None
    assignee_id: uuid.UUID | None = None
    screenshots: list[str] | None = None
    source: str
    status: str
    resolution: str | None = None
    resolved_at: datetime | None = None
    sync_status: str
    last_sync_at: datetime | None = None
    followups: list[FeedbackFollowupOut] = []
    followup_count: int = 0
    last_followup_at: datetime | None = None
    last_followup_by: str | None = None
    created_at: datetime
    updated_at: datetime
