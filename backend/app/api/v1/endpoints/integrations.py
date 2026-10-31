"""M6 K3 集成接口：客户/订单同步、日志、重试、对账、中间表查询。"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.core import response as resp
from app.core.deps import CurrentUser, DbSession, require_permission
from app.models.integration import (
    IntegrationLog,
    IntegrationOutbox,
    K3CustomerStaging,
    K3OrderStaging,
)
from app.models.user import User
from app.schemas.integration import (
    IntegrationLogOut,
    K3CustomerStagingOut,
    K3OrderStagingOut,
    ReconcileOut,
    SyncResultOut,
)
from app.services import k3
from app.services.query import apply_sort, paginate

router = APIRouter(prefix="/integrations/k3", tags=["M6-K3集成"])


class SyncIn(BaseModel):
    ids: list[uuid.UUID] | None = None
    limit: int = 50


@router.post("/customer/sync", summary="客户同步到 K3 中间表")
async def sync_customers(
    payload: SyncIn,
    db: DbSession,
    current: CurrentUser,
    _: User = Depends(require_permission("integration:view")),
) -> dict[str, Any]:
    result = await k3.sync_customers(db, company_ids=payload.ids, limit=payload.limit, user_id=current.id)
    await db.commit()
    return resp.ok(SyncResultOut(**result).model_dump(mode="json"))


@router.post("/order/sync", summary="订单同步到 K3 中间表")
async def sync_orders(
    payload: SyncIn,
    db: DbSession,
    _: User = Depends(require_permission("integration:view")),
) -> dict[str, Any]:
    result = await k3.sync_orders(db, quotation_ids=payload.ids, limit=payload.limit)
    await db.commit()
    return resp.ok(SyncResultOut(**result).model_dump(mode="json"))


@router.get("/logs", summary="集成日志")
async def list_logs(
    db: DbSession,
    _: User = Depends(require_permission("integration:view")),
    status: str | None = None,
    action: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    sort: str = "created_at",
    order: str = Query("desc", pattern="^(asc|desc)$"),
) -> dict[str, Any]:
    stmt = select(IntegrationLog).where(IntegrationLog.deleted_at.is_(None))
    if status:
        stmt = stmt.where(IntegrationLog.status == status)
    if action:
        stmt = stmt.where(IntegrationLog.action == action)
    stmt = apply_sort(stmt, IntegrationLog, sort, order)
    rows, total = await paginate(db, stmt, page, page_size)
    items = [IntegrationLogOut.model_validate(r).model_dump(mode="json") for r in rows]
    return resp.page(items, total, page, page_size)


@router.post("/retry/{log_id}", summary="重试同步")
async def retry(
    log_id: uuid.UUID,
    db: DbSession,
    _: User = Depends(require_permission("integration:view")),
) -> dict[str, Any]:
    result = await k3.retry(db, log_id)
    await db.commit()
    return resp.ok(result)


@router.post("/reconcile", summary="每日对账")
async def reconcile(
    db: DbSession,
    _: User = Depends(require_permission("integration:view")),
) -> dict[str, Any]:
    result = await k3.reconcile(db)
    return resp.ok(ReconcileOut(**result).model_dump(mode="json"))


@router.get("/customer-staging", summary="K3 客户中间表")
async def customer_staging(
    db: DbSession,
    _: User = Depends(require_permission("integration:view")),
    sync_status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
) -> dict[str, Any]:
    stmt = select(K3CustomerStaging).where(K3CustomerStaging.deleted_at.is_(None))
    if sync_status:
        stmt = stmt.where(K3CustomerStaging.sync_status == sync_status)
    stmt = stmt.order_by(K3CustomerStaging.created_at.desc())
    rows, total = await paginate(db, stmt, page, page_size)
    items = [K3CustomerStagingOut.model_validate(r).model_dump(mode="json") for r in rows]
    return resp.page(items, total, page, page_size)


@router.get("/order-staging", summary="K3 订单中间表")
async def order_staging(
    db: DbSession,
    _: User = Depends(require_permission("integration:view")),
    sync_status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
) -> dict[str, Any]:
    stmt = select(K3OrderStaging).where(K3OrderStaging.deleted_at.is_(None))
    if sync_status:
        stmt = stmt.where(K3OrderStaging.sync_status == sync_status)
    stmt = stmt.order_by(K3OrderStaging.created_at.desc())
    rows, total = await paginate(db, stmt, page, page_size)
    items = [K3OrderStagingOut.model_validate(r).model_dump(mode="json") for r in rows]
    return resp.page(items, total, page, page_size)


@router.get("/outbox", summary="本地消息表（Outbox）")
async def outbox(
    db: DbSession,
    _: User = Depends(require_permission("integration:view")),
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
) -> dict[str, Any]:
    stmt = select(IntegrationOutbox).where(IntegrationOutbox.deleted_at.is_(None))
    if status:
        stmt = stmt.where(IntegrationOutbox.status == status)
    stmt = stmt.order_by(IntegrationOutbox.created_at.desc())
    rows, total = await paginate(db, stmt, page, page_size)
    items = [
        {
            "id": str(r.id),
            "event_type": r.event_type,
            "biz_type": r.biz_type,
            "biz_id": str(r.biz_id),
            "status": r.status,
            "retry_count": r.retry_count,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "processed_at": r.processed_at.isoformat() if r.processed_at else None,
        }
        for r in rows
    ]
    return resp.page(items, total, page, page_size)
