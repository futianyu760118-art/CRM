"""EBMS 双向同步——出站序列化与字段 Owner 边界（PAND-249）。

设计要点（契约冻结版 §5 读法 A）：
- EBMS 仅一次性迁移来源，CRM 为长期 Owner。出站把 CRM 侧实体变更构造成
  ``AEOS.Event.V1`` 事件入队 Outbox（经 ``services.ebms.emit_entity_event``），不直写 EBMS 库。
- 字段级 Owner：对象已存在时，入站 UPSERT 仅应用 ``EBMS_OWNED_FIELDS`` 中的字段；
  其余字段由 CRM 拥有（见 ``services.ebms_ingest`` 的 OWNER_KEPT 冲突留痕）。
- 出站字段名对齐 EBMS 契约 §4.3 字段表（如 ``customer_code``/``serial_number``/
  ``country_region``/``customer_source``/``remarks``）；金额/数量一律十进制字符串
  （str-dec）传输，规避浮点漂移。
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.state_machine import INQUIRY_STATUS_MIGRATION
from app.models.business import Company, Inquiry, InquiryItem
from app.models.sales import Feedback, QuoteLibrary, SalesOrder, Sample
from app.services import ebms

Serializer = Callable[[Any], dict[str, Any]]

#: object_id 编码保留字符与转义（契约 §2 冻结）
KEY_SEP = "#"
KEY_ESC = "~"


def _ser(value: Any) -> Any:
    """线格式规整：Decimal→float、datetime/date→ISO、UUID→str。"""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def _dec(value: Any) -> str | None:
    """金额/数量 → 十进制字符串（str-dec 线格式，规避浮点漂移）。"""
    if value is None:
        return None
    try:
        return format(Decimal(str(value)), "f")
    except (ValueError, TypeError, ArithmeticError):
        return None


def _sanitize_key(value: Any) -> str:
    """业务键分量：`#` 转义为 `~`（契约 §2 保留字符）。"""
    return str(value if value is not None else "").replace(KEY_SEP, KEY_ESC)


def _drop_none(data: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in data.items() if v is not None}


def _screenshots_wire(value: Any) -> str | None:
    """screenshots 出站：JSONB 数组 → JSON 字符串（EBMS 字段线格式为 str）。"""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


# ------------------------------------------------------------------ 出站序列化（EBMS 字段名 + 线格式）


def customer_payload(c: Company) -> dict[str, Any]:
    return _drop_none(
        {
            "name": c.name,
            "customer_code": c.code,
            "former_name": c.former_name,
            "parent_code": c.parent_code,
            "customer_level": c.customer_level,
            "sales_mode": c.sales_mode,
            "customer_status": c.customer_status,
            "decision_maker": c.decision_maker,
            "decision_maker_position": c.decision_maker_position,
            "decision_core_need": c.decision_core_need,
            "last_trade_year": c.last_trade_year,
            "invoice_title": c.invoice_title,
            "tax_id": c.tax_id,
            "bank_name": c.bank_name,
            "bank_account": c.bank_account,
            "address": c.address,
            "country_region": c.country_region,
            "customer_source": c.source,
            "remarks": c.remark,
            "website": c.website,
        }
    )


def _inquiry_item_payload(it: InquiryItem) -> dict[str, Any]:
    return _drop_none(
        {
            "external_model": it.product_model,
            "internal_model": it.internal_model,
            "product_name": it.product_name,
            "power": it.power,
            "quantity": _dec(it.quantity),
            "target_price": _dec(it.target_price),
            "certificate_compliant": it.certificate_compliant,
            "certificate_level": it.certificate_level,
            "input_voltage": it.voltage,
            "battery": it.battery,
            "color_temp": it.color_temp,
            "luminous_flux": it.lumen,
            "light_source": it.light_source,
            "main_body": it.main_body,
            "lampshade": it.lamp_shade,
            "reflector": it.reflector,
            "cable": it.cable,
            "switch_type": it.switch,
            "usb": it.usb,
            "waterproof": it.waterproof,
            "sensor": it.sensor,
            "quote_time_needed": it.quote_lead_time,
            "custom_requirements": it.other_requirement,
        }
    )


def inquiry_payload(i: Inquiry) -> dict[str, Any]:
    status = i.status
    if status in INQUIRY_STATUS_MIGRATION:
        status = INQUIRY_STATUS_MIGRATION[status]
    data = _drop_none(
        {
            "serial_number": i.inquiry_no,
            "customer_name": i.customer_name,
            "customer_code": i.customer_code,
            "country_region": i.market,
            "customer_source": i.source,
            "quote_validity": i.quote_validity,
            "status": status,
            "delivery_date": _ser(i.delivery_date),
            "inquiry_time": _ser(i.start_date),
        }
    )
    items = [_inquiry_item_payload(it) for it in (i.items or [])]
    if items:
        data["items"] = items
    return data


def quote_library_payload(q: QuoteLibrary) -> dict[str, Any]:
    return _drop_none(
        {
            "external_model": q.external_model,
            "certificate_level": q.certificate_level or "",
            "internal_model": q.internal_model,
            "product_name": q.product_name,
            "category": q.category,
            "power": q.power,
            "configuration": q.configuration,
            "specs": q.specs,
            "price_rmb": _dec(q.price_rmb),
            "price_usd": _dec(q.price_usd),
            "unit_price": _dec(q.unit_price),
            "min_price": _dec(q.min_price),
            "validity_days": q.validity_days,
            "usage_count": q.usage_count,
            "source_inquiry_no": q.source_inquiry_no,
            "source_pricing_id": q.source_pricing_id,
            "creator": q.creator,
        }
    )


def sales_order_payload(o: SalesOrder) -> dict[str, Any]:
    return _drop_none(
        {
            "order_no": o.order_no,
            "line_no": o.line_no or "",
            "customer_name": o.customer_name,
            "customer_code": o.customer_code,
            "product_code": o.product_code,
            "product_name": o.product_name,
            "project_no": o.project_no,
            "quantity": _dec(o.quantity),
            "completed_qty": _dec(o.completed_qty),
            "order_amount": _dec(o.order_amount),
            "status": o.status,
            "risk_level": o.risk_level,
            "promised_date": _ser(o.promised_date),
            "plan_date": _ser(o.plan_date),
            "online_date": _ser(o.online_date),
            "user_status_locked": bool(o.user_status_locked),
            "user_status_modified_at": _ser(o.user_status_modified_at),
            "user_status_modified_by": _ser(o.user_status_modified_by),
        }
    )


def sample_payload(s: Sample) -> dict[str, Any]:
    return _drop_none(
        {
            "sample_no": s.sample_no,
            "customer_name": s.customer_name,
            "inquiry_no": s.inquiry_no,
            "product_name": s.product_name,
            "product_code": s.product_code,
            "quantity": _dec(s.quantity),
            "sample_type": s.sample_type,
            "status": s.status,
            "remarks": s.remark,
            "send_date": _ser(s.send_date),
            "confirm_date": _ser(s.confirm_date),
        }
    )


def feedback_payload(f: Feedback) -> dict[str, Any]:
    return _drop_none(
        {
            "feedback_no": f.feedback_no,
            "title": f.title,
            "description": f.description,
            "type": f.type,
            "priority": f.priority,
            "module": f.module,
            "submitter": f.submitter,
            "assignee": f.assignee,
            "screenshots": _screenshots_wire(f.screenshots),
            "source": f.source,
            "status": f.status,
            "resolution": f.resolution,
            "resolved_at": _ser(f.resolved_at),
        }
    )


SERIALIZERS: dict[str, Serializer] = {
    "Customer": customer_payload,
    "Inquiry": inquiry_payload,
    "QuoteLibrary": quote_library_payload,
    "Order": sales_order_payload,
    "Sample": sample_payload,
    "Feedback": feedback_payload,
}

#: object_type（PascalCase）-> Outbox biz_type
BIZ_TYPES: dict[str, str] = {
    "Customer": "COMPANY",
    "Inquiry": "INQUIRY",
    "QuoteLibrary": "QUOTE_LIBRARY",
    "Order": "ORDER",
    "Sample": "SAMPLE",
    "Feedback": "FEEDBACK",
}


def natural_id(object_type: str, obj: Any) -> str:
    """对象自然键（跨系统唯一业务标识，契约 §2 编码）。"""
    if object_type == "Customer":
        return _sanitize_key(obj.name)
    if object_type == "Inquiry":
        return _sanitize_key(obj.inquiry_no)
    if object_type == "QuoteLibrary":
        return f"{_sanitize_key(obj.external_model)}{KEY_SEP}{_sanitize_key(obj.certificate_level or '')}"
    if object_type == "Order":
        return f"{_sanitize_key(obj.order_no)}{KEY_SEP}{_sanitize_key(obj.line_no or '')}"
    if object_type == "Sample":
        return _sanitize_key(obj.sample_no)
    if object_type == "Feedback":
        return _sanitize_key(obj.feedback_no)
    raise ValueError(f"未知对象类型: {object_type!r}")


def _key_payload(object_type: str, obj: Any) -> dict[str, Any]:
    """deleted 事件 payload：仅携带自然键（EBMS 字段名），供接收侧定位对象。"""
    if object_type == "Customer":
        return {"name": obj.name}
    if object_type == "Inquiry":
        return {"serial_number": obj.inquiry_no}
    if object_type == "QuoteLibrary":
        return {"external_model": obj.external_model, "certificate_level": obj.certificate_level or ""}
    if object_type == "Order":
        return {"order_no": obj.order_no, "line_no": obj.line_no or ""}
    if object_type == "Sample":
        return {"sample_no": obj.sample_no}
    if object_type == "Feedback":
        return {"feedback_no": obj.feedback_no}
    return {}


async def emit_upsert(db: AsyncSession, object_type: str, obj: Any) -> dict[str, Any]:
    """对象创建/更新后，出站 upserted 事件。"""
    return await ebms.emit_entity_event(
        db,
        object_type=object_type,
        object_id=natural_id(object_type, obj),
        action="upserted",
        payload=SERIALIZERS[object_type](obj),
        biz_type=BIZ_TYPES[object_type],
        biz_id=obj.id,
    )


async def emit_delete(db: AsyncSession, object_type: str, obj: Any) -> dict[str, Any]:
    """对象删除后，出站 deleted 事件（payload 仅保留自然键）。"""
    return await ebms.emit_entity_event(
        db,
        object_type=object_type,
        object_id=natural_id(object_type, obj),
        action="deleted",
        payload=_key_payload(object_type, obj),
        biz_type=BIZ_TYPES[object_type],
        biz_id=obj.id,
    )


# ------------------------------------------------------------------ 字段 Owner 边界（读法 A）


#: 对象已存在时，入站 UPSERT 仅应用 Owner=EBMS 的字段（身份/迁移锚点）。
#: 其余字段 Owner=CRM，入站若试图改写 → 记录 SyncConflict(OWNER_KEPT) 并跳过。
EBMS_OWNED_FIELDS: dict[str, set[str]] = {
    "Customer": {"external_id"},
    "Inquiry": {"external_id"},
    "QuoteLibrary": {"external_id"},
    "Order": {"external_id"},
    "Sample": {"external_id"},
    "Feedback": {"external_id"},
}
