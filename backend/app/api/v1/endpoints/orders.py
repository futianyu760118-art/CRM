"""M4/M5 订单管理接口（AC-M4）。"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select

from app.core import response as resp
from app.core.deps import DbSession, require_permission
from app.core.exceptions import ConflictError
from app.db.base import utcnow
from app.domain.state_machine import ORDER_STATUSES, allowed_order_transitions
from app.models.sales import SalesOrder
from app.models.user import User
from app.schemas.sales import SalesOrderCreate, SalesOrderOut, SalesOrderStatusIn, SalesOrderUpdate
from app.services import ebms_sync
from app.services.data_scope import apply_data_scope
from app.services.query import apply_sort, get_or_404, paginate, soft_delete

router = APIRouter(prefix="/orders", tags=["销售中心-订单"])


def _out(order: SalesOrder) -> dict[str, Any]:
    return SalesOrderOut.model_validate(order).model_dump(mode="json")


@router.get("", summary="订单列表")
async def list_orders(
    db: DbSession,
    current: User = Depends(require_permission("order:view")),
    keyword: str | None = Query(None, description="订单号/客户名称/产品名称/项目号"),
    status: str | None = None,
    risk_level: str | None = None,
    customer_code: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    sort: str = "created_at",
    order: str = Query("desc", pattern="^(asc|desc)$"),
) -> dict[str, Any]:
    stmt = select(SalesOrder).where(SalesOrder.deleted_at.is_(None))
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(
            or_(
                SalesOrder.order_no.ilike(like),
                SalesOrder.customer_name.ilike(like),
                SalesOrder.product_name.ilike(like),
                SalesOrder.project_no.ilike(like),
            )
        )
    if status:
        stmt = stmt.where(SalesOrder.status == status)
    if risk_level:
        stmt = stmt.where(SalesOrder.risk_level == risk_level)
    if customer_code:
        stmt = stmt.where(SalesOrder.customer_code == customer_code)
    stmt = await apply_data_scope(stmt, SalesOrder, current, db)
    stmt = apply_sort(stmt, SalesOrder, sort, order)
    rows, total = await paginate(db, stmt, page, page_size)
    return resp.page([_out(r) for r in rows], total, page, page_size)


@router.get("/stats", summary="订单统计（按状态/风险）")
async def order_stats(
    db: DbSession,
    _: User = Depends(require_permission("order:view")),
) -> dict[str, Any]:
    status_rows = (
        await db.execute(
            select(SalesOrder.status, func.count())
            .where(SalesOrder.deleted_at.is_(None))
            .group_by(SalesOrder.status)
        )
    ).all()
    risk_rows = (
        await db.execute(
            select(SalesOrder.risk_level, func.count())
            .where(SalesOrder.deleted_at.is_(None))
            .group_by(SalesOrder.risk_level)
        )
    ).all()
    return resp.ok(
        {
            "by_status": {s: int(c) for s, c in status_rows},
            "by_risk": {r: int(c) for r, c in risk_rows},
        }
    )


@router.post("", summary="新建订单", status_code=201)
async def create_order(
    payload: SalesOrderCreate,
    db: DbSession,
    current: User = Depends(require_permission("order:create")),
) -> dict[str, Any]:
    row = SalesOrder(
        **payload.model_dump(exclude_unset=True),
        owner_id=current.id,
        department_id=current.department_id,
    )
    db.add(row)
    await db.flush()
    await ebms_sync.emit_upsert(db, "Order", row)
    await db.commit()
    await db.refresh(row)
    return resp.ok(_out(row))


@router.get("/{order_id}", summary="订单详情")
async def get_order(
    order_id: uuid.UUID,
    db: DbSession,
    _: User = Depends(require_permission("order:view")),
) -> dict[str, Any]:
    row = await get_or_404(db, SalesOrder, order_id, "订单")
    return resp.ok(_out(row))


@router.put("/{order_id}", summary="更新订单")
async def update_order(
    order_id: uuid.UUID,
    payload: SalesOrderUpdate,
    db: DbSession,
    _: User = Depends(require_permission("order:update")),
) -> dict[str, Any]:
    row = await get_or_404(db, SalesOrder, order_id, "订单")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await db.flush()
    await ebms_sync.emit_upsert(db, "Order", row)
    await db.commit()
    await db.refresh(row)
    return resp.ok(_out(row))


@router.post("/{order_id}/status", summary="订单状态流转")
async def transition_order(
    order_id: uuid.UUID,
    payload: SalesOrderStatusIn,
    db: DbSession,
    current: User = Depends(require_permission("order:status")),
) -> dict[str, Any]:
    row = await get_or_404(db, SalesOrder, order_id, "订单")
    if payload.status not in ORDER_STATUSES:
        raise ConflictError(f"非法订单状态: {payload.status}")
    if payload.status != row.status and payload.status not in allowed_order_transitions(row.status):
        raise ConflictError(f"不允许从 {row.status} 流转到 {payload.status}")
    row.status = payload.status
    row.user_status_modified_at = utcnow()
    row.user_status_modified_by = current.id
    await db.flush()
    await ebms_sync.emit_upsert(db, "Order", row)
    await db.commit()
    await db.refresh(row)
    return resp.ok(_out(row))


@router.delete("/{order_id}", summary="删除订单（软删除）")
async def delete_order(
    order_id: uuid.UUID,
    db: DbSession,
    _: User = Depends(require_permission("order:delete")),
) -> dict[str, Any]:
    row = await get_or_404(db, SalesOrder, order_id, "订单")
    soft_delete(row)
    await db.flush()
    await ebms_sync.emit_delete(db, "Order", row)
    await db.commit()
    return resp.ok({"deleted": True})
