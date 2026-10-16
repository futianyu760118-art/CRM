"""EBMS 集成（AEOS 契约投递）Schema。"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class ContractValidateIn(BaseModel):
    """联调：待校验的 AEOS 契约（原样提交）。"""

    contract: dict[str, Any] = Field(description="AEOS.Result.V1 / AEOS.Exception.V1 报文")


class ContractValidateOut(BaseModel):
    valid: bool
    contract_version: str | None = None
    contract_id: str | None = None
    normalized: dict[str, Any] | None = None
    unknown_fields: list[str] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)


class PilotResultIn(BaseModel):
    period_start: date
    period_end: date
    metric_code: str = "order_amount"
    currency: str = "RMB"
    limit: int = Field(default=500, ge=1, le=5000)
    deliver: bool = Field(default=True, description="入队后立即投递（联调一把过）")


class PilotExceptionIn(BaseModel):
    sla_days: int = Field(default=30, ge=0, le=3650)
    as_of: datetime | None = None
    limit: int = Field(default=200, ge=1, le=5000)
    deliver: bool = Field(default=True, description="入队后立即投递（联调一把过）")


class DeliverOut(BaseModel):
    mode: str
    picked: int
    delivered: int
    skipped: int
    failed: int
    dead_letter: int


class DeliverIn(BaseModel):
    limit: int = Field(default=50, ge=1, le=1000)


class ReconcileSideOut(BaseModel):
    produced: int
    delivered: int
    pending: int
    failed: int


class EbmsReconcileOut(BaseModel):
    checked_at: str
    mode: str
    result: ReconcileSideOut
    exception: ReconcileSideOut
    dead_letter: int
    consistent: bool


class RetryOut(BaseModel):
    log_id: uuid.UUID
    status: str
    message: str
    retry_count: int | None = None
    mode: str | None = None
