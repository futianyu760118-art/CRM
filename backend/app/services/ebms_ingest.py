"""EBMS 入站摄入（AEOS.Event.V1）—— 幂等 / Owner 规则 / 冲突留痕（PAND-249）。

契约冻结版 §5 冲突规则（本模块实现）：
- OWNER_KEPT ：对象已存在时，入站仅应用 ``EBMS_OWNED_FIELDS``；CRM 拥有字段若被
  改写，只记录 ``SyncConflict``（resolution=SKIPPED），不改本地值。
- LOCKED     ：订单 ``user_status_locked`` 时，状态相关变更被拒并留痕。
- STALE      ：``occurred_at < last_sync_at`` 的迟到事件被丢弃。
- DELETE 保护：``sync_status=PENDING``（本地有未同步出站变更）时拒绝删除。

红线：不直写 EBMS 库——本模块只消费 EBMS 推入的契约事件，写本地 CRM 表。
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contracts.aeos import (
    AeosEventContract,
    ContractValidationError,
    event_idempotency_key,
    to_wire,
    validate_contract,
)
from app.db.base import utcnow
from app.models.business import Company, Inquiry
from app.models.integration import IntegrationLog
from app.models.sales import Feedback, QuoteLibrary, SalesOrder, Sample, SyncConflict
from app.services.ebms_sync import EBMS_OWNED_FIELDS, FIELD_SETS, _ser
from app.services.number_sequence import next_number

INBOUND_SYSTEM = "EBMS"
INBOUND_ACTION = "EVENT_INGEST"
LOG_SUCCESS = "SUCCESS"

#: 创建时需转 UUID 的外键/归属列
_UUID_COLUMNS = {
    "company_id",
    "contact_id",
    "inquiry_id",
    "assignee_id",
    "submitter_id",
    "source_inquiry_id",
    "product_id",
    "sku_id",
    "opportunity_id",
    "owner_id",
    "department_id",
    "user_status_modified_by",
}

_MODEL_BY_TYPE: dict[str, type] = {
    "customer": Company,
    "inquiry": Inquiry,
    "quote_library": QuoteLibrary,
    "order": SalesOrder,
    "sample": Sample,
    "feedback": Feedback,
}


def _coerce(column: str, value: Any) -> Any:
    if value is None:
        return None
    if column in _UUID_COLUMNS:
        if isinstance(value, uuid.UUID):
            return value
        try:
            return uuid.UUID(str(value))
        except (ValueError, AttributeError):
            return None
    if column in {"screenshots", "spec_rows"} and isinstance(value, list):
        return value
    return value


def _differs(local: Any, incoming: Any) -> bool:
    return _ser(local) != _ser(incoming)


def _mark_synced(obj: Any) -> None:
    if hasattr(obj, "sync_status"):
        obj.sync_status = "SYNCED"
    if hasattr(obj, "last_sync_at"):
        obj.last_sync_at = utcnow()


def _record_conflict(
    db: AsyncSession,
    object_type: str,
    obj: Any,
    field: str,
    contract: AeosEventContract,
    key: str,
    incoming: Any,
    local: Any,
) -> dict[str, Any]:
    row = SyncConflict(
        object_type=object_type,
        object_id=contract.object_id,
        field=field,
        source_system=contract.source_system,
        incoming_value={"value": incoming},
        local_value={"value": local},
        resolution="SKIPPED",
        event_id=contract.event_id,
        idempotency_key=key,
        occurred_at=contract.occurred_at,
    )
    db.add(row)
    return {"field": field, "resolution": "OWNER_KEPT", "local": local, "incoming": incoming}


async def _find_object(db: AsyncSession, object_type: str, payload: dict[str, Any]) -> Any | None:
    model = _MODEL_BY_TYPE[object_type]
    external_id = payload.get("external_id")
    if external_id:
        row = (
            await db.execute(select(model).where(model.external_id == external_id, model.deleted_at.is_(None)))
        ).scalar_one_or_none()
        if row is not None:
            return row
    if object_type == "customer" and payload.get("code"):
        return (
            await db.execute(select(model).where(model.code == payload["code"], model.deleted_at.is_(None)))
        ).scalar_one_or_none()
    if object_type == "inquiry" and payload.get("inquiry_no"):
        return (
            await db.execute(select(model).where(model.inquiry_no == payload["inquiry_no"], model.deleted_at.is_(None)))
        ).scalar_one_or_none()
    if object_type == "quote_library" and payload.get("external_model"):
        return (
            await db.execute(
                select(model).where(
                    model.external_model == payload["external_model"],
                    model.certificate_level == (payload.get("certificate_level") or ""),
                    model.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
    if object_type == "order" and payload.get("order_no"):
        return (
            await db.execute(
                select(model).where(
                    model.order_no == payload["order_no"],
                    model.line_no == (payload.get("line_no") or ""),
                    model.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
    if object_type == "sample" and payload.get("sample_no"):
        return (
            await db.execute(select(model).where(model.sample_no == payload["sample_no"], model.deleted_at.is_(None)))
        ).scalar_one_or_none()
    if object_type == "feedback" and payload.get("feedback_no"):
        return (
            await db.execute(
                select(model).where(model.feedback_no == payload["feedback_no"], model.deleted_at.is_(None))
            )
        ).scalar_one_or_none()
    return None


async def _fill_natural_key(db: AsyncSession, object_type: str, payload: dict[str, Any]) -> str | None:
    """补全/校验自然键，返回该对象缺失自然键时的错误（None 表示可创建）。"""
    if object_type == "customer":
        if not payload.get("name"):
            return "customer 缺少必填字段 name"
        if not payload.get("code"):
            payload["code"] = f"CUS-{uuid.uuid4().hex[:8]}"
        return None
    if object_type == "inquiry":
        if not payload.get("inquiry_no"):
            payload["inquiry_no"] = await next_number("inquiry")
        return None
    if object_type == "quote_library":
        if not payload.get("external_model"):
            return "quote_library 缺少必填字段 external_model"
        return None
    if object_type == "order":
        if not payload.get("order_no"):
            return "order 缺少必填字段 order_no"
        return None
    if object_type == "sample":
        if not payload.get("sample_no"):
            payload["sample_no"] = await next_number("sample")
        return None
    if object_type == "feedback":
        if not payload.get("feedback_no"):
            payload["feedback_no"] = await next_number("feedback")
        return None
    return f"未知对象类型: {object_type!r}"


async def _apply_object(
    db: AsyncSession,
    contract: AeosEventContract,
    payload: dict[str, Any],
    key: str,
) -> dict[str, Any]:
    object_type = contract.object_type
    is_delete = contract.event_type.endswith(".deleted")
    model = _MODEL_BY_TYPE[object_type]
    obj = await _find_object(db, object_type, payload)

    if obj is None:
        if is_delete:
            return {
                "object_type": object_type,
                "object_id": contract.object_id,
                "action": "skipped",
                "reason": "not_found",
            }
        error = await _fill_natural_key(db, object_type, payload)
        if error:
            return {"object_type": object_type, "object_id": contract.object_id, "action": "error", "reason": error}
        obj = model()
        for column in FIELD_SETS.get(object_type, ()):
            if column not in payload:
                continue
            setattr(obj, column, _coerce(column, payload[column]))
        db.add(obj)
        _mark_synced(obj)
        return {"object_type": object_type, "object_id": contract.object_id, "action": "created"}

    # ---- 对象已存在 ----
    if is_delete:
        if getattr(obj, "sync_status", None) == "PENDING":
            return {
                "object_type": object_type,
                "object_id": contract.object_id,
                "action": "skipped",
                "reason": "delete_protected_pending",
            }
        obj.deleted_at = utcnow()
        return {"object_type": object_type, "object_id": contract.object_id, "action": "deleted"}

    # STALE：迟到事件
    last_sync = getattr(obj, "last_sync_at", None)
    if last_sync and contract.occurred_at < last_sync:
        return {"object_type": object_type, "object_id": contract.object_id, "action": "skipped", "reason": "stale"}

    # LOCKED：订单用户锁定
    if object_type == "order" and getattr(obj, "user_status_locked", False):
        return {"object_type": object_type, "object_id": contract.object_id, "action": "skipped", "reason": "locked"}

    owned = EBMS_OWNED_FIELDS.get(object_type, set())
    conflicts: list[dict[str, Any]] = []
    applied = 0
    for field, value in payload.items():
        if field == "id" or not hasattr(obj, field) or value is None:
            continue
        if field in owned:
            coerced = _coerce(field, value)
            if not _differs(getattr(obj, field), coerced):
                continue
            setattr(obj, field, coerced)
            applied += 1
        elif _differs(getattr(obj, field), value):
            conflicts.append(
                _record_conflict(db, object_type, obj, field, contract, key, value, _ser(getattr(obj, field)))
            )

    _mark_synced(obj)
    if applied == 0 and not conflicts:
        action = "unchanged"
    elif conflicts and applied == 0:
        action = "conflict"
    else:
        action = "updated"
    return {
        "object_type": object_type,
        "object_id": contract.object_id,
        "action": action,
        "applied_fields": applied,
        "conflicts": conflicts,
    }


async def _find_ingest_log(db: AsyncSession, key: str) -> IntegrationLog | None:
    return (
        await db.execute(
            select(IntegrationLog)
            .where(IntegrationLog.idempotency_key == key, IntegrationLog.deleted_at.is_(None))
            .order_by(IntegrationLog.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def ingest_event(db: AsyncSession, event: Mapping[str, Any]) -> dict[str, Any]:
    """消费一条 EBMS 事件：校验 → 幂等 → 应用 → 记日志。

    幂等键 = ``CRM:{event_type}:{object_id}:{fingerprint}``；同内容重复投递直接返回 duplicate。
    契约校验失败抛 ``ContractValidationError``（HTTP 422）。
    """
    contract = validate_contract(event)
    if not isinstance(contract, AeosEventContract):
        raise ContractValidationError(f"期望 AEOS.Event.V1，实际 {contract.contract_version}")
    wire = to_wire(contract)
    key = event_idempotency_key("CRM", wire)

    existing = await _find_ingest_log(db, key)
    if existing is not None and existing.status == LOG_SUCCESS:
        return {
            "idempotent": True,
            "status": "duplicate",
            "event_id": contract.event_id,
            "idempotency_key": key,
        }

    result = await _apply_object(db, contract, dict(contract.payload), key)

    db.add(
        IntegrationLog(
            system=INBOUND_SYSTEM,
            action=INBOUND_ACTION,
            request_id=contract.event_id,
            idempotency_key=key,
            business_id=contract.object_id,
            request_payload=dict(event),
            response_payload=result,
            status=LOG_SUCCESS,
            started_at=utcnow(),
            finished_at=utcnow(),
        )
    )
    await db.flush()
    return {
        "idempotent": False,
        "status": result.get("action", "processed"),
        "event_id": contract.event_id,
        "event_type": contract.event_type,
        "object_type": contract.object_type,
        "object_id": contract.object_id,
        "idempotency_key": key,
        "detail": result,
    }


async def list_conflicts(
    db: AsyncSession,
    *,
    object_type: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[SyncConflict], int]:
    """同步冲突分页查询（对账/人工裁决用）。"""
    from sqlalchemy import func

    stmt = select(SyncConflict).where(SyncConflict.deleted_at.is_(None))
    if object_type:
        stmt = stmt.where(SyncConflict.object_type == object_type)
    total = int((await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one())
    rows = (
        (
            await db.execute(
                stmt.order_by(SyncConflict.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    return list(rows), total
