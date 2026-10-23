"""EBMS 销售中心 6 模块存量 → CRM 一次性迁移（PAND-301）。

数据源：EBMS 的 SQLite 库（``database/sales.db``，表 ``t_<name>``，业务字段存于 ``j`` 列 JSON）。
迁入通道：复用 ``app.services.ebms_ingest.ingest_event``（即 ``POST /api/v1/integrations/ebms/ingest``
的同一实现：契约校验 → 幂等键 → Owner 规则 → 落库），本文书不绕过映射与去重逻辑。

自然键口径（契约 §4.1）：
    Customer→name, Inquiry→serial_number, QuoteLibrary→external_model#certificate_level,
    Order→order_no#line_no, Sample→sample_no, Feedback→feedback_no（EBMS 缺失，迁移期合成）

用法（在 crm-backend 容器内执行）::

    python /tmp/ebms_migrate_sales_center.py extract --ebms-db /data/sales.db --dump /tmp/ebms_dump.json
    python /tmp/ebms_migrate_sales_center.py migrate --dump /tmp/ebms_dump.json --direct --batch-size 500
    python /tmp/ebms_migrate_sales_center.py verify  --dump /tmp/ebms_dump.json

``migrate`` 幂等：同一快照重复执行时，事件指纹一致，入站层按 ``M05:{event_type}:{object_id}:{fingerprint}``
直接返回 duplicate，不新增业务记录。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

CST = timezone(timedelta(hours=8))

#: 对象类型 → (快照键, EBMS 表名)
TABLES: dict[str, tuple[str, str]] = {
    "Customer": ("customers", "t_customers"),
    "Inquiry": ("inquiries", "t_inquiries"),
    "QuoteLibrary": ("quote_library", "t_quote_library"),
    "Order": ("orders", "t_orders"),
    "Sample": ("samples", "t_samples"),
    "Feedback": ("feedback", "t_feedback"),
}
EVENT_TYPE = {
    "Customer": "customer.upserted",
    "Inquiry": "inquiry.upserted",
    "QuoteLibrary": "quote_library.upserted",
    "Order": "order.upserted",
    "Sample": "sample.upserted",
    "Feedback": "feedback.upserted",
}
SHORT = {
    "Customer": "cus",
    "Inquiry": "inq",
    "QuoteLibrary": "qlt",
    "Order": "ord",
    "Sample": "smp",
    "Feedback": "fbk",
}

#: 与 app/services/ebms_ingest.py FIELD_MAPS / INQUIRY_ITEM_MAP 保持一致的线字段集合
CUSTOMER_WIRES = [
    "name", "customer_code", "former_name", "parent_code", "customer_level", "sales_mode",
    "customer_status", "decision_maker", "decision_maker_position", "decision_core_need",
    "last_trade_year", "invoice_title", "tax_id", "bank_name", "bank_account", "address",
    "country_region", "customer_source", "remarks", "website",
]
INQUIRY_WIRES = [
    "serial_number", "customer_name", "customer_code", "country_region", "customer_source",
    "quote_validity", "status", "delivery_date", "inquiry_time",
]
INQUIRY_ITEM_WIRES = [
    "external_model", "internal_model", "product_name", "power", "quantity", "target_price",
    "certificate_compliant", "certificate_level", "input_voltage", "battery", "color_temp",
    "luminous_flux", "light_source", "main_body", "lampshade", "reflector", "cable",
    "switch_type", "usb", "waterproof", "sensor", "quote_time_needed", "custom_requirements",
]
QUOTE_WIRES = [
    "external_model", "certificate_level", "internal_model", "product_name", "category", "power",
    "configuration", "specs", "price_rmb", "price_usd", "unit_price", "min_price", "validity_days",
    "usage_count", "source_inquiry_no", "source_pricing_id", "creator",
]
ORDER_WIRES = [
    "order_no", "line_no", "customer_name", "customer_code", "product_code", "product_name",
    "project_no", "quantity", "completed_qty", "order_amount", "status", "risk_level",
    "promised_date", "plan_date", "online_date", "user_status_locked", "user_status_modified_at",
    "user_status_modified_by",
]
SAMPLE_WIRES = [
    "sample_no", "customer_name", "inquiry_no", "product_name", "product_code", "quantity",
    "sample_type", "status", "remarks", "send_date", "confirm_date",
]
FEEDBACK_WIRES = [
    "feedback_no", "title", "description", "type", "priority", "module", "submitter", "assignee",
    "screenshots", "source", "status", "resolution", "resolved_at",
]

#: 旧版客户分级（EBMS 早期导入）→ 契约 CUSTOMER_LEVELS
CUSTOMER_LEVEL_MAP = {
    "A类客户": "A级（核心大客户）",
    "B类客户": "B级（普通大客户）",
    "C类客户": "C级（中小客户）",
    "D类客户": "D级（新客/休眠客）",
}
#: EBMS 历史英文状态 → CRM 客户状态
CUSTOMER_STATUS_MAP = {"active": "大货合作客户"}
#: EBMS 样品 open ↔ CRM 待确认
SAMPLE_STATUS_MAP = {"open": "pending"}
#: EBMS 样品类型乱码（GBK 转码残留）→ 默认常规样品
SAMPLE_TYPE_MAP = {"??": "常规"}


def _s(value: Any) -> str | None:
    """线字段统一为去空白字符串；空串视为未提供。"""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(Decimal(str(value)))
    except (ValueError, ArithmeticError):
        return None


def _int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(Decimal(str(value)))
    except (ValueError, ArithmeticError):
        return None


def _parse_ts(value: Any) -> datetime | None:
    text = _s(value)
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed.replace(tzinfo=CST) if parsed.tzinfo is None else parsed


def _iso_date(value: Any) -> str | None:
    ts = _parse_ts(value)
    return ts.date().isoformat() if ts else None


def _iso_dt(value: Any) -> str | None:
    ts = _parse_ts(value)
    return ts.isoformat() if ts else None


def _updated_key(row: dict[str, Any]) -> datetime:
    return _parse_ts(row.get("updated_at")) or _parse_ts(row.get("created_at")) or datetime.min.replace(tzinfo=CST)


def _occurred_at(row: dict[str, Any]) -> str:
    ts = _parse_ts(row.get("updated_at")) or _parse_ts(row.get("created_at")) or datetime(1970, 1, 1, tzinfo=CST)
    return ts.isoformat()


def _payload(row: dict[str, Any], wires: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for wire in wires:
        value = _s(row.get(wire))
        if value is not None:
            out[wire] = value
    return out


def load_dump(path: str) -> dict[str, list[dict[str, Any]]]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    missing = [key for key, _ in TABLES.values() if key not in data]
    if missing:
        raise SystemExit(f"快照缺少表: {missing}")
    return data


def extract_sqlite(db_path: str, dump_path: str) -> dict[str, int]:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        out: dict[str, list[dict[str, Any]]] = {}
        for key, table in TABLES.values():
            rows = conn.execute(f"SELECT id, j FROM {table}").fetchall()  # noqa: S608 - 表名来自固定白名单
            parsed: list[dict[str, Any]] = []
            for row_id, raw in rows:
                try:
                    parsed.append(json.loads(raw))
                except (TypeError, ValueError):
                    parsed.append({"_id": row_id, "_parse_error": True})
            out[key] = parsed
        with open(dump_path, "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False)
        return {key: len(rows) for key, rows in out.items()}
    finally:
        conn.close()


def build_events(dump: dict[str, list[dict[str, Any]]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """按契约构造事件；返回 (事件列表, 迁移口径报告)。"""
    events: list[dict[str, Any]] = []
    notes: dict[str, Any] = {
        "source_rows": {},
        "planned": {},
        "dedup": {},
        "value_maps": {},
        "unmapped": {},
    }

    def emit(object_type: str, object_id: str, payload: dict[str, Any], occurred_at: str) -> None:
        seq = len(events) + 1
        events.append(
            {
                "contract_version": "AEOS.Event.V1",
                "event_id": f"evt-mig-{SHORT[object_type]}-{seq:05d}",
                "event_type": EVENT_TYPE[object_type],
                "source_system": "EBMS",
                "object_type": object_type,
                "object_id": object_id,
                "operation": "UPSERT",
                "occurred_at": occurred_at,
                "trace_id": f"trace-mig-{SHORT[object_type]}-{seq:05d}",
                "payload": payload,
            }
        )

    # ---- Customer：自然键 name，同名多行为历史重复，保留 updated_at 最新一条 ----
    rows = dump["customers"]
    notes["source_rows"]["Customer"] = len(rows)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        name = _s(row.get("name"))
        if name:
            groups[name].append(row)
    notes["dedup"]["Customer"] = {"distinct_names": len(groups), "dropped_duplicate_rows": len(rows) - len(groups)}
    used_codes: set[str] = set()
    level_remap = status_remap = source_fallback = synth_code = adjusted_code = 0
    for name in sorted(groups):
        rep = max(groups[name], key=_updated_key)
        code = _s(rep.get("customer_code"))
        if not code:
            code = f"EBMS-C{_int(rep.get('id')) or 0:06d}"
            synth_code += 1
        if code in used_codes:
            code = f"{code}-EB{_int(rep.get('id')) or 0}"
            adjusted_code += 1
        used_codes.add(code)
        payload = _payload(rep, CUSTOMER_WIRES)
        payload["name"] = name
        payload["customer_code"] = code
        if not payload.get("customer_source"):
            fallback = _s(rep.get("source"))
            if fallback:
                payload["customer_source"] = fallback
                source_fallback += 1
        level = payload.get("customer_level")
        if level in CUSTOMER_LEVEL_MAP:
            payload["customer_level"] = CUSTOMER_LEVEL_MAP[level]
            level_remap += 1
        status = payload.get("customer_status")
        if status in CUSTOMER_STATUS_MAP:
            payload["customer_status"] = CUSTOMER_STATUS_MAP[status]
            status_remap += 1
        emit("Customer", name, payload, _occurred_at(rep))
    notes["value_maps"]["Customer.customer_level"] = {"legacy_remapped": level_remap}
    notes["value_maps"]["Customer.customer_status"] = {"active_remapped": status_remap}
    notes["dedup"]["Customer"].update(
        {"synthesized_codes": synth_code, "conflict_suffixed_codes": adjusted_code, "source_fallback": source_fallback}
    )

    # ---- Inquiry：自然键 serial_number；扁平产品字段组装为单条 items 明细 ----
    rows = dump["inquiries"]
    notes["source_rows"]["Inquiry"] = len(rows)
    inquiry_status_map = Counter()
    for row in rows:
        serial = _s(row.get("serial_number"))
        if not serial:
            continue
        payload = _payload(row, INQUIRY_WIRES)
        status = payload.get("status")
        if status == "invalid_status":
            payload["status"] = "new"
            inquiry_status_map["invalid_status→new"] += 1
        if payload.get("delivery_date"):
            payload["delivery_date"] = _iso_date(row.get("delivery_date"))
        if payload.get("inquiry_time"):
            payload["inquiry_time"] = _iso_dt(row.get("inquiry_time"))
        item: dict[str, Any] = {}
        for wire in INQUIRY_ITEM_WIRES:
            raw = row.get(wire)
            value = _num(raw) if wire in {"quantity", "target_price"} else _s(raw)
            if value is not None:
                item[wire] = value
        if item:
            payload["items"] = [item]
        emit("Inquiry", serial, payload, _occurred_at(row))
    notes["value_maps"]["Inquiry.status"] = dict(inquiry_status_map)

    # ---- QuoteLibrary：自然键 external_model#certificate_level ----
    rows = dump["quote_library"]
    notes["source_rows"]["QuoteLibrary"] = len(rows)
    for row in rows:
        model = _s(row.get("external_model"))
        if not model:
            continue
        payload = _payload(row, QUOTE_WIRES)
        for wire in ("price_rmb", "price_usd", "unit_price", "min_price"):
            if wire in payload:
                payload[wire] = _num(row.get(wire))
        for wire in ("validity_days", "usage_count"):
            if wire in payload:
                payload[wire] = _int(row.get(wire))
        payload["certificate_level"] = _s(row.get("certificate_level")) or ""
        emit("QuoteLibrary", f"{model}#{payload['certificate_level']}", payload, _occurred_at(row))
    notes["unmapped"]["QuoteLibrary.remarks"] = sum(1 for r in rows if _s(r.get("remarks")))

    # ---- Order：自然键 order_no#line_no；重复行保留 updated_at 最新 ----
    rows = dump["orders"]
    notes["source_rows"]["Order"] = len(rows)
    order_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        order_no = _s(row.get("order_no"))
        if order_no:
            order_groups[f"{order_no}#{_s(row.get('line_no')) or ''}"].append(row)
    notes["dedup"]["Order"] = {
        "distinct_keys": len(order_groups),
        "dropped_duplicate_rows": len(rows) - len(order_groups),
    }
    for key, group in order_groups.items():
        rep = max(group, key=_updated_key)
        payload = _payload(rep, ORDER_WIRES)
        for wire in ("quantity", "completed_qty", "order_amount"):
            if wire in payload:
                payload[wire] = _num(rep.get(wire))
        for wire in ("promised_date", "plan_date", "online_date"):
            if wire in payload:
                payload[wire] = _iso_date(rep.get(wire))
        if "user_status_locked" in payload:
            payload["user_status_locked"] = bool(_int(rep.get("user_status_locked")))
        if payload.get("user_status_modified_at"):
            payload["user_status_modified_at"] = _iso_dt(rep.get("user_status_modified_at"))
        payload.pop("user_status_modified_by", None)  # EBMS 侧为整数用户号，非 CRM UUID
        order_no, line_no = key.split("#", 1)
        payload["order_no"] = order_no
        payload["line_no"] = line_no
        emit("Order", key, payload, _occurred_at(rep))
    notes["unmapped"]["Order.remarks"] = sum(1 for r in rows if _s(r.get("remarks")))
    notes["unmapped"]["Order.bom_no"] = sum(1 for r in rows if _s(r.get("bom_no")))

    # ---- Sample：自然键 sample_no；open→pending，类型乱码归常规 ----
    rows = dump["samples"]
    notes["source_rows"]["Sample"] = len(rows)
    sample_status_map = Counter()
    sample_type_map = Counter()
    for row in rows:
        sample_no = _s(row.get("sample_no"))
        if not sample_no:
            continue
        payload = _payload(row, SAMPLE_WIRES)
        if payload.get("status") in SAMPLE_STATUS_MAP:
            sample_status_map[f"{payload['status']}→{SAMPLE_STATUS_MAP[payload['status']]}"] += 1
            payload["status"] = SAMPLE_STATUS_MAP[payload["status"]]
        if payload.get("sample_type") in SAMPLE_TYPE_MAP:
            sample_type_map[f"{payload['sample_type']}→{SAMPLE_TYPE_MAP[payload['sample_type']]}"] += 1
            payload["sample_type"] = SAMPLE_TYPE_MAP[payload["sample_type"]]
        for wire in ("send_date", "confirm_date"):
            if wire in payload:
                payload[wire] = _iso_date(row.get(wire))
        emit("Sample", sample_no, payload, _occurred_at(row))
    notes["value_maps"]["Sample.status"] = dict(sample_status_map)
    notes["value_maps"]["Sample.sample_type"] = dict(sample_type_map)

    # ---- Feedback：EBMS 无 feedback_no，迁移期以 EBMS 主键合成稳定业务键 ----
    rows = dump["feedback"]
    notes["source_rows"]["Feedback"] = len(rows)
    for row in rows:
        row_id = _int(row.get("id"))
        feedback_no = f"FB-EBMS-{row_id:04d}" if row_id is not None else None
        if not feedback_no:
            continue
        payload = _payload(row, FEEDBACK_WIRES)
        payload["feedback_no"] = feedback_no
        shots = _s(row.get("screenshots"))
        if shots:
            try:
                parsed = json.loads(shots)
                payload["screenshots"] = parsed if isinstance(parsed, list) else [shots]
            except ValueError:
                payload["screenshots"] = [shots]
        if payload.get("resolved_at"):
            payload["resolved_at"] = _iso_dt(row.get("resolved_at"))
        emit("Feedback", feedback_no, payload, _occurred_at(row))
    notes["unmapped"]["Feedback.feedback_no"] = "EBMS 源无该字段，按 FB-EBMS-{id} 合成"

    for object_type in TABLES:
        notes["planned"][object_type] = sum(1 for e in events if e["object_type"] == object_type)
    return events, notes


async def _run_direct(events: list[dict[str, Any]], batch_size: int) -> tuple[Counter, list[dict[str, Any]]]:
    from app.db.session import async_session_factory
    from app.services import ebms_ingest

    stats: Counter = Counter()
    errors: list[dict[str, Any]] = []
    async with async_session_factory() as db:
        for index, event in enumerate(events, 1):
            try:
                async with db.begin_nested():
                    result = await ebms_ingest.ingest_event(db, event)
            except Exception as exc:  # noqa: BLE001 - 逐条隔离，避免一条脏数据回滚整批
                stats["error"] += 1
                errors.append({"event_id": event["event_id"], "object_id": event["object_id"], "error": str(exc)[:300]})
                continue
            stats[result.get("status", "unknown")] += 1
            if index % batch_size == 0:
                await db.commit()
        await db.commit()
    return stats, errors


async def _run_http(
    events: list[dict[str, Any]], base_url: str, token: str, chunk: int
) -> tuple[Counter, list[dict[str, Any]]]:
    import httpx

    stats: Counter = Counter()
    errors: list[dict[str, Any]] = []
    url = base_url.rstrip("/") + "/api/v1/integrations/ebms/ingest/batch"
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=120) as client:
        for start in range(0, len(events), chunk):
            batch = events[start : start + chunk]
            response = await client.post(url, json={"events": batch}, headers=headers)
            if response.status_code != 200:
                errors.append({"batch": start, "status_code": response.status_code, "body": response.text[:300]})
                continue
            for result in response.json()["data"]["results"]:
                stats[result.get("status", "unknown")] += 1
    return stats, errors


LINK_RULES: dict[str, tuple[str, str]] = {
    # 表别名 -> (别名, 承载客户编码的列)；EBMS 订单/样品的 customer_name 实际存的是客户编码
    "sales_order": ("o", "o.customer_code"),
    "inquiry": ("i", "i.customer_code"),
    "sample": ("s", "s.customer_name"),
}


async def _link_company_refs(dry_run: bool) -> dict[str, int]:
    from sqlalchemy import text

    from app.db.session import async_session_factory

    counts: dict[str, int] = {}
    async with async_session_factory() as db:
        for table, (alias, code_column) in LINK_RULES.items():
            source = f"{table} {alias}"
            match = f"c.code = {code_column} AND c.deleted_at IS NULL"
            pending = f"{alias}.company_id IS NULL AND {alias}.deleted_at IS NULL"
            counts[table] = int(
                (
                    await db.execute(
                        text(f"SELECT count(*) FROM {source} JOIN company c ON {match} WHERE {pending}")
                    )
                ).scalar_one()
            )
            if not dry_run:
                await db.execute(
                    text(f"UPDATE {source} SET company_id = c.id FROM company c WHERE {match} AND {pending}")
                )
        if dry_run:
            await db.rollback()
        else:
            await db.commit()
    return counts


async def _verify(dump: dict[str, list[dict[str, Any]]], events: list[dict[str, Any]]) -> dict[str, Any]:
    from sqlalchemy import select

    from app.db.session import async_session_factory
    from app.models.business import Company, Inquiry
    from app.models.sales import Feedback, QuoteLibrary, SalesOrder, Sample

    expected: dict[str, dict[str, dict[str, Any]]] = {}
    for event in events:
        expected.setdefault(event["object_type"], {})[event["object_id"]] = event["payload"]

    async with async_session_factory() as db:
        rows: dict[str, list[Any]] = {
            "Customer": list((await db.execute(select(Company).where(Company.deleted_at.is_(None)))).scalars()),
            "Inquiry": list((await db.execute(select(Inquiry).where(Inquiry.deleted_at.is_(None)))).scalars()),
            "QuoteLibrary": list(
                (await db.execute(select(QuoteLibrary).where(QuoteLibrary.deleted_at.is_(None)))).scalars()
            ),
            "Order": list((await db.execute(select(SalesOrder).where(SalesOrder.deleted_at.is_(None)))).scalars()),
            "Sample": list((await db.execute(select(Sample).where(Sample.deleted_at.is_(None)))).scalars()),
            "Feedback": list((await db.execute(select(Feedback).where(Feedback.deleted_at.is_(None)))).scalars()),
        }

    def get(obj: Any, attr: str) -> Any:
        return getattr(obj, attr, None)

    def key_of(object_type: str, obj: Any) -> str:
        if object_type == "Customer":
            return get(obj, "name")
        if object_type == "Inquiry":
            return get(obj, "inquiry_no")
        if object_type == "QuoteLibrary":
            return f"{get(obj, 'external_model')}#{get(obj, 'certificate_level') or ''}"
        if object_type == "Order":
            return f"{get(obj, 'order_no')}#{get(obj, 'line_no') or ''}"
        if object_type == "Sample":
            return get(obj, "sample_no")
        return get(obj, "feedback_no")

    compare_fields = {
        "Customer": ["name", "code", "customer_level", "customer_status", "source", "country_region"],
        "Inquiry": ["inquiry_no", "customer_name", "status", "market", "start_date"],
        "QuoteLibrary": ["external_model", "certificate_level", "price_rmb", "unit_price", "usage_count"],
        "Order": ["order_no", "line_no", "quantity", "completed_qty", "order_amount", "status", "risk_level"],
        "Sample": ["sample_no", "customer_name", "status", "sample_type"],
        "Feedback": ["feedback_no", "title", "status", "priority", "type"],
    }
    column_for_wire = {
        "name": "name", "code": "code", "customer_level": "customer_level",
        "customer_status": "customer_status", "source": "source", "country_region": "country_region",
        "inquiry_no": "inquiry_no", "customer_name": "customer_name", "status": "status",
        "market": "market", "start_date": "start_date",
        "external_model": "external_model", "certificate_level": "certificate_level",
        "price_rmb": "price_rmb", "unit_price": "unit_price", "usage_count": "usage_count",
        "order_no": "order_no", "line_no": "line_no", "quantity": "quantity",
        "completed_qty": "completed_qty", "order_amount": "order_amount",
        "risk_level": "risk_level", "sample_no": "sample_no", "sample_type": "sample_type",
        "feedback_no": "feedback_no", "title": "title", "priority": "priority", "type": "type",
    }
    wire_for_column = {
        "start_date": "inquiry_time", "market": "country_region", "source": "customer_source",
        "code": "customer_code", "name": "name",
    }

    def as_datetime(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        return None

    def same(left: Any, right: Any) -> bool:
        if left is None and right is None:
            return True
        if left is None or right is None:
            return False
        left_dt, right_dt = as_datetime(left), as_datetime(right)
        if left_dt is not None and right_dt is not None:
            if left_dt.tzinfo is None:
                left_dt = left_dt.replace(tzinfo=CST)
            if right_dt.tzinfo is None:
                right_dt = right_dt.replace(tzinfo=CST)
            return left_dt == right_dt
        if isinstance(left, Decimal) or isinstance(right, (int, float, Decimal)):
            try:
                return abs(float(left) - float(right)) < 0.0001
            except (TypeError, ValueError):
                pass
        if isinstance(left, date) or isinstance(right, date):
            return str(left) == str(right)
        return str(left) == str(right)

    result: dict[str, Any] = {}
    for object_type, model_rows in rows.items():
        exp = expected.get(object_type, {})
        actual: dict[str, Any] = {}
        extras = []
        for obj in model_rows:
            key = key_of(object_type, obj)
            if key in exp:
                actual[key] = obj
            else:
                extras.append(key)
        missing = [key for key in exp if key not in actual]
        mismatches: list[dict[str, Any]] = []
        for key, obj in actual.items():
            payload = exp[key]
            for column in compare_fields[object_type]:
                wire = wire_for_column.get(column, column)
                if wire not in payload:
                    continue
                expected_value = payload[wire]
                actual_value = get(obj, column_for_wire.get(column, column))
                if not same(actual_value, expected_value):
                    mismatches.append(
                        {"key": key, "field": column, "expected": expected_value, "actual": str(actual_value)}
                    )
        result[object_type] = {
            "expected": len(exp),
            "crm": len(model_rows),
            "matched": len(actual),
            "missing": missing[:20],
            "missing_count": len(missing),
            "extra_count": len(extras),
            "extra_sample": extras[:20],
            "field_mismatch_count": len(mismatches),
            "field_mismatch_sample": mismatches[:20],
        }
    return result


def _print_verify(report: dict[str, Any]) -> None:
    print("\n## 对账结果\n")
    print("| 模块 | EBMS 源记录 | 去重后对象 | CRM 记录 | 匹配 | 缺失 | 多余* | 字段不一致 |")
    print("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    labels = {
        "Customer": "客户", "Inquiry": "询价", "QuoteLibrary": "报价库",
        "Order": "订单行", "Sample": "样品", "Feedback": "问题反馈",
    }
    for object_type, row in report.items():
        print(
            f"| {labels[object_type]} | {SOURCE.get(object_type, 0)} | {row['expected']} | {row['crm']} | "
            f"{row['matched']} | {row['missing_count']} | {row['extra_count']} | {row['field_mismatch_count']} |"
        )
    print("\n* 多余：CRM 中不属于本次快照自然键的记录（迁移前既有数据/其他来源）。")
    for object_type, row in report.items():
        if row["missing"] or row["field_mismatch_sample"]:
            print(f"\n- {object_type} 缺失样例: {row['missing']}")
            print(f"- {object_type} 字段差异样例: {row['field_mismatch_sample']}")


SOURCE: dict[str, int] = {}


def main() -> None:
    parser = argparse.ArgumentParser(description="EBMS 销售中心 6 模块 → CRM 存量迁移")
    sub = parser.add_subparsers(dest="command", required=True)

    p_extract = sub.add_parser("extract", help="从 EBMS SQLite 导出快照")
    p_extract.add_argument("--ebms-db", required=True)
    p_extract.add_argument("--dump", required=True)

    p_migrate = sub.add_parser("migrate", help="构造事件并迁入 CRM")
    p_migrate.add_argument("--dump", required=True)
    p_migrate.add_argument("--direct", action="store_true", help="进程内调用入站摄入服务（默认）")
    p_migrate.add_argument("--http-url", help="改为 HTTP 调用 CRM 入站端点")
    p_migrate.add_argument("--token", help="EBMS_INBOUND_TOKEN")
    p_migrate.add_argument("--batch-size", type=int, default=500)
    p_migrate.add_argument("--dry-run", action="store_true", help="只构造事件与统计，不写库")

    p_verify = sub.add_parser("verify", help="对账 EBMS 快照 vs CRM")
    p_verify.add_argument("--dump", required=True)
    p_verify.add_argument("--json-out", help="对账 JSON 输出路径")

    p_link = sub.add_parser("link", help="按客户编码回填订单/询价/样品的公司外键")
    p_link.add_argument("--dry-run", action="store_true", help="只统计待回填行数，不写库")

    args = parser.parse_args()

    if args.command == "extract":
        counts = extract_sqlite(args.ebms_db, args.dump)
        print(json.dumps(counts, ensure_ascii=False))
        return

    if args.command == "link":
        counts = asyncio.run(_link_company_refs(args.dry_run))
        print(json.dumps({"dry_run": args.dry_run, "linked": counts}, ensure_ascii=False))
        return

    dump = load_dump(args.dump)
    events, notes = build_events(dump)
    SOURCE.update(notes["source_rows"])
    print(json.dumps({"planned": notes["planned"], "dedup": notes["dedup"], "value_maps": notes["value_maps"]},
                     ensure_ascii=False, indent=2))

    if args.command == "migrate":
        if args.dry_run:
            print(json.dumps({"dry_run": True, "events": len(events)}, ensure_ascii=False))
            return
        if args.http_url:
            if not args.token:
                raise SystemExit("HTTP 模式需要 --token（EBMS_INBOUND_TOKEN）")
            stats, errors = asyncio.run(_run_http(events, args.http_url, args.token, args.batch_size))
        else:
            stats, errors = asyncio.run(_run_direct(events, args.batch_size))
        print(json.dumps({"stats": dict(stats), "errors": errors[:20], "error_count": len(errors)},
                         ensure_ascii=False, indent=2))
        if errors:
            sys.exit(1)
        return

    report = asyncio.run(_verify(dump, events))
    _print_verify(report)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump({"notes": notes, "verify": report}, fh, ensure_ascii=False, indent=2, default=str)
        print(f"\nJSON 报告: {args.json_out}")


if __name__ == "__main__":
    main()
