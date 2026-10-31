"""销售中心-样品管理接口（PAND-316 SAMP-01~04）。"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select

from app.core import response as resp
from app.core.deps import DbSession, require_permission
from app.core.error_codes import ErrCode
from app.core.exceptions import ApiError
from app.domain.state_machine import (
    SAMPLE_STATUS_LABELS,
    SAMPLE_STATUSES,
    SAMPLE_TERMINAL_STATUS,
)
from app.models.sales import Sample
from app.models.user import User
from app.schemas.sales import SampleCreate, SampleOut, SampleStatusIn, SampleUpdate
from app.services import ebms_sync, product_assets
from app.services.data_scope import apply_data_scope
from app.services.number_sequence import next_number
from app.services.query import apply_sort, get_or_404, paginate, soft_delete

router = APIRouter(prefix="/samples", tags=["销售中心-样品"])

STATUS_LABEL_TEXT = "、".join(SAMPLE_STATUS_LABELS[s] for s in SAMPLE_STATUSES)
SEND_FIELDS = ("courier", "tracking_no", "send_date")
FEEDBACK_FIELDS = ("feedback", "feedback_date")


def _bad(message: str) -> ApiError:
    return ApiError(ErrCode.VALIDATION_ERROR, message, http_status=400)


def _overdue_days(sample: Sample) -> int | None:
    if sample.plan_date and sample.status != SAMPLE_TERMINAL_STATUS and sample.plan_date < date.today():
        return (date.today() - sample.plan_date).days
    return None


def _out(sample: Sample) -> dict[str, Any]:
    data = SampleOut.model_validate(sample).model_dump(mode="json")
    data["overdue_days"] = _overdue_days(sample)
    return data


async def _tracking_owner(db: DbSession, tracking_no: str, exclude_id: uuid.UUID | None = None) -> Sample | None:
    stmt = select(Sample).where(Sample.tracking_no == tracking_no, Sample.deleted_at.is_(None))
    if exclude_id is not None:
        stmt = stmt.where(Sample.id != exclude_id)
    return (await db.execute(stmt.limit(1))).scalar_one_or_none()


async def _ensure_tracking_free(db: DbSession, tracking_no: str | None, exclude_id: uuid.UUID | None = None) -> None:
    if not tracking_no:
        return
    other = await _tracking_owner(db, tracking_no, exclude_id)
    if other is not None:
        raise ApiError(
            ErrCode.CONFLICT,
            f"快递单号：已被样品 {other.sample_no} 使用",
            http_status=409,
        )


def _check_plan_date(plan_date: date | None, floor: date) -> date:
    if plan_date is None:
        return product_assets.default_plan_date(floor)
    if plan_date < floor:
        raise _bad("计划完成日期：不得早于创建日期")
    return plan_date


@router.get("", summary="样品列表")
async def list_samples(
    db: DbSession,
    current: User = Depends(require_permission("sample:view")),
    keyword: str | None = Query(None, description="样品号/客户/产品型号/产品名称/询价号"),
    status: str | None = None,
    owner_id: uuid.UUID | None = None,
    plan_date_from: date | None = None,
    plan_date_to: date | None = None,
    overdue: bool = False,
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
                Sample.product_model.ilike(like),
                Sample.inquiry_no.ilike(like),
            )
        )
    if status:
        stmt = stmt.where(Sample.status == status)
    if owner_id:
        stmt = stmt.where(Sample.owner_id == owner_id)
    if plan_date_from:
        stmt = stmt.where(Sample.plan_date >= plan_date_from)
    if plan_date_to:
        stmt = stmt.where(Sample.plan_date <= plan_date_to)
    if overdue:
        stmt = stmt.where(
            Sample.plan_date.is_not(None),
            Sample.plan_date < date.today(),
            Sample.status != SAMPLE_TERMINAL_STATUS,
        )
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
    overdue_total = (
        await db.execute(
            select(func.count())
            .select_from(Sample)
            .where(
                Sample.deleted_at.is_(None),
                Sample.plan_date.is_not(None),
                Sample.plan_date < date.today(),
                Sample.status != SAMPLE_TERMINAL_STATUS,
            )
        )
    ).scalar_one()
    return resp.ok({"by_status": {s: int(c) for s, c in rows}, "overdue": int(overdue_total)})


@router.post("", summary="新建样品", status_code=201)
async def create_sample(
    payload: SampleCreate,
    db: DbSession,
    current: User = Depends(require_permission("sample:create")),
) -> dict[str, Any]:
    data = payload.model_dump(exclude_unset=True)
    today = date.today()
    data["plan_date"] = _check_plan_date(data.get("plan_date"), today)
    await _ensure_tracking_free(db, data.get("tracking_no"))
    if not data.get("sample_no"):
        data["sample_no"] = await next_number("sample")
    owner_id = data.pop("owner_id", None) or current.id
    row = Sample(**data, owner_id=owner_id, department_id=current.department_id)
    db.add(row)
    await db.flush()
    await ebms_sync.emit_upsert(db, "Sample", row)
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
    data = payload.model_dump(exclude_unset=True)
    if "plan_date" in data:
        data["plan_date"] = _check_plan_date(data["plan_date"], row.created_at.date())
    if "tracking_no" in data:
        await _ensure_tracking_free(db, data["tracking_no"], exclude_id=row.id)
    for key, value in data.items():
        setattr(row, key, value)
    await db.flush()
    await ebms_sync.emit_upsert(db, "Sample", row)
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
    target = payload.status
    if target not in SAMPLE_STATUSES:
        raise _bad(f"样品状态：仅可选 {STATUS_LABEL_TEXT}")

    current_label = SAMPLE_STATUS_LABELS.get(row.status, row.status)
    if target != row.status:
        idx = SAMPLE_STATUSES.index(row.status)
        if idx == len(SAMPLE_STATUSES) - 1:
            raise _bad(f"样品已处于【{current_label}】终态，不能继续流转")
        nxt = SAMPLE_STATUSES[idx + 1]
        if target != nxt:
            raise _bad(
                f"不能从【{current_label}】直接流转到【{SAMPLE_STATUS_LABELS[target]}】，"
                f"下一状态为【{SAMPLE_STATUS_LABELS[nxt]}】"
            )

    extra = payload.model_dump(exclude_unset=True)
    extras = {k: v for k, v in extra.items() if k != "status" and v is not None}

    if target == "sent" and target != row.status:
        missing = [
            label
            for field, label in (("courier", "快递公司"), ("tracking_no", "快递单号"), ("send_date", "寄出日期"))
            if not (extras.get(field) or getattr(row, field))
        ]
        if missing:
            raise _bad(f"流转至【已寄出】失败：缺少必填项——{'、'.join(missing)}")

    if target == "feedback" and target != row.status:
        missing = [
            label
            for field, label in (("feedback", "客户反馈"), ("feedback_date", "反馈日期"))
            if not (extras.get(field) or getattr(row, field))
        ]
        if missing:
            raise _bad(f"流转至【客户反馈】失败：缺少必填项——{'、'.join(missing)}")

    if "tracking_no" in extras:
        await _ensure_tracking_free(db, extras["tracking_no"], exclude_id=row.id)

    for field in (*SEND_FIELDS, *FEEDBACK_FIELDS):
        if extras.get(field) is not None:
            setattr(row, field, extras[field])
    row.status = target

    await db.flush()
    await ebms_sync.emit_upsert(db, "Sample", row)
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
    await ebms_sync.emit_delete(db, "Sample", row)
    await db.commit()
    return resp.ok({"deleted": True})
