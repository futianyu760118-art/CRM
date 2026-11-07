"""AEOS V7.2.2 兼容层（PAND-330，架构 §3）。

**单一实现点**：出站（``services/ebms.py`` / ``services/ebms_sync.py``）与入站
（``services/ebms_ingest.py``）共用本模块的纯函数，禁止两侧各写一份映射。

兼容标记 ``compat``（写入 ``integration_log.compat``）：

- ``L2``：原生 ``AEOS.Event.V2`` 报文；
- ``V1x``：L1 报文已携带 L2 字段（过渡期双写）；
- ``legacy``：仅含 L1 字段的旧报文，已由本模块补默认（F8-A04）。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.contracts.aeos import (
    EVENT_CONTRACT_VERSION,
    EVENT_CONTRACT_VERSION_V2,
    EXCEPTION_CONTRACT_VERSION,
    RESULT_CONTRACT_VERSION,
)

COMPAT_L2 = "L2"
COMPAT_V1X = "V1x"
COMPAT_LEGACY = "legacy"

#: L2 信封相对 L1 新增、入站旧报文需要补默认的字段（F1-A04 / F8-A04）
LEGACY_L2_FIELDS: tuple[str, ...] = (
    "object_ref",
    "correlation_id",
    "actor_id",
    "payload_version",
    "evidence_refs",
)

#: 出站风险映射：表单 3 值 → 线格式 3 值（F7-A03/Q11 双口径）
_OUTBOUND_RISK: dict[str, str] = {
    "low": "blue",
    "medium": "yellow",
    "high": "red",
    "blue": "blue",
    "yellow": "yellow",
    "red": "red",
}

#: 入站风险映射：schema 6 值 → CRM 内部 3 值（越界外值不在此表，交给值域校验拒绝）
_INBOUND_RISK: dict[str, str] = {
    "low": "blue",
    "medium": "yellow",
    "high": "red",
    "blue": "blue",
    "yellow": "yellow",
    "red": "red",
}


def object_ref_of(object_type: str | None, object_id: str | None) -> dict[str, str]:
    """由扁平 object_type/object_id 构造 ``object_ref``（F1-A06）。"""
    return {"object_type": object_type or "", "object_id": object_id or ""}


def merge_evidence(
    evidence_ids: list[str] | None = None,
    evidence_refs: list[str] | None = None,
) -> tuple[list[str], list[str]]:
    """``evidence_ids``/``evidence_refs`` 双发口径（F2-A03）。

    出站：两者内容逐项一致；入站：任一存在即接受，仅一侧时同名映射。
    """
    ids = list(evidence_ids or [])
    refs = list(evidence_refs or [])
    if not ids:
        ids = list(refs)
    if not refs:
        refs = list(ids)
    return ids, refs


def apply_legacy_defaults(event: Mapping[str, Any], *, actor_id: str = "M05") -> dict[str, Any]:
    """为仅含 L1 字段的旧事件补 L2 默认值（F1-A04 / F8-A04）。

    - ``object_ref`` ← 扁平 ``object_type/object_id``；
    - ``correlation_id`` ← ``trace_id``（并存非替代；无 trace_id 时退到 event_id）；
    - ``actor_id`` ← 发起主体未知时的系统标识（M05）；
    - ``payload_version`` ← 报文契约版本（Q4：version = payload_version）；
    - ``evidence_refs`` ← ``[]``（事件无证据引用时不得为 null）。
    """
    out = dict(event)
    out.setdefault("object_ref", object_ref_of(out.get("object_type"), out.get("object_id")))
    out.setdefault("correlation_id", out.get("trace_id") or out.get("event_id") or "")
    out.setdefault("actor_id", actor_id)
    out.setdefault("payload_version", out.get("contract_version") or "")
    out.setdefault("evidence_refs", [])
    return out


def normalize_event_v1(wire: Mapping[str, Any]) -> dict[str, Any]:
    """入站事件统一归一：V2 原样返回，V1 补齐 L2 默认值。"""
    if wire.get("contract_version") == EVENT_CONTRACT_VERSION_V2:
        return dict(wire)
    return apply_legacy_defaults(wire)


def normalize_result(wire: Mapping[str, Any]) -> dict[str, Any]:
    """入站 Result 归一：补齐 ``source/version/object_ref/evidence_refs``（F2-A01/A03）。"""
    out = dict(wire)
    out.setdefault("source", out.get("source_system") or "")
    out.setdefault("version", out.get("contract_version") or RESULT_CONTRACT_VERSION)
    out.setdefault("object_ref", object_ref_of(out.get("object_type"), out.get("object_id")))
    ids, refs = merge_evidence(out.get("evidence_ids"), out.get("evidence_refs"))
    out["evidence_ids"] = ids
    out["evidence_refs"] = refs
    return out


def normalize_exception(wire: Mapping[str, Any]) -> dict[str, Any]:
    """入站 Exception 归一（F2-A02）。"""
    out = dict(wire)
    out.setdefault("source", out.get("source_system") or "")
    out.setdefault("version", out.get("contract_version") or EXCEPTION_CONTRACT_VERSION)
    out.setdefault("object_ref", object_ref_of(out.get("object_type"), out.get("object_id")))
    ids, refs = merge_evidence(out.get("evidence_ids"), out.get("evidence_refs"))
    out["evidence_ids"] = ids
    out["evidence_refs"] = refs
    return out


def normalize_outbound(payload: Mapping[str, Any]) -> dict[str, Any]:
    """出站投递前归一：Result/Exception 补 L2 增补字段；V1 事件原样（L1 严格端不收额外字段）。"""
    version = payload.get("contract_version")
    if version == RESULT_CONTRACT_VERSION:
        return normalize_result(payload)
    if version == EXCEPTION_CONTRACT_VERSION:
        return normalize_exception(payload)
    return dict(payload)


def compat_marker(wire: Mapping[str, Any]) -> str:
    """兼容标记：``L2`` / ``V1x`` / ``legacy``。"""
    version = wire.get("contract_version")
    if version == EVENT_CONTRACT_VERSION_V2:
        return COMPAT_L2
    if version == EVENT_CONTRACT_VERSION:
        missing = [field for field in LEGACY_L2_FIELDS if field not in wire]
        return COMPAT_LEGACY if missing else COMPAT_V1X
    return COMPAT_V1X


def version_of_payload(payload_version: str | None) -> str:
    """Q4：Event ``version`` 与 ``payload_version`` 同义，实现取 payload_version。"""
    return payload_version or ""


def to_outbound_risk(value: str | None) -> str | None:
    """出站 order risk：表单值 ``low/medium/high`` → 线格式 ``blue/yellow/red``。"""
    if value is None:
        return None
    return _OUTBOUND_RISK.get(value, value)


def to_inbound_risk(value: str | None) -> str | None:
    """入站 order risk：schema 6 值 → CRM 内部 3 值（未知值原样返回，由校验拒绝）。"""
    if value is None:
        return None
    return _INBOUND_RISK.get(value, value)


def normalize_inbound_payload(event_type: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """入站 payload 值域映射（Q11：入站接受 6 值并映射到内部 3 值）。"""
    out = dict(payload)
    if event_type == "order.upserted" and "risk_level" in out:
        out["risk_level"] = to_inbound_risk(out.get("risk_level"))
    return out
