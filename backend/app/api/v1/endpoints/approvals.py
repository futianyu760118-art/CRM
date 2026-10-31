"""M4 审批接口：待办 / 详情 / 通过 / 驳回。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.core import response as resp
from app.core.deps import CurrentUser, DbSession, require_permission
from app.models.pricing import ApprovalInstance
from app.models.user import User
from app.schemas.pricing import ApprovalActionIn, ApprovalOut
from app.services import approval as approval_service
from app.services.query import get_or_404

router = APIRouter(prefix="/approvals", tags=["M4-审批"])


async def _to_out(db: DbSession, instance: ApprovalInstance) -> dict[str, Any]:
    data = ApprovalOut.model_validate(instance).model_dump(mode="json")
    data["logs"] = await approval_service.logs_of(db, instance.id)
    if instance.applicant_id:
        applicant = (await db.execute(select(User.name).where(User.id == instance.applicant_id))).scalar_one_or_none()
        data["applicant_name"] = applicant
    return data


@router.get("", summary="审批列表")
async def list_approvals(
    db: DbSession,
    current: CurrentUser,
    scope: str = Query("mine", description="mine=我的待办 / all=全部"),
    status: str | None = None,
    biz_type: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
) -> dict[str, Any]:
    if scope == "mine" and status is None:
        rows = await approval_service.pending_for(db, current)
        total = len(rows)
        start = (page - 1) * page_size
        rows = rows[start : start + page_size]
    else:
        stmt = select(ApprovalInstance).where(ApprovalInstance.deleted_at.is_(None))
        if status:
            stmt = stmt.where(ApprovalInstance.status == status)
        if biz_type:
            stmt = stmt.where(ApprovalInstance.biz_type == biz_type)
        stmt = stmt.order_by(ApprovalInstance.created_at.desc())
        total = len(list((await db.execute(stmt)).scalars().all()))
        rows = list((await db.execute(stmt.offset((page - 1) * page_size).limit(page_size))).scalars().all())

    items = [await _to_out(db, r) for r in rows]
    return resp.page(items, total, page, page_size)


@router.get("/count", summary="待审批数量")
async def pending_count(db: DbSession, current: CurrentUser) -> dict[str, Any]:
    rows = await approval_service.pending_for(db, current)
    return resp.ok({"pending": len(rows)})


@router.get("/{approval_id}", summary="审批详情")
async def get_approval(approval_id: uuid.UUID, db: DbSession, _: CurrentUser) -> dict[str, Any]:
    instance = await get_or_404(db, ApprovalInstance, approval_id, "审批实例")
    return resp.ok(await _to_out(db, instance))


@router.post("/{approval_id}/approve", summary="审批通过")
async def approve(
    approval_id: uuid.UUID,
    payload: ApprovalActionIn,
    db: DbSession,
    current: CurrentUser,
    _: User = Depends(require_permission("approval:approve")),
) -> dict[str, Any]:
    instance = await approval_service.act(
        db, instance_id=approval_id, user=current, approved=True, comment=payload.comment
    )
    await _sync_biz(db, instance)
    await db.commit()
    await db.refresh(instance)
    return resp.ok(await _to_out(db, instance))


@router.post("/{approval_id}/reject", summary="审批驳回")
async def reject(
    approval_id: uuid.UUID,
    payload: ApprovalActionIn,
    db: DbSession,
    current: CurrentUser,
    _: User = Depends(require_permission("approval:reject")),
) -> dict[str, Any]:
    instance = await approval_service.act(
        db, instance_id=approval_id, user=current, approved=False, comment=payload.comment
    )
    await _sync_biz(db, instance)
    await db.commit()
    await db.refresh(instance)
    return resp.ok(await _to_out(db, instance))


async def _sync_biz(db: DbSession, instance: ApprovalInstance) -> None:
    """审批结束后回写业务单据状态。"""
    from app.db.base import utcnow
    from app.models.pricing import PricingRecord, Quotation

    if instance.status == "PENDING":
        if instance.biz_type == "QUOTATION":
            quotation = (
                await db.execute(select(Quotation).where(Quotation.id == instance.biz_id))
            ).scalar_one_or_none()
            if quotation is not None:
                quotation.status = "PENDING_APPROVAL"
        return

    if instance.biz_type == "QUOTATION":
        quotation = (await db.execute(select(Quotation).where(Quotation.id == instance.biz_id))).scalar_one_or_none()
        if quotation is None:
            return
        if instance.status == "APPROVED":
            quotation.status = "APPROVED"
            quotation.approved_by = _last_operator(instance)
            quotation.approved_at = utcnow()
        else:
            quotation.status = "REJECTED"
    elif instance.biz_type == "PRICING":
        record = (
            await db.execute(select(PricingRecord).where(PricingRecord.id == instance.biz_id))
        ).scalar_one_or_none()
        if record is None:
            return
        if instance.status == "APPROVED":
            record.status = "APPROVED"
            record.approved_by = _last_operator(instance)
            record.approved_at = utcnow()
        else:
            record.status = "DRAFT"


def _last_operator(instance: ApprovalInstance) -> uuid.UUID | None:
    acted = [t for t in instance.tasks if t.acted_at is not None and t.approver_id]
    if not acted:
        return None
    acted.sort(key=lambda t: t.acted_at or datetime.min.replace(tzinfo=UTC))
    return acted[-1].approver_id
