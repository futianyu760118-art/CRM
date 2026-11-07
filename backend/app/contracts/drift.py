"""CRM 常量 vs 冻结 schema 枚举的漂移检查（PAND-330，F7-A03/F7-A05）。

权威 = `contracts/schema/aeos-contracts-v1.schema.json`（EBMS 1d10853 快照）。
本模块只读、无副作用，供 `tests/test_pand330_drift.py` 纳入常规回归。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.contracts.aeos import (
    EVENT_TYPES,
    EVENT_VALUE_DOMAINS,
    EXCEPTION_STATUSES,
    INBOUND_VALUE_DOMAINS,
    RESULT_STATUSES,
    SEVERITY_LEVELS,
)
from app.domain.aeos_ledger import L1_EVENT_TYPES

SCHEMA_PATH = Path(__file__).with_name("schema") / "aeos-contracts-v1.schema.json"

#: CRM 值域键 → schema `$defs` 名（12 个 Event 值域 + 3 个核心值域 + 事件枚举）
DOMAIN_TO_SCHEMA: dict[str, str] = {
    "customer_level": "customer_level",
    "sales_mode": "sales_mode",
    "customer_status": "customer_status",
    "inquiry_certificate_level": "inquiry_certificate_level",
    "quote_library_certificate_level": "quote_library_certificate_level",
    "inquiry_status": "inquiry_status",
    "order_status": "order_status",
    # 双口径（Q11）：入站接受域与 schema 6 值集合相等；出站为其 3 值子集
    "order_risk_level": "order_risk_level",
    "sample_status": "sample_status",
    "feedback_type": "feedback_type",
    "feedback_priority": "feedback_priority",
    "feedback_status": "feedback_status",
    "result_status": "result_status",
    "exception_status": "exception_status",
    "exception_severity": "exception_severity",
}

_CORE_DOMAINS: dict[str, tuple[str, ...]] = {
    "result_status": RESULT_STATUSES,
    "exception_status": EXCEPTION_STATUSES,
    "exception_severity": SEVERITY_LEVELS,
}


@dataclass(frozen=True)
class DriftDiff:
    domain: str
    schema_only: list[str] = field(default_factory=list)
    crm_only: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DriftReport:
    checked: int
    diffs: list[DriftDiff]

    @property
    def ok(self) -> bool:
        return not self.diffs


def load_schema(path: Path | None = None) -> dict[str, Any]:
    with (path or SCHEMA_PATH).open(encoding="utf-8") as fh:
        return json.load(fh)


def _schema_enum(schema: dict[str, Any], name: str) -> list[str]:
    return list(schema["$defs"][name]["enum"])


def _crm_domain(key: str) -> tuple[str, ...]:
    if key == "order_risk_level":
        return INBOUND_VALUE_DOMAINS[key]
    if key in _CORE_DOMAINS:
        return _CORE_DOMAINS[key]
    return EVENT_VALUE_DOMAINS[key]


def check_drift(schema: dict[str, Any] | None = None) -> DriftReport:
    """逐域比较集合相等性，返回差异清单（空 = 无漂移）。"""
    schema = schema or load_schema()
    diffs: list[DriftDiff] = []

    for key, schema_name in DOMAIN_TO_SCHEMA.items():
        expected = set(_schema_enum(schema, schema_name))
        actual = set(_crm_domain(key))
        if expected != actual:
            diffs.append(
                DriftDiff(
                    domain=key,
                    schema_only=sorted(expected - actual),
                    crm_only=sorted(actual - expected),
                )
            )

    schema_events = set(_schema_enum(schema, "event_type"))
    if schema_events != set(L1_EVENT_TYPES):
        diffs.append(
            DriftDiff(
                domain="event_type",
                schema_only=sorted(schema_events - set(L1_EVENT_TYPES)),
                crm_only=sorted(set(L1_EVENT_TYPES) - schema_events),
            )
        )
    if set(EVENT_TYPES) != set(L1_EVENT_TYPES):
        diffs.append(
            DriftDiff(
                domain="event_types_declared",
                schema_only=sorted(set(L1_EVENT_TYPES) - set(EVENT_TYPES)),
                crm_only=sorted(set(EVENT_TYPES) - set(L1_EVENT_TYPES)),
            )
        )

    # 出站风险域必须是 schema 6 值的子集（Q11 双口径）
    outbound_risk = set(EVENT_VALUE_DOMAINS["order_risk_level"])
    inbound_risk = set(INBOUND_VALUE_DOMAINS["order_risk_level"])
    if not outbound_risk <= inbound_risk:
        diffs.append(
            DriftDiff(
                domain="order_risk_level_outbound_subset",
                crm_only=sorted(outbound_risk - inbound_risk),
            )
        )

    return DriftReport(checked=len(DOMAIN_TO_SCHEMA) + 2, diffs=diffs)


def assert_no_drift(schema: dict[str, Any] | None = None) -> None:
    """差异即失败（Contract Test 入口）。"""
    report = check_drift(schema)
    if not report.ok:
        detail = "; ".join(
            f"{d.domain}: schema_only={d.schema_only} crm_only={d.crm_only}" for d in report.diffs
        )
        raise AssertionError(f"AEOS 值域漂移: {detail}")
