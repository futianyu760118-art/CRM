"""审批流引擎（M4）。

流程定义：按业务类型与金额决定审批步骤（角色链）。
- 报价审批：金额 <= 阈值 → [manager]；> 阈值 → [manager, boss]
- 核价审批：> 阈值 → [manager, boss]；否则 [manager]
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.db.base import utcnow
from app.models.pricing import ApprovalInstance, ApprovalLog, ApprovalTask
from app.models.user import User

AMOUNT_THRESHOLD = 50000.0

FLOWS: dict[str, list[str]] = {
    "QUOTATION": ["manager", "boss"],
    "PRICING": ["manager", "boss"],
}


def steps_for(biz_type: str, amount: float | None) -> list[str]:
    steps = FLOWS.get(biz_type, ["manager"])
    if amount is not None and amount <= AMOUNT_THRESHOLD:
        return steps[:1]
    if amount is None:
        return steps[:1]
    return steps


async def start(
    db: AsyncSession,
    *,
    biz_type: str,
    biz_id: uuid.UUID,
    biz_no: str | None,
    title: str,
    amount: float | None,
    currency: str,
    applicant: User,
) -> ApprovalInstance:
    existing = (
        await db.execute(
            select(ApprovalInstance).where(
                ApprovalInstance.biz_type == biz_type,
                ApprovalInstance.biz_id == biz_id,
                ApprovalInstance.status == "PENDING",
                ApprovalInstance.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError("该单据已存在进行中的审批")

    steps = steps_for(biz_type, amount)
    instance = ApprovalInstance(
        biz_type=biz_type,
        biz_id=biz_id,
        biz_no=biz_no,
        title=title,
        status="PENDING",
        current_step=1,
        total_steps=len(steps),
        applicant_id=applicant.id,
        amount=amount,
        currency=currency,
    )
    db.add(instance)
    await db.flush()
    for idx, role in enumerate(steps, start=1):
        db.add(
            ApprovalTask(
                instance_id=instance.id,
                step=idx,
                approver_role=role,
                status="PENDING",
            )
        )
    db.add(
        ApprovalLog(
            instance_id=instance.id,
            action="SUBMIT",
            operator_id=applicant.id,
            operator_name=applicant.name,
            comment=f"提交审批（{len(steps)} 级）",
        )
    )
    await db.flush()
    return instance


def _can_act(user: User, task: ApprovalTask) -> bool:
    if user.is_superuser:
        return True
    if task.approver_role and task.approver_role in user.role_codes:
        return True
    return "admin" in user.role_codes


async def _current_task(db: AsyncSession, instance: ApprovalInstance) -> ApprovalTask:
    task = (
        await db.execute(
            select(ApprovalTask).where(
                ApprovalTask.instance_id == instance.id,
                ApprovalTask.step == instance.current_step,
                ApprovalTask.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if task is None:
        raise NotFoundError("审批任务不存在")
    return task


async def act(
    db: AsyncSession,
    *,
    instance_id: uuid.UUID,
    user: User,
    approved: bool,
    comment: str | None,
) -> ApprovalInstance:
    instance = (
        await db.execute(
            select(ApprovalInstance).where(ApprovalInstance.id == instance_id, ApprovalInstance.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if instance is None:
        raise NotFoundError("审批实例不存在")
    if instance.status != "PENDING":
        raise ConflictError(f"审批已结束（{instance.status}）")

    task = await _current_task(db, instance)
    if not _can_act(user, task):
        raise ForbiddenError(f"当前步骤需由角色 {task.approver_role} 审批")

    task.status = "APPROVED" if approved else "REJECTED"
    task.comment = comment
    task.approver_id = user.id
    task.acted_at = utcnow()

    db.add(
        ApprovalLog(
            instance_id=instance.id,
            task_id=task.id,
            action="APPROVE" if approved else "REJECT",
            operator_id=user.id,
            operator_name=user.name,
            comment=comment,
        )
    )

    if not approved:
        instance.status = "REJECTED"
        instance.finished_at = utcnow()
    elif instance.current_step >= instance.total_steps:
        instance.status = "APPROVED"
        instance.finished_at = utcnow()
    else:
        instance.current_step += 1

    await db.flush()
    return instance


async def pending_for(db: AsyncSession, user: User) -> list[ApprovalInstance]:
    """当前用户可处理的待审批实例。"""
    stmt = select(ApprovalInstance).where(ApprovalInstance.status == "PENDING", ApprovalInstance.deleted_at.is_(None))
    if not user.is_superuser:
        stmt = stmt.where(ApprovalInstance.applicant_id != user.id)
    instances = list((await db.execute(stmt.order_by(ApprovalInstance.created_at.desc()))).scalars().all())

    allowed: list[ApprovalInstance] = []
    roles = set(user.role_codes)
    for inst in instances:
        task = next((t for t in inst.tasks if t.step == inst.current_step), None)
        if task is None:
            continue
        if user.is_superuser or (task.approver_role or "") in roles or "admin" in roles:
            allowed.append(inst)
    return allowed


async def latest_for_biz(db: AsyncSession, biz_type: str, biz_id: uuid.UUID) -> ApprovalInstance | None:
    return (
        (
            await db.execute(
                select(ApprovalInstance)
                .where(
                    ApprovalInstance.biz_type == biz_type,
                    ApprovalInstance.biz_id == biz_id,
                    ApprovalInstance.deleted_at.is_(None),
                )
                .order_by(ApprovalInstance.created_at.desc())
            )
        )
        .scalars()
        .first()
    )


async def logs_of(db: AsyncSession, instance_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = (
        (
            await db.execute(
                select(ApprovalLog)
                .where(ApprovalLog.instance_id == instance_id, ApprovalLog.deleted_at.is_(None))
                .order_by(ApprovalLog.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "action": r.action,
            "operator_name": r.operator_name,
            "comment": r.comment,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
