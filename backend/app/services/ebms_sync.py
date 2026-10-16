"""EBMS 双向同步——出站序列化与字段 Owner 边界（PAND-249）。

设计要点（契约冻结版 §5 读法 A）：
- EBMS 仅一次性迁移来源，CRM 为长期 Owner。出站把 CRM 侧实体变更构造成
  ``AEOS.Event.V1`` 事件入队 Outbox（经 ``services.ebms.emit_entity_event``），不直写 EBMS 库。
- 字段级 Owner：对象已存在时，入站 UPSERT 仅应用 ``EBMS_OWNED_FIELDS`` 中的字段；
  其余字段由 CRM 拥有（见 ``services.ebms_ingest`` 的 OWNER_KEPT 冲突留痕）。
- 金额/数量统一转 float（指纹计算在契约层已按十进制字符串规整，规避浮点漂移）。
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.state_machine import INQUIRY_STATUS_MIGRATION
from app.models.business import Company, Inquiry
from app.models.sales import Feedback, QuoteLibrary, SalesOrder, Sample
from app.services import ebms

Serializer = Callable[[Any], dict[str, Any]]


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


def _pick(obj: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    return {f: _ser(getattr(obj, f, None)) for f in fields if getattr(obj, f, None) is not None}


# ------------------------------------------------------------------ 出站字段集


CUSTOMER_FIELDS: tuple[str, ...] = (
    "code",
    "name",
    "name_en",
    "country",
    "currency",
    "industry",
    "customer_level",
    "source",
    "status",
    "website",
    "address",
    "remark",
    "external_id",
    "former_name",
    "parent_code",
    "sales_mode",
    "customer_status",
    "decision_maker",
    "decision_maker_position",
    "decision_core_need",
    "last_trade_year",
    "invoice_title",
    "tax_id",
    "bank_name",
    "bank_account",
    "country_region",
)

INQUIRY_FIELDS: tuple[str, ...] = (
    "inquiry_no",
    "external_id",
    "company_id",
    "contact_id",
    "source",
    "requirement_text",
    "currency",
    "target_price",
    "delivery_date",
    "trade_terms",
    "payment_terms",
    "status",
    "customer_code",
    "customer_name",
    "customer_type",
    "market",
    "quantity_total",
    "quote_validity",
)

QUOTE_FIELDS: tuple[str, ...] = (
    "external_model",
    "certificate_level",
    "external_id",
    "internal_model",
    "product_name",
    "category",
    "power",
    "configuration",
    "specs",
    "price_rmb",
    "price_usd",
    "unit_price",
    "min_price",
    "validity_days",
    "usage_count",
    "source_inquiry_no",
    "remark",
    "creator",
)

ORDER_FIELDS: tuple[str, ...] = (
    "order_no",
    "line_no",
    "external_id",
    "company_id",
    "customer_name",
    "customer_code",
    "product_code",
    "product_name",
    "project_no",
    "quantity",
    "completed_qty",
    "order_amount",
    "status",
    "risk_level",
    "promised_date",
    "plan_date",
    "online_date",
    "user_status_locked",
    "remark",
)

SAMPLE_FIELDS: tuple[str, ...] = (
    "sample_no",
    "external_id",
    "company_id",
    "customer_name",
    "inquiry_no",
    "product_name",
    "product_code",
    "quantity",
    "sample_type",
    "status",
    "send_date",
    "confirm_date",
    "remark",
)

FEEDBACK_FIELDS: tuple[str, ...] = (
    "feedback_no",
    "external_id",
    "title",
    "description",
    "type",
    "priority",
    "module",
    "submitter",
    "assignee",
    "screenshots",
    "source",
    "status",
    "resolution",
    "resolved_at",
)


def customer_payload(c: Company) -> dict[str, Any]:
    return _pick(c, CUSTOMER_FIELDS)


def inquiry_payload(i: Inquiry) -> dict[str, Any]:
    data = _pick(i, INQUIRY_FIELDS)
    # 出站对齐 EBMS 11 态取值域（AC-M2.7）
    if data.get("status") in INQUIRY_STATUS_MIGRATION:
        data["status"] = INQUIRY_STATUS_MIGRATION[data["status"]]
    return data


def quote_library_payload(q: QuoteLibrary) -> dict[str, Any]:
    return _pick(q, QUOTE_FIELDS)


def sales_order_payload(o: SalesOrder) -> dict[str, Any]:
    return _pick(o, ORDER_FIELDS)


def sample_payload(s: Sample) -> dict[str, Any]:
    return _pick(s, SAMPLE_FIELDS)


def feedback_payload(f: Feedback) -> dict[str, Any]:
    return _pick(f, FEEDBACK_FIELDS)


SERIALIZERS: dict[str, Serializer] = {
    "customer": customer_payload,
    "inquiry": inquiry_payload,
    "quote_library": quote_library_payload,
    "order": sales_order_payload,
    "sample": sample_payload,
    "feedback": feedback_payload,
}

#: object_type -> Outbox biz_type
BIZ_TYPES: dict[str, str] = {
    "customer": "COMPANY",
    "inquiry": "INQUIRY",
    "quote_library": "QUOTE_LIBRARY",
    "order": "ORDER",
    "sample": "SAMPLE",
    "feedback": "FEEDBACK",
}

#: object_type -> 可入站/出站字段集（均为模型列名）
FIELD_SETS: dict[str, tuple[str, ...]] = {
    "customer": CUSTOMER_FIELDS,
    "inquiry": INQUIRY_FIELDS,
    "quote_library": QUOTE_FIELDS,
    "order": ORDER_FIELDS,
    "sample": SAMPLE_FIELDS,
    "feedback": FEEDBACK_FIELDS,
}


def natural_id(object_type: str, obj: Any) -> str:
    """对象自然键（跨系统唯一业务标识）。"""
    if object_type == "customer":
        return obj.code
    if object_type == "inquiry":
        return obj.inquiry_no
    if object_type == "quote_library":
        return f"{obj.external_model}::{obj.certificate_level or ''}"
    if object_type == "order":
        return obj.order_no
    if object_type == "sample":
        return obj.sample_no
    if object_type == "feedback":
        return obj.feedback_no
    raise ValueError(f"未知对象类型: {object_type!r}")


async def emit_upsert(db: AsyncSession, object_type: str, obj: Any) -> dict[str, Any]:
    """对象创建/更新后，出站 upserted 事件。"""
    payload = SERIALIZERS[object_type](obj)
    payload["id"] = str(obj.id)
    return await ebms.emit_entity_event(
        db,
        object_type=object_type,
        object_id=natural_id(object_type, obj),
        action="upserted",
        payload=payload,
        biz_type=BIZ_TYPES[object_type],
        biz_id=obj.id,
    )


async def emit_delete(db: AsyncSession, object_type: str, obj: Any) -> dict[str, Any]:
    """对象删除后，出站 deleted 事件（payload 仅保留身份标识）。"""
    object_id = natural_id(object_type, obj)
    payload = {"id": str(obj.id), "external_id": _ser(getattr(obj, "external_id", None))}
    return await ebms.emit_entity_event(
        db,
        object_type=object_type,
        object_id=object_id,
        action="deleted",
        payload=payload,
        biz_type=BIZ_TYPES[object_type],
        biz_id=obj.id,
    )


# ------------------------------------------------------------------ 字段 Owner 边界（读法 A）


#: 对象已存在时，入站 UPSERT 仅应用 Owner=EBMS 的字段（身份/迁移锚点）。
#: 其余字段 Owner=CRM，入站若试图改写 → 记录 SyncConflict(OWNER_KEPT) 并跳过。
EBMS_OWNED_FIELDS: dict[str, set[str]] = {
    "customer": {"external_id"},
    "inquiry": {"external_id"},
    "quote_library": {"external_id"},
    "order": {"external_id"},
    "sample": {"external_id"},
    "feedback": {"external_id"},
}
