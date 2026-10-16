"""销售中心 6 模块 Schema（订单 / 样品 / 报价库 / 问题反馈）。"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator

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
class SampleCreate(BaseModel):
    sample_no: str | None = None
    customer_name: str = Field(min_length=1, max_length=200)
    inquiry_no: str | None = None
    product_name: str | None = None
    product_code: str | None = None
    quantity: float = 0
    sample_type: str = "常规"
    send_date: date | None = None
    confirm_date: date | None = None
    remark: str | None = None
    owner_id: uuid.UUID | None = None


class SampleUpdate(BaseModel):
    customer_name: str | None = None
    inquiry_no: str | None = None
    product_name: str | None = None
    product_code: str | None = None
    quantity: float | None = None
    sample_type: str | None = None
    send_date: date | None = None
    confirm_date: date | None = None
    remark: str | None = None
    owner_id: uuid.UUID | None = None


class SampleStatusIn(BaseModel):
    status: str = Field(min_length=1, max_length=20)


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
    quantity: float
    sample_type: str
    status: str
    send_date: date | None = None
    confirm_date: date | None = None
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
