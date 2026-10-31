"""EBMS 入站摄入（AEOS.Event.V1）—— 幂等 / Owner 规则 / 冲突留痕（PAND-249）。

契约冻结版 §5 冲突规则（本模块实现）：
- OWNER_KEPT ：对象已存在时，入站仅应用 ``EBMS_OWNED_FIELDS``；CRM 拥有字段若被
  改写，只记录 ``SyncConflict``（resolution=OWNER_KEPT），不改本地值。
- LOCKED     ：订单 ``user_status_locked`` 时，仅跳过 ``status`` 覆盖并留痕
  （resolution=LOCKED），其余字段照常按 Owner 规则同步（对齐 EBMS 外部 API）。
- STALE      ：``occurred_at < last_sync_at`` 的迟到事件被丢弃。
- DELETE 保护：``sync_status=PENDING``（本地有未同步出站变更）时拒绝删除。

字段映射（§4.3 EBMS→CRM）：入站先按 ``FIELD_MAPS`` 把 EBMS 线字段名映射到 CRM 模型列
（``customer_code→code``、``serial_number→inquiry_no``、``customer_source→source``、
``country_region→market``、``remarks→remark`` 等），再按自然键 → ``external_id`` 定位，
保证「一物一 ID」不重复建对象。

红线：不直写 EBMS 库——本模块只消费 EBMS 推入的契约事件，写本地 CRM 表。
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
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
from app.domain.state_machine import EXTERNAL_ORDER_STATUS_MAP
from app.models.business import Company, Inquiry, InquiryItem
from app.models.integration import IntegrationLog
from app.models.sales import Feedback, QuoteLibrary, SalesOrder, Sample, SyncConflict
from app.services.ebms_sync import EBMS_OWNED_FIELDS, KEY_SEP, _sanitize_key, _ser

INBOUND_SYSTEM = "EBMS"
INBOUND_ACTION = "EVENT_INGEST"
LOG_SUCCESS = "SUCCESS"

#: EBMS→CRM 入站幂等键 target 段（契约 §4.1：CRM→EBMS 用 EBMS，EBMS→CRM 用 M05）
INBOUND_TARGET = "M05"

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

#: str-dec 金额/数量列（入站从十进制字符串转 float）
_STR_DEC_COLUMNS = {
    "quantity",
    "completed_qty",
    "order_amount",
    "target_price",
    "quantity_total",
    "price_rmb",
    "price_usd",
    "unit_price",
    "min_price",
    "first_order_amount",
    "annual_amount",
}

_DATE_COLUMNS = {"delivery_date", "promised_date", "plan_date", "online_date", "send_date", "confirm_date"}
_DATETIME_COLUMNS = {
    "start_date",
    "end_date",
    "resolved_at",
    "user_status_modified_at",
    "sample_date",
    "order_date",
    "shipment_date",
}

_MODEL_BY_TYPE: dict[str, Any] = {
    "Customer": Company,
    "Inquiry": Inquiry,
    "QuoteLibrary": QuoteLibrary,
    "Order": SalesOrder,
    "Sample": Sample,
    "Feedback": Feedback,
}

#: §4.3 EBMS 线字段名 → CRM 模型列名（字段映射层）
FIELD_MAPS: dict[str, dict[str, str]] = {
    "Customer": {
        "name": "name",
        "customer_code": "code",
        "former_name": "former_name",
        "parent_code": "parent_code",
        "customer_level": "customer_level",
        "sales_mode": "sales_mode",
        "customer_status": "customer_status",
        "decision_maker": "decision_maker",
        "decision_maker_position": "decision_maker_position",
        "decision_core_need": "decision_core_need",
        "last_trade_year": "last_trade_year",
        "invoice_title": "invoice_title",
        "tax_id": "tax_id",
        "bank_name": "bank_name",
        "bank_account": "bank_account",
        "address": "address",
        "country_region": "country_region",
        "customer_source": "source",
        "remarks": "remark",
        "website": "website",
    },
    "Inquiry": {
        "serial_number": "inquiry_no",
        "customer_name": "customer_name",
        "customer_code": "customer_code",
        "country_region": "market",
        "customer_source": "source",
        "quote_validity": "quote_validity",
        "status": "status",
        "delivery_date": "delivery_date",
        "inquiry_time": "start_date",
    },
    "QuoteLibrary": {
        "external_model": "external_model",
        "certificate_level": "certificate_level",
        "internal_model": "internal_model",
        "product_name": "product_name",
        "category": "category",
        "power": "power",
        "configuration": "configuration",
        "specs": "specs",
        "price_rmb": "price_rmb",
        "price_usd": "price_usd",
        "unit_price": "unit_price",
        "min_price": "min_price",
        "validity_days": "validity_days",
        "usage_count": "usage_count",
        "source_inquiry_no": "source_inquiry_no",
        "source_pricing_id": "source_pricing_id",
        "creator": "creator",
    },
    "Order": {
        "order_no": "order_no",
        "line_no": "line_no",
        "customer_name": "customer_name",
        "customer_code": "customer_code",
        "product_code": "product_code",
        "product_name": "product_name",
        "project_no": "project_no",
        "quantity": "quantity",
        "completed_qty": "completed_qty",
        "order_amount": "order_amount",
        "status": "status",
        "risk_level": "risk_level",
        "promised_date": "promised_date",
        "plan_date": "plan_date",
        "online_date": "online_date",
        "user_status_locked": "user_status_locked",
        "user_status_modified_at": "user_status_modified_at",
        "user_status_modified_by": "user_status_modified_by",
    },
    "Sample": {
        "sample_no": "sample_no",
        "customer_name": "customer_name",
        "inquiry_no": "inquiry_no",
        "product_name": "product_name",
        "product_code": "product_code",
        "quantity": "quantity",
        "sample_type": "sample_type",
        "status": "status",
        "remarks": "remark",
        "send_date": "send_date",
        "confirm_date": "confirm_date",
    },
    "Feedback": {
        "feedback_no": "feedback_no",
        "title": "title",
        "description": "description",
        "type": "type",
        "priority": "priority",
        "module": "module",
        "submitter": "submitter",
        "assignee": "assignee",
        "screenshots": "screenshots",
        "source": "source",
        "status": "status",
        "resolution": "resolution",
        "resolved_at": "resolved_at",
    },
}

INQUIRY_ITEM_MAP: dict[str, str] = {
    "external_model": "product_model",
    "internal_model": "internal_model",
    "product_name": "product_name",
    "power": "power",
    "quantity": "quantity",
    "target_price": "target_price",
    "certificate_compliant": "certificate_compliant",
    "certificate_level": "certificate_level",
    "input_voltage": "voltage",
    "battery": "battery",
    "color_temp": "color_temp",
    "luminous_flux": "lumen",
    "light_source": "light_source",
    "main_body": "main_body",
    "lampshade": "lamp_shade",
    "reflector": "reflector",
    "cable": "cable",
    "switch_type": "switch",
    "usb": "usb",
    "waterproof": "waterproof",
    "sensor": "sensor",
    "quote_time_needed": "quote_lead_time",
    "custom_requirements": "other_requirement",
}


def _external_id(object_type: str, payload: Mapping[str, Any]) -> str:
    """按 §2 由 EBMS 线字段编码 external_id（= 契约 object_id 同源）。"""
    if object_type == "Customer":
        name = payload.get("name")
        return _sanitize_key(name) if name else ""
    if object_type == "Inquiry":
        no = payload.get("serial_number")
        return _sanitize_key(no) if no else ""
    if object_type == "QuoteLibrary":
        model = payload.get("external_model")
        if not model:
            return ""
        return f"{_sanitize_key(model)}{KEY_SEP}{_sanitize_key(payload.get('certificate_level') or '')}"
    if object_type == "Order":
        no = payload.get("order_no")
        if not no:
            return ""
        return f"{_sanitize_key(no)}{KEY_SEP}{_sanitize_key(payload.get('line_no') or '')}"
    if object_type == "Sample":
        no = payload.get("sample_no")
        return _sanitize_key(no) if no else ""
    if object_type == "Feedback":
        no = payload.get("feedback_no")
        return _sanitize_key(no) if no else ""
    return ""


def _map_payload(object_type: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """把 EBMS 线字段映射为 CRM 模型列（仅白名单字段，未声明字段丢弃）。

    订单状态按冻结契约 ``EXTERNAL_ORDER_STATUS_MAP`` 做值映射（16-09=B：同名映射）。
    """
    mapping = FIELD_MAPS.get(object_type, {})
    out: dict[str, Any] = {}
    for wire, column in mapping.items():
        if wire not in payload:
            continue
        value = payload[wire]
        if object_type == "Order" and column == "status":
            value = EXTERNAL_ORDER_STATUS_MAP.get(value, value)
        out[column] = value
    return out


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
    if column in _STR_DEC_COLUMNS:
        if isinstance(value, str):
            try:
                return float(Decimal(value))
            except (ValueError, ArithmeticError):
                return value
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return float(value)
        return value
    if column in _DATE_COLUMNS and isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return value
    if column in _DATETIME_COLUMNS and isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    if column == "screenshots" and isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else [parsed]
        except ValueError:
            return [value]
    if column == "screenshots" and isinstance(value, list):
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
    *,
    resolution: str = "OWNER_KEPT",
) -> dict[str, Any]:
    row = SyncConflict(
        object_type=object_type,
        object_id=contract.object_id,
        field=field,
        source_system=contract.source_system,
        incoming_value={"value": incoming},
        local_value={"value": local},
        resolution=resolution,
        event_id=contract.event_id,
        idempotency_key=key,
        occurred_at=contract.occurred_at,
    )
    db.add(row)
    return {"field": field, "resolution": resolution, "local": local, "incoming": incoming}


async def _find_object(
    db: AsyncSession, object_type: str, external_id: str, mapped: dict[str, Any]
) -> Any | None:
    model = _MODEL_BY_TYPE[object_type]
    # 客户身份 = customer_code（PAND-304 R2 口径）；同名客户可能对应不同编码，须先按编码定位
    if object_type == "Customer" and mapped.get("code"):
        row = (
            await db.execute(select(model).where(model.code == mapped["code"], model.deleted_at.is_(None)))
        ).scalar_one_or_none()
        if row is not None:
            return row
    if external_id:
        row = (
            await db.execute(select(model).where(model.external_id == external_id, model.deleted_at.is_(None)))
        ).scalar_one_or_none()
        if row is not None:
            return row
    # 自然键兜底（external_id 尚未回填的存量/边界）
    if object_type == "Customer" and mapped.get("name"):
        return (
            await db.execute(select(model).where(model.name == mapped["name"], model.deleted_at.is_(None)))
        ).scalar_one_or_none()
    if object_type == "Inquiry" and mapped.get("inquiry_no"):
        return (
            await db.execute(select(model).where(model.inquiry_no == mapped["inquiry_no"], model.deleted_at.is_(None)))
        ).scalar_one_or_none()
    if object_type == "QuoteLibrary" and mapped.get("external_model"):
        return (
            await db.execute(
                select(model).where(
                    model.external_model == mapped["external_model"],
                    model.certificate_level == (mapped.get("certificate_level") or ""),
                    model.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
    if object_type == "Order" and mapped.get("order_no"):
        return (
            await db.execute(
                select(model).where(
                    model.order_no == mapped["order_no"],
                    model.line_no == (mapped.get("line_no") or ""),
                    model.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
    if object_type == "Sample" and mapped.get("sample_no"):
        return (
            await db.execute(select(model).where(model.sample_no == mapped["sample_no"], model.deleted_at.is_(None)))
        ).scalar_one_or_none()
    if object_type == "Feedback" and mapped.get("feedback_no"):
        return (
            await db.execute(
                select(model).where(model.feedback_no == mapped["feedback_no"], model.deleted_at.is_(None))
            )
        ).scalar_one_or_none()
    return None


async def _create_items(db: AsyncSession, inquiry: Inquiry, items: list[Any]) -> None:
    for raw in items:
        if not isinstance(raw, dict):
            continue
        mapped_item = {
            column: _coerce(column, raw[wire])
            for wire, column in INQUIRY_ITEM_MAP.items()
            if wire in raw and raw[wire] is not None
        }
        db.add(InquiryItem(inquiry_id=inquiry.id, **mapped_item))


async def _apply_object(
    db: AsyncSession,
    contract: AeosEventContract,
    payload: dict[str, Any],
    key: str,
) -> dict[str, Any]:
    object_type = contract.object_type
    is_delete = contract.event_type.endswith(".deleted")
    model = _MODEL_BY_TYPE[object_type]
    external_id = _external_id(object_type, payload) or contract.object_id
    mapped = _map_payload(object_type, payload)
    obj = await _find_object(db, object_type, external_id, mapped)

    if obj is None:
        if is_delete:
            return {
                "object_type": object_type,
                "object_id": contract.object_id,
                "action": "skipped",
                "reason": "not_found",
            }
        if not external_id:
            return {
                "object_type": object_type,
                "object_id": contract.object_id,
                "action": "error",
                "reason": "缺少必填自然键",
            }
        obj = model()
        for column, value in mapped.items():
            if hasattr(obj, column):
                setattr(obj, column, _coerce(column, value))
        obj.external_id = external_id
        db.add(obj)
        await db.flush()
        if object_type == "Inquiry":
            await _create_items(db, obj, payload.get("items") or [])
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

    # LOCKED：订单用户锁定 → 仅跳过 status 覆盖（其余字段照常按 Owner 规则同步），并留痕 resolution=LOCKED
    locked_status = object_type == "Order" and getattr(obj, "user_status_locked", False)

    owned = EBMS_OWNED_FIELDS.get(object_type, set())
    conflicts: list[dict[str, Any]] = []
    applied = 0
    for column, value in mapped.items():
        if not hasattr(obj, column) or value is None:
            continue
        coerced = _coerce(column, value)
        if locked_status and column == "status":
            if _differs(getattr(obj, column), value):
                conflicts.append(
                    _record_conflict(
                        db,
                        object_type,
                        obj,
                        column,
                        contract,
                        key,
                        value,
                        _ser(getattr(obj, column)),
                        resolution="LOCKED",
                    )
                )
            continue
        if column in owned:
            if not _differs(getattr(obj, column), coerced):
                continue
            setattr(obj, column, coerced)
            applied += 1
        elif _differs(getattr(obj, column), coerced):
            conflicts.append(
                _record_conflict(db, object_type, obj, column, contract, key, value, _ser(getattr(obj, column)))
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


def _resolve_key(
    contract: AeosEventContract, wire: Mapping[str, Any], body_key: Any, header_key: str | None
) -> str:
    """幂等键：头/体一致性校验 → 头键 → 体键 → 按 target=M05 整包重算。

    无头/体键时按 EBMS→CRM 出站同规则重算（target=M05 + 整包指纹），保证两侧写入的
    idempotency_key 逐字一致，用于幂等去重与对账。
    """
    if header_key:
        if body_key and str(body_key) != header_key:
            raise ContractValidationError("X-Idempotency-Key 与报文 idempotency_key 不一致")
        return header_key
    if body_key:
        return str(body_key)
    return event_idempotency_key(INBOUND_TARGET, wire)


async def ingest_event(
    db: AsyncSession, event: Mapping[str, Any], header_idempotency_key: str | None = None
) -> dict[str, Any]:
    """消费一条 EBMS 事件：校验 → 幂等 → 应用 → 记日志。

    幂等键 = ``M05:{event_type}:{object_id}:{fingerprint}``；头/体均缺时按整包口径重算。
    ``dictionary.upserted`` 暂不落 CRM 业务表，返回「未实现」不 500。
    """
    contract = validate_contract(event)
    if not isinstance(contract, AeosEventContract):
        raise ContractValidationError(f"期望 AEOS.Event.V1，实际 {contract.contract_version}")

    if contract.object_type == "Dictionary":
        # 优雅降级：字典组（Owner=EBMS）暂无 CRM 落位表，暂存/跳过，不 500
        return {
            "idempotent": False,
            "status": "not_implemented",
            "event_id": contract.event_id,
            "event_type": contract.event_type,
            "object_type": contract.object_type,
            "object_id": contract.object_id,
        }

    wire = to_wire(contract)
    key = _resolve_key(contract, wire, event.get("idempotency_key"), header_idempotency_key)

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
