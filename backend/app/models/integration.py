"""M6 K3 集成 数据模型（中间表 + 本地消息表 + 集成日志）。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class IntegrationLog(BaseModel):
    """集成日志（幂等、重试、对账依据）。"""

    __tablename__ = "integration_log"

    system: Mapped[str] = mapped_column(String(20), default="K3", nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    request_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    business_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    request_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    response_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False, index=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retry: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IntegrationOutbox(BaseModel):
    """本地消息表：CRM 事务内写入，Worker 异步投递。"""

    __tablename__ = "integration_outbox"

    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    biz_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    # 与 integration_log.idempotency_key 对齐，保证 Outbox 与日志可精确定位、可对账
    idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    biz_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False, index=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class K3CustomerStaging(BaseModel):
    """K3 客户中间表。"""

    __tablename__ = "k3_customer_staging"

    batch_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    crm_customer_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    customer_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    customer_name: Mapped[str] = mapped_column(String(200), nullable=False)
    country: Mapped[str | None] = mapped_column(String(50), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    sync_status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False, index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class K3OrderStaging(BaseModel):
    """K3 订单中间表。"""

    __tablename__ = "k3_order_staging"

    batch_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    crm_quotation_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    order_no: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    customer_code: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    total_amount: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    sync_status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False, index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
