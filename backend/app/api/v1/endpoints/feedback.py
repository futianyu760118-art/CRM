"""销售中心-问题反馈接口（AC-M6）。"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select

from app.core import response as resp
from app.core.deps import DbSession, require_permission
from app.core.exceptions import ConflictError
from app.db.base import utcnow
from app.domain.state_machine import FEEDBACK_STATUSES
from app.models.sales import Feedback, FeedbackFollowup
from app.models.user import User
from app.schemas.sales import (
    FeedbackAssignIn,
    FeedbackCommentIn,
    FeedbackCreate,
    FeedbackFollowupOut,
    FeedbackOut,
    FeedbackStatusIn,
    FeedbackUpdate,
)
from app.services import ebms_sync
from app.services.number_sequence import next_number
from app.services.query import apply_sort, get_or_404, paginate, soft_delete

router = APIRouter(prefix="/feedback", tags=["销售中心-问题反馈"])


def _enrich(feedback: Feedback) -> dict[str, Any]:
    followups = sorted(feedback.followups or [], key=lambda f: f.created_at)
    data = FeedbackOut.model_validate(feedback).model_dump(mode="json")
    data["followups"] = [
        FeedbackFollowupOut.model_validate(f).model_dump(mode="json") for f in followups
    ]
    data["followup_count"] = len(followups)
    if followups:
        data["last_followup_at"] = followups[-1].created_at.isoformat() if followups[-1].created_at else None
        data["last_followup_by"] = followups[-1].operator
    return data


@router.get("", summary="问题反馈列表")
async def list_feedback(
    db: DbSession,
    _: User = Depends(require_permission("feedback:view")),
    keyword: str | None = Query(None, description="反馈号/标题"),
    type: str | None = None,
    priority: str | None = None,
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    sort: str = "created_at",
    order: str = Query("desc", pattern="^(asc|desc)$"),
) -> dict[str, Any]:
    stmt = select(Feedback).where(Feedback.deleted_at.is_(None))
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(or_(Feedback.feedback_no.ilike(like), Feedback.title.ilike(like)))
    if type:
        stmt = stmt.where(Feedback.type == type)
    if priority:
        stmt = stmt.where(Feedback.priority == priority)
    if status:
        stmt = stmt.where(Feedback.status == status)
    stmt = apply_sort(stmt, Feedback, sort, order)
    rows, total = await paginate(db, stmt, page, page_size)
    return resp.page([_enrich(r) for r in rows], total, page, page_size)


@router.get("/stats", summary="反馈统计（按类型/优先级/状态 + 平均处理时长）")
async def feedback_stats(
    db: DbSession,
    _: User = Depends(require_permission("feedback:view")),
) -> dict[str, Any]:
    async def _group(column: Any) -> dict[str, int]:
        rows = (
            await db.execute(select(column, func.count()).where(Feedback.deleted_at.is_(None)).group_by(column))
        ).all()
        return {str(k): int(c) for k, c in rows}

    total = int((await db.execute(select(func.count()).where(Feedback.deleted_at.is_(None)))).scalar_one())

    # 平均处理时长（小时）：创建到 resolved/closed，保留 1 位小数；无已处理样本返回 0（除零保护）
    handle_rows = (
        await db.execute(
            select(Feedback.created_at, Feedback.resolved_at).where(
                Feedback.deleted_at.is_(None), Feedback.resolved_at.isnot(None)
            )
        )
    ).all()
    handle_seconds = 0.0
    handle_count = 0
    for created_at, resolved_at in handle_rows:
        if created_at is not None and resolved_at is not None and resolved_at >= created_at:
            handle_seconds += (resolved_at - created_at).total_seconds()
            handle_count += 1
    avg_handle_hours = round(handle_seconds / handle_count / 3600, 1) if handle_count else 0.0

    return resp.ok(
        {
            "total": total,
            "avg_handle_hours": avg_handle_hours,
            "by_type": await _group(Feedback.type),
            "by_priority": await _group(Feedback.priority),
            "by_status": await _group(Feedback.status),
        }
    )


@router.post("", summary="新建问题反馈", status_code=201)
async def create_feedback(
    payload: FeedbackCreate,
    db: DbSession,
    current: User = Depends(require_permission("feedback:create")),
) -> dict[str, Any]:
    feedback_no = await next_number("feedback")
    row = Feedback(
        **payload.model_dump(exclude_unset=True),
        feedback_no=feedback_no,
        submitter=current.name,
        submitter_id=current.id,
    )
    db.add(row)
    await db.flush()
    db.add(
        FeedbackFollowup(
            feedback_id=row.id,
            action="submit",
            content=payload.description,
            operator=current.name,
            operator_id=current.id,
        )
    )
    await db.flush()
    await ebms_sync.emit_upsert(db, "Feedback", row)
    await db.commit()
    await db.refresh(row)
    return resp.ok(_enrich(row))


@router.get("/{feedback_id}", summary="反馈详情")
async def get_feedback(
    feedback_id: uuid.UUID,
    db: DbSession,
    _: User = Depends(require_permission("feedback:view")),
) -> dict[str, Any]:
    row = await get_or_404(db, Feedback, feedback_id, "问题反馈")
    return resp.ok(_enrich(row))


@router.put("/{feedback_id}", summary="更新反馈")
async def update_feedback(
    feedback_id: uuid.UUID,
    payload: FeedbackUpdate,
    db: DbSession,
    _: User = Depends(require_permission("feedback:handle")),
) -> dict[str, Any]:
    row = await get_or_404(db, Feedback, feedback_id, "问题反馈")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await db.flush()
    await ebms_sync.emit_upsert(db, "Feedback", row)
    await db.commit()
    await db.refresh(row)
    return resp.ok(_enrich(row))


@router.post("/{feedback_id}/status", summary="反馈状态流转")
async def transition_feedback(
    feedback_id: uuid.UUID,
    payload: FeedbackStatusIn,
    db: DbSession,
    current: User = Depends(require_permission("feedback:handle")),
) -> dict[str, Any]:
    row = await get_or_404(db, Feedback, feedback_id, "问题反馈")
    if payload.status not in FEEDBACK_STATUSES:
        raise ConflictError(f"非法反馈状态: {payload.status}")
    if payload.status != row.status:
        idx, target = FEEDBACK_STATUSES.index(row.status), FEEDBACK_STATUSES.index(payload.status)
        if target != idx + 1:
            raise ConflictError(f"不允许从 {row.status} 跳转到 {payload.status}")
    old_status = row.status
    row.status = payload.status
    if payload.status == "resolved":
        row.resolved_at = utcnow()
    if payload.resolution is not None:
        row.resolution = payload.resolution
    db.add(
        FeedbackFollowup(
            feedback_id=row.id,
            action="status",
            content=payload.content or payload.resolution,
            status_from=old_status,
            status_to=payload.status,
            operator=current.name,
            operator_id=current.id,
        )
    )
    await db.flush()
    await ebms_sync.emit_upsert(db, "Feedback", row)
    await db.commit()
    await db.refresh(row)
    return resp.ok(_enrich(row))


@router.post("/{feedback_id}/assign", summary="反馈指派")
async def assign_feedback(
    feedback_id: uuid.UUID,
    payload: FeedbackAssignIn,
    db: DbSession,
    current: User = Depends(require_permission("feedback:handle")),
) -> dict[str, Any]:
    row = await get_or_404(db, Feedback, feedback_id, "问题反馈")
    if payload.assignee is not None:
        row.assignee = payload.assignee
    if payload.assignee_id is not None:
        row.assignee_id = payload.assignee_id
    db.add(
        FeedbackFollowup(
            feedback_id=row.id,
            action="assign",
            content=f"指派给 {payload.assignee}",
            assignee=payload.assignee,
            operator=current.name,
            operator_id=current.id,
        )
    )
    await db.flush()
    await ebms_sync.emit_upsert(db, "Feedback", row)
    await db.commit()
    await db.refresh(row)
    return resp.ok(_enrich(row))


@router.post("/{feedback_id}/comments", summary="反馈跟进/评论", status_code=201)
async def comment_feedback(
    feedback_id: uuid.UUID,
    payload: FeedbackCommentIn,
    db: DbSession,
    current: User = Depends(require_permission("feedback:handle")),
) -> dict[str, Any]:
    row = await get_or_404(db, Feedback, feedback_id, "问题反馈")
    db.add(
        FeedbackFollowup(
            feedback_id=row.id,
            action="comment",
            content=payload.content,
            operator=current.name,
            operator_id=current.id,
        )
    )
    await db.commit()
    await db.refresh(row)
    return resp.ok(_enrich(row))


@router.delete("/{feedback_id}", summary="删除反馈（软删除，级联删跟进）")
async def delete_feedback(
    feedback_id: uuid.UUID,
    db: DbSession,
    _: User = Depends(require_permission("feedback:delete")),
) -> dict[str, Any]:
    row = await get_or_404(db, Feedback, feedback_id, "问题反馈")
    soft_delete(row)
    # 级联软删跟进记录（AC-M6.6：不残留 deleted_at IS NULL 的孤儿跟进）
    followups = (
        (
            await db.execute(
                select(FeedbackFollowup).where(
                    FeedbackFollowup.feedback_id == row.id, FeedbackFollowup.deleted_at.is_(None)
                )
            )
        )
        .scalars()
        .all()
    )
    for followup in followups:
        soft_delete(followup)
    await db.flush()
    await ebms_sync.emit_delete(db, "Feedback", row)
    await db.commit()
    return resp.ok({"deleted": True})
