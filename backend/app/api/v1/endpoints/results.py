"""经营结果与验证接口（AEOS Verification，F5；权限 View/Operation/Verify 相互独立）。"""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.core import response as resp
from app.core.deps import DbSession, require_permission
from app.models.sales import SalesResult
from app.models.user import User
from app.schemas.result import VerifyIn
from app.services import verify as verify_service
from app.services.data_scope import apply_data_scope
from app.services.query import apply_sort, paginate

router = APIRouter(prefix="/results", tags=["销售中心-经营结果"])


@router.get("", summary="经营结果列表（含 submitted/verified 状态筛选）")
async def list_results(
    db: DbSession,
    current: User = Depends(require_permission("result:view")),
    status: str | None = Query(None, description="submitted / verified"),
    metric_code: str | None = None,
    period_start: date | None = None,
    period_end: date | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    sort: str = "created_at",
    order: str = Query("desc", pattern="^(asc|desc)$"),
) -> dict[str, Any]:
    stmt = select(SalesResult).where(SalesResult.deleted_at.is_(None))
    if status:
        stmt = stmt.where(SalesResult.status == status)
    if metric_code:
        stmt = stmt.where(SalesResult.metric_code == metric_code)
    if period_start:
        stmt = stmt.where(SalesResult.period_end >= period_start)
    if period_end:
        stmt = stmt.where(SalesResult.period_start <= period_end)
    stmt = await apply_data_scope(stmt, SalesResult, current, db)
    stmt = apply_sort(stmt, SalesResult, sort, order)
    rows, total = await paginate(db, stmt, page, page_size)
    return resp.page([verify_service.result_out(r) for r in rows], total, page, page_size)


@router.get("/{result_id}", summary="经营结果详情")
async def get_result(
    result_id: str,
    db: DbSession,
    _: User = Depends(require_permission("result:view")),
) -> dict[str, Any]:
    row = await verify_service.get_result(db, result_id)
    verification = await verify_service.latest_verification(db, row)
    return resp.ok(
        {
            "result": verify_service.result_out(row),
            "verification": verify_service.verification_out(verification) if verification else None,
        }
    )


@router.get("/{result_id}/verifications", summary="结果验证记录")
async def list_verifications(
    result_id: str,
    db: DbSession,
    _: User = Depends(require_permission("result:view")),
) -> dict[str, Any]:
    rows = await verify_service.list_verifications(db, result_id)
    return resp.ok([verify_service.verification_out(r) for r in rows])


@router.post("/{result_id}/verify", summary="验证结果（verify，幂等）")
async def verify_result(
    result_id: str,
    payload: VerifyIn,
    db: DbSession,
    current: User = Depends(require_permission("result:verify")),
) -> dict[str, Any]:
    outcome = await verify_service.verify_result(
        db,
        subject_id=result_id,
        verifier=current.id,
        status=payload.status,
        reason=payload.reason,
        evidence_refs=payload.evidence_refs,
        comment=payload.comment,
    )
    await db.commit()
    return resp.ok(outcome)
