"""审计日志查询接口。"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.core import response as resp
from app.core.deps import DbSession, require_permission
from app.models.audit import AuditLog
from app.models.user import User
from app.schemas.system import AuditLogOut

router = APIRouter(prefix="/audit-logs", tags=["系统-审计日志"])


@router.get("", summary="审计日志列表")
async def list_audit_logs(
    db: DbSession,
    _: User = Depends(require_permission("audit:view")),
    username: str | None = None,
    module: str | None = None,
    action: str | None = None,
    success: bool | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    stmt = select(AuditLog).where(AuditLog.deleted_at.is_(None))
    if username:
        stmt = stmt.where(AuditLog.username.ilike(f"%{username}%"))
    if module:
        stmt = stmt.where(AuditLog.module == module)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if success is not None:
        stmt = stmt.where(AuditLog.success.is_(success))
    if start:
        stmt = stmt.where(AuditLog.created_at >= start)
    if end:
        stmt = stmt.where(AuditLog.created_at <= end)

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    stmt = stmt.order_by(AuditLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(stmt)).scalars().all()
    return resp.page(
        [AuditLogOut.model_validate(i).model_dump(mode="json") for i in items],
        total,
        page,
        page_size,
    )
