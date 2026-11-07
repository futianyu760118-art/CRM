"""AEOS ``verify`` 动作（PAND-330，架构 §4.4 / F5）。

单一实现点：
- ``verify`` 幂等（F5-A03）：同 ``(subject_type, subject_id, subject_revision)`` 返回同一条；
- 状态联动唯一路径（F5-A04）：``SalesResult.status`` 仅当存在 ``passed``/``exempt``
  Verification 时 ``submitted → verified``；``failed`` 不改变结果状态；
- 验证通过后构造 ``AEOS.Result.V1``（status=VERIFIED）与 L2 ``SalesResultVerified`` 事件出站。
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.error_codes import ErrCode
from app.core.exceptions import ApiError, NotFoundError
from app.db.base import utcnow
from app.domain.state_machine import VERIFICATION_STATUSES
from app.models.sales import SalesResult
from app.models.verification import Verification
from app.services import ebms

SUBJECT_TYPE_RESULT = "result"
ACCEPTING_STATUSES = frozenset({"passed", "exempt"})


def verification_out(row: Verification) -> dict[str, Any]:
    return {
        "verification_id": str(row.verification_id),
        "subject_type": row.subject_type,
        "subject_id": row.subject_id,
        "subject_revision": row.subject_revision,
        "object_ref": {"object_type": row.object_ref_type, "object_id": row.object_ref_id},
        "verifier": str(row.verifier) if row.verifier else None,
        "verifier_role": row.verifier_role,
        "verified_at": row.verified_at.isoformat() if row.verified_at else None,
        "status": row.status,
        "reason": row.reason,
        "evidence_refs": list(row.evidence_refs or []),
        "comment": row.comment,
        "tenant_id": row.tenant_id,
        "revision": row.revision,
    }


def result_out(row: SalesResult) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "result_id": row.result_id,
        "period": {"start": row.period_start.isoformat(), "end": row.period_end.isoformat()},
        "metric": {
            "code": row.metric_code,
            "value": float(row.metric_value),
            "unit": row.metric_unit,
            "calculation_version": row.calculation_version,
        },
        "object_ref": {"object_type": row.object_ref_type, "object_id": row.object_ref_id},
        "status": row.status,
        "evidence_refs": list(row.evidence_refs or []),
        "currency": row.currency,
        "order_count": row.order_count,
        "tenant_id": row.tenant_id,
        "revision": row.revision,
        "fact_owner": row.fact_owner,
        "record_owner": str(row.owner_id) if row.owner_id else None,
        "processor": str(row.processor) if row.processor else None,
        "consumer": list(row.consumer or []),
        "verifier": str(row.verifier) if row.verifier else None,
    }


async def get_result(db: AsyncSession, result_id: str) -> SalesResult:
    row = (
        await db.execute(
            select(SalesResult).where(
                SalesResult.result_id == result_id,
                SalesResult.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError("经营结果不存在")
    return row


async def latest_verification(db: AsyncSession, result: SalesResult) -> Verification | None:
    return (
        await db.execute(
            select(Verification)
            .where(
                Verification.subject_type == SUBJECT_TYPE_RESULT,
                Verification.subject_id == result.result_id,
                Verification.deleted_at.is_(None),
            )
            .order_by(Verification.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def list_verifications(db: AsyncSession, result_id: str) -> Sequence[Verification]:
    return (
        (
            await db.execute(
                select(Verification)
                .where(
                    Verification.subject_type == SUBJECT_TYPE_RESULT,
                    Verification.subject_id == result_id,
                    Verification.deleted_at.is_(None),
                )
                .order_by(Verification.created_at)
            )
        )
        .scalars()
        .all()
    )


async def verify_result(
    db: AsyncSession,
    *,
    subject_id: str,
    verifier: uuid.UUID | None,
    status: str,
    reason: str | None = None,
    evidence_refs: list[str] | None = None,
    comment: str | None = None,
    verifier_role: str | None = None,
    emit: bool = True,
) -> dict[str, Any]:
    """验证一条 Result；幂等且状态联动唯一路径（F5-A03/A04）。"""
    result = await get_result(db, subject_id)
    if verifier is None:
        raise ApiError(ErrCode.PARAM_ERROR, "verifier 不能为空（F5-A01）")
    if status not in VERIFICATION_STATUSES:
        raise ApiError(ErrCode.PARAM_ERROR, f"status 取值越界，允许: {VERIFICATION_STATUSES}")
    if status in {"failed", "exempt"} and not (reason or "").strip():
        raise ApiError(ErrCode.PARAM_ERROR, f"status={status} 时必须填写 reason（F5-A01）")

    existing = (
        await db.execute(
            select(Verification).where(
                Verification.subject_type == SUBJECT_TYPE_RESULT,
                Verification.subject_id == result.result_id,
                Verification.subject_revision == result.revision,
                Verification.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return {
            "duplicate": True,
            "verification": verification_out(existing),
            "result": result_out(result),
            "delivery": None,
            "event": None,
        }

    row = Verification(
        verification_id=uuid.uuid4(),
        subject_type=SUBJECT_TYPE_RESULT,
        subject_id=result.result_id,
        subject_revision=result.revision,
        object_ref_type=result.object_ref_type,
        object_ref_id=result.object_ref_id,
        verifier=verifier,
        verifier_role=verifier_role,
        verified_at=utcnow(),
        status=status,
        reason=(reason or "").strip() or None,
        evidence_refs=list(evidence_refs) if evidence_refs is not None else list(result.evidence_refs or []),
        comment=comment,
    )
    db.add(row)

    delivery: dict[str, Any] | None = None
    event: dict[str, Any] | None = None
    if status in ACCEPTING_STATUSES:
        # 状态联动唯一路径：直接更新状态/verifier，不触发 revision 自增（验证是状态转移，
        # 非业务内容变更；revision 保持提交时版本，保证 verify 幂等键稳定）。
        await db.execute(
            update(SalesResult)
            .where(SalesResult.id == result.id)
            .values(status="verified", verifier=verifier)
            .execution_options(synchronize_session=False)
        )
        await db.refresh(result)
        if emit:
            delivery = await ebms.emit_result_verified(db, result)
            event = await ebms.emit_sales_result_verified_event(
                db,
                result,
                verification_id=row.verification_id,
                actor_id=str(verifier),
                evidence_refs=list(row.evidence_refs or []),
            )

    await db.flush()
    return {
        "duplicate": False,
        "verification": verification_out(row),
        "result": result_out(result),
        "delivery": delivery,
        "event": event,
    }
