"""M6 集成 Schema。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.schemas.common import ORMModel


class IntegrationLogOut(ORMModel):
    id: uuid.UUID
    system: str
    action: str
    request_id: str | None = None
    idempotency_key: str | None = None
    business_id: str | None = None
    request_payload: dict[str, Any] | None = None
    response_payload: dict[str, Any] | None = None
    status: str
    retry_count: int
    max_retry: int
    next_retry_at: datetime | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime


class SyncResultOut(BaseModel):
    batch_id: str
    total: int
    success: int
    failed: int
    skipped: int
    log_ids: list[uuid.UUID]


class StagingOut(ORMModel):
    id: uuid.UUID
    batch_id: str
    sync_status: str
    error_message: str | None = None
    retry_count: int
    processed_at: datetime | None = None
    created_at: datetime


class K3CustomerStagingOut(StagingOut):
    crm_customer_id: uuid.UUID
    customer_code: str
    customer_name: str
    country: str | None = None
    currency: str | None = None


class K3OrderStagingOut(StagingOut):
    crm_quotation_id: uuid.UUID
    order_no: str
    customer_code: str | None = None
    total_amount: float | None = None
    currency: str | None = None


class ReconcileOut(BaseModel):
    checked_at: datetime
    crm_customers: int
    k3_customers: int
    crm_orders: int
    k3_orders: int
    customer_diff: int
    order_diff: int
    consistent: bool
