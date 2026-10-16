"""销售中心-样品管理接口（AC-M5）。"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select

from app.core import response as resp
from app.core.deps import DbSession, require_permission
from app.core.exceptions import ConflictError
from app.domain.state_machine import SAMPLE_STATUSES
from app.models.sales import Sample
from app.models.user import User
from app.schemas.sales import SampleCreate, SampleOut, SampleStatusIn, SampleUpdate
from app.services import ebms_sync
from app.services.data_scope import apply_data_scope
from app.services.number_sequence import next_number
from app.services.query import apply_sort, get_or_404, paginate, soft_delete

router = APIRouter(prefix="/samples", tags=["销售中心-样品"])


def _out(sample: Sample) -> dict[str, Any]:
    return SampleOut.model_validate(sample).model_dump(mode="json")


@router.get("", summary="样品列表")
async def list_samples(
    db: DbSession,
    current: User = Depends(require_permission("sample:view")),
    keyword: str | None = Query(None, description="样品号/客户/产品/询价号"),
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    sort: str = "created_at",
    order: str = Query("desc", pattern="^(asc|desc)$"),
) -> dict[str, Any]:
    stmt = select(Sample).where(Sample.deleted_at.is_(None))
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(
            or_(
                Sample.sample_no.ilike(like),
                Sample.customer_name.ilike(like),
                Sample.product_name.ilike(like),
                Sample.inquiry_no.ilike(like),
            )
        )
    if status:
        stmt = stmt.where(Sample.status == status)
    stmt = await apply_data_scope(stmt, Sample, current, db)
    stmt = apply_sort(stmt, Sample, sort, order)
    rows, total = await paginate(db, stmt, page, page_size)
    return resp.page([_out(r) for r in rows], total, page, page_size)


@router.get("/stats", summary="样品统计（按状态）")
async def sample_stats(
    db: DbSession,
    _: User = Depends(require_permission("sample:view")),
) -> dict[str, Any]:
    rows = (
        await db.execute(
            select(Sample.status, func.count()).where(Sample.deleted_at.is_(None)).group_by(Sample.status)
        )
    ).all()
    return resp.ok({"by_status": {s: int(c) for s, c in rows}})


@router.post("", summary="新建样品", status_code=201)
async def create_sample(
    payload: SampleCreate,
    db: DbSession,
    current: User = Depends(require_permission("sample:create")),
) -> dict[str, Any]:
    data = payload.model_dump(exclude_unset=True)
    if not data.get("sample_no"):
        data["sample_no"] = await next_number("sample")
    row = Sample(**data, owner_id=current.id, department_id=current.department_id)
    db.add(row)
    await db.flush()
    await ebms_sync.emit_upsert(db, "sample", row)
    await db.commit()
    await db.refresh(row)
    return resp.ok(_out(row))


@router.get("/{sample_id}", summary="样品详情")
async def get_sample(
    sample_id: uuid.UUID,
    db: DbSession,
    _: User = Depends(require_permission("sample:view")),
) -> dict[str, Any]:
    row = await get_or_404(db, Sample, sample_id, "样品")
    return resp.ok(_out(row))


@router.put("/{sample_id}", summary="更新样品")
async def update_sample(
    sample_id: uuid.UUID,
    payload: SampleUpdate,
    db: DbSession,
    _: User = Depends(require_permission("sample:update")),
) -> dict[str, Any]:
    row = await get_or_404(db, Sample, sample_id, "样品")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await db.flush()
    await ebms_sync.emit_upsert(db, "sample", row)
    await db.commit()
    await db.refresh(row)
    return resp.ok(_out(row))


@router.post("/{sample_id}/status", summary="样品状态流转")
async def transition_sample(
    sample_id: uuid.UUID,
    payload: SampleStatusIn,
    db: DbSession,
    _: User = Depends(require_permission("sample:status")),
) -> dict[str, Any]:
    row = await get_or_404(db, Sample, sample_id, "样品")
    if payload.status not in SAMPLE_STATUSES:
        raise ConflictError(f"非法样品状态: {payload.status}")
    if payload.status != row.status:
        idx, target = SAMPLE_STATUSES.index(row.status), SAMPLE_STATUSES.index(payload.status)
        if target != idx + 1:
            raise ConflictError(f"不允许从 {row.status} 跳转到 {payload.status}")
    row.status = payload.status
    await db.flush()
    await ebms_sync.emit_upsert(db, "sample", row)
    await db.commit()
    await db.refresh(row)
    return resp.ok(_out(row))


@router.delete("/{sample_id}", summary="删除样品（软删除）")
async def delete_sample(
    sample_id: uuid.UUID,
    db: DbSession,
    _: User = Depends(require_permission("sample:delete")),
) -> dict[str, Any]:
    row = await get_or_404(db, Sample, sample_id, "样品")
    soft_delete(row)
    await db.flush()
    await ebms_sync.emit_delete(db, "sample", row)
    await db.commit()
    return resp.ok({"deleted": True})
