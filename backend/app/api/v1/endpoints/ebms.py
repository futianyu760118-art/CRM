"""EBMS 集成接口（AEOS 契约）：联调入口 / 投递 / 日志 / 重试 / 对账。

与 M6 K3 集成并列，独立前缀 `/integrations/ebms`，复用 `integration_outbox` /
`integration_log` 两表，不新增业务表。
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.contracts.aeos import (
    EXCEPTION_CONTRACT_VERSION,
    EXCEPTION_STATUSES,
    RESULT_CONTRACT_VERSION,
    RESULT_STATUSES,
    SEVERITY_LEVELS,
    AeosExceptionContract,
    AeosMetric,
    AeosPeriod,
    AeosResultContract,
    ContractValidationError,
    to_wire,
    unknown_fields,
    validate_contract,
)
from app.core import response as resp
from app.core.deps import DbSession, require_permission
from app.models.integration import IntegrationLog, IntegrationOutbox
from app.models.user import User
from app.schemas.ebms import (
    ContractValidateIn,
    ContractValidateOut,
    DeliverIn,
    DeliverOut,
    EbmsReconcileOut,
    PilotExceptionIn,
    PilotResultIn,
    RetryOut,
)
from app.schemas.integration import IntegrationLogOut
from app.services import ebms
from app.services.query import apply_sort, paginate

router = APIRouter(prefix="/integrations/ebms", tags=["M6-EBMS集成"])

_EVENT_ACTION = {ebms.EVENT_RESULT: ebms.ACTION_RESULT, ebms.EVENT_EXCEPTION: ebms.ACTION_EXCEPTION}


@router.get("/contracts/baseline", summary="CRM 侧契约字段基线（供与 EBMS contracts 对照）")
async def contracts_baseline(
    _: User = Depends(require_permission("integration:view")),
) -> dict[str, Any]:
    """返回 CRM 侧已落地的契约版本、字段集与取值域，便于逐字段对照 EBMS 基线。"""
    return resp.ok(
        {
            "contracts": {
                RESULT_CONTRACT_VERSION: {
                    "required_fields": sorted(AeosResultContract.model_fields),
                    "status_values": list(RESULT_STATUSES),
                    "period_fields": sorted(AeosPeriod.model_fields),
                    "metric_fields": sorted(AeosMetric.model_fields),
                },
                EXCEPTION_CONTRACT_VERSION: {
                    "required_fields": sorted(AeosExceptionContract.model_fields),
                    "severity_values": list(SEVERITY_LEVELS),
                    "status_values": list(EXCEPTION_STATUSES),
                },
            },
            "source_system": ebms.SOURCE_SYSTEM,
            "note": "EBMS 仓库当前无 contracts/aeos-contracts-v1.schema.json，基线取 examples.json + README。",
        }
    )


@router.post("/contracts/validate", summary="联调：校验 AEOS 契约（不落库）")
async def validate(
    payload: ContractValidateIn,
    _: User = Depends(require_permission("integration:view")),
) -> dict[str, Any]:
    try:
        contract = validate_contract(payload.contract)
    except ContractValidationError as exc:
        return resp.ok(
            ContractValidateOut(
                valid=False,
                contract_version=payload.contract.get("contract_version"),
                unknown_fields=unknown_fields(payload.contract),
                errors=list(exc.data) if isinstance(exc.data, list) else [{"message": exc.message}],
            ).model_dump(mode="json")
        )
    return resp.ok(
        ContractValidateOut(
            valid=True,
            contract_version=contract.contract_version,
            contract_id=contract.contract_id,
            normalized=to_wire(contract),
            unknown_fields=unknown_fields(payload.contract),
        ).model_dump(mode="json")
    )


@router.post("/pilot-a/result", summary="试点 A：销售/订单经营结果 Result → EBMS")
async def pilot_a_result(
    payload: PilotResultIn,
    db: DbSession,
    _: User = Depends(require_permission("integration:view")),
) -> dict[str, Any]:
    result = await ebms.emit_sales_result(
        db,
        period_start=payload.period_start,
        period_end=payload.period_end,
        metric_code=payload.metric_code,
        currency=payload.currency,
        limit=payload.limit,
    )
    if payload.deliver:
        result["delivery"] = await ebms.deliver_pending(db)
    await db.commit()
    return resp.ok(result)


@router.post("/pilot-b/exception", summary="试点 B：订单交付逾期 Exception → EBMS")
async def pilot_b_exception(
    payload: PilotExceptionIn,
    db: DbSession,
    _: User = Depends(require_permission("integration:view")),
) -> dict[str, Any]:
    result = await ebms.emit_delivery_overdue(
        db,
        sla_days=payload.sla_days,
        as_of=payload.as_of,
        limit=payload.limit,
    )
    if payload.deliver:
        result["delivery"] = await ebms.deliver_pending(db)
    await db.commit()
    return resp.ok(result)


@router.post("/deliver", summary="投递所有到期未处理的 Outbox")
async def deliver(
    payload: DeliverIn,
    db: DbSession,
    _: User = Depends(require_permission("integration:view")),
) -> dict[str, Any]:
    result = await ebms.deliver_pending(db, limit=payload.limit)
    await db.commit()
    return resp.ok(DeliverOut(**result).model_dump(mode="json"))


@router.post("/retry/{log_id}", summary="重投某条投递")
async def retry(
    log_id: uuid.UUID,
    db: DbSession,
    _: User = Depends(require_permission("integration:view")),
) -> dict[str, Any]:
    result = await ebms.retry(db, log_id)
    await db.commit()
    return resp.ok(RetryOut(**result).model_dump(mode="json"))


@router.post("/reconcile", summary="对账：产出 vs 投递成功")
async def reconcile(
    db: DbSession,
    _: User = Depends(require_permission("integration:view")),
) -> dict[str, Any]:
    result = await ebms.reconcile(db)
    return resp.ok(EbmsReconcileOut(**result).model_dump(mode="json"))


@router.get("/logs", summary="EBMS 投递日志")
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
    stmt = select(IntegrationLog).where(IntegrationLog.deleted_at.is_(None), IntegrationLog.system == "EBMS")
    if status:
        stmt = stmt.where(IntegrationLog.status == status)
    if action:
        stmt = stmt.where(IntegrationLog.action == action)
    stmt = apply_sort(stmt, IntegrationLog, sort, order)
    rows, total = await paginate(db, stmt, page, page_size)
    items = [IntegrationLogOut.model_validate(r).model_dump(mode="json") for r in rows]
    return resp.page(items, total, page, page_size)


@router.get("/outbox", summary="EBMS 本地消息表（Outbox）")
async def outbox(
    db: DbSession,
    _: User = Depends(require_permission("integration:view")),
    status: str | None = None,
    event_type: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
) -> dict[str, Any]:
    stmt = select(IntegrationOutbox).where(
        IntegrationOutbox.deleted_at.is_(None),
        IntegrationOutbox.event_type.in_(tuple(_EVENT_ACTION)),
    )
    if status:
        stmt = stmt.where(IntegrationOutbox.status == status)
    if event_type:
        stmt = stmt.where(IntegrationOutbox.event_type == event_type)
    stmt = stmt.order_by(IntegrationOutbox.created_at.desc())
    rows, total = await paginate(db, stmt, page, page_size)
    items = [
        {
            "id": str(r.id),
            "event_type": r.event_type,
            "biz_type": r.biz_type,
            "biz_id": str(r.biz_id),
            "contract_id": (r.payload or {}).get("result_id")
            or (r.payload or {}).get("exception_id")
            or (r.payload or {}).get("event_id"),
            "status": r.status,
            "retry_count": r.retry_count,
            "available_at": r.available_at.isoformat() if r.available_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "processed_at": r.processed_at.isoformat() if r.processed_at else None,
        }
        for r in rows
    ]
    return resp.page(items, total, page, page_size)
