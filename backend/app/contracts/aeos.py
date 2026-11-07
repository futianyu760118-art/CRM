"""AEOS 契约族（Event / Result / Exception）—— CRM 侧模型与校验。

## 契约基线来源（已确认，PAND-330 / F7-A01）

- 取值域与枚举的唯一权威：EBMS `contracts/aeos-contracts-v1.schema.json`（1d10853）。
  CRM 侧钉死快照见 `contracts/schema/aeos-contracts-v1.schema.json`，漂移检查见
  `contracts/drift.py`。
- 字段集基线：`contracts/aeos-contracts-v1.examples.json` + `README.md`。

## 演进策略（架构 §2）

1. Event：新增 `AEOS.Event.V2` 独立信封承载 L2 字段；L1 `AEOS.Event.V1` 一字不改
   （冻结 schema `event_envelope` 为 ``additionalProperties:false``）。
2. Result / Exception：沿用 V1 信封增补 `source/version/object_ref/evidence_refs`
   （schema 未禁额外字段，次版本 V1.x）。
3. 入站旧报文由 `contracts.compat` 补默认后校验，不因未知字段拒收（F8-A04）。
4. 值域校验在 `validate_contract(..., direction=...)` 中统一生效：出站按 3 值风险域，
   入站接受 6 值并按兼容层映射（Q11）。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic import ValidationError as PydanticValidationError

from app.core.error_codes import ErrCode
from app.core.exceptions import ApiError
from app.domain.aeos_ledger import L2_CHANNEL, is_registered
from app.domain.state_machine import (
    CUSTOMER_LEVELS,
    CUSTOMER_STATUSES,
    FEEDBACK_PRIORITIES,
    FEEDBACK_STATUSES,
    FEEDBACK_TYPES,
    INQUIRY_CERTIFICATE_LEVELS,
    INQUIRY_STATUSES_V2,
    ORDER_RISK_FILTER,
    ORDER_STATUSES,
    QUOTE_LIBRARY_CERTIFICATE_LEVELS,
    SALES_MODES,
    SAMPLE_STATUSES,
)

RESULT_CONTRACT_VERSION = "AEOS.Result.V1"
EXCEPTION_CONTRACT_VERSION = "AEOS.Exception.V1"
EVENT_CONTRACT_VERSION = "AEOS.Event.V1"
EVENT_CONTRACT_VERSION_V2 = "AEOS.Event.V2"

#: 冻结 schema `result_status`（F7-A02，逐字）
RESULT_STATUSES: tuple[str, ...] = ("VERIFIED",)
#: 冻结 schema `exception_status`（F7-A02，逐字）
EXCEPTION_STATUSES: tuple[str, ...] = ("OPEN",)
#: 冻结 schema `exception_severity`（F7-A02，逐字）
SEVERITY_LEVELS: tuple[str, ...] = ("low", "medium", "high", "critical")


class ContractValidationError(ApiError):
    """契约校验失败（字段缺失 / 取值越界 / 版本未知）。"""

    def __init__(self, message: str, data: object | None = None) -> None:
        super().__init__(ErrCode.CONTRACT_INVALID, message, http_status=422, data=data)


class AeosPeriod(BaseModel):
    """统计区间（闭区间语义，精度到日）。"""

    model_config = ConfigDict(extra="allow")

    start: date
    end: date

    @model_validator(mode="after")
    def _validate_range(self) -> AeosPeriod:
        if self.end < self.start:
            raise ValueError("period.end 不得早于 period.start")
        return self


class AeosMetric(BaseModel):
    """专业指标：必须携带计算口径版本，避免多系统多答案。"""

    model_config = ConfigDict(extra="allow")

    code: str = Field(min_length=1, max_length=100)
    value: float
    unit: str = Field(min_length=1, max_length=50)
    calculation_version: str = Field(min_length=1, max_length=100)


class AeosObjectRef(BaseModel):
    """对象引用：1:1 唯一定位（F1-A06）。"""

    model_config = ConfigDict(extra="allow")

    object_type: str = Field(min_length=1, max_length=50)
    object_id: str = Field(min_length=1, max_length=100)


class AeosResultContract(BaseModel):
    """AEOS.Result.V1 —— 经营/专业结果（L2 增补字段 V1.x）。

    L1 必填集保持：``source_system/object_type/object_id/evidence_ids``；
    L2 增补：``source/version/object_ref/evidence_refs``（F2-A01）。
    """

    model_config = ConfigDict(extra="allow")

    contract_version: Literal["AEOS.Result.V1"]
    result_id: str = Field(min_length=1, max_length=100)
    source: str = Field(min_length=1, max_length=30)
    source_system: str = Field(min_length=1, max_length=30)
    version: str = Field(min_length=1, max_length=100)
    object_ref: AeosObjectRef
    object_type: str = Field(min_length=1, max_length=50)
    object_id: str = Field(min_length=1, max_length=100)
    period: AeosPeriod
    metric: AeosMetric
    status: str
    evidence_ids: list[str]
    evidence_refs: list[str]
    trace_id: str = Field(min_length=1, max_length=100)
    occurred_at: datetime

    @model_validator(mode="after")
    def _validate_fields(self) -> AeosResultContract:
        if self.status not in RESULT_STATUSES:
            raise ValueError(f"status 取值越界，允许: {list(RESULT_STATUSES)}")
        if self.source != self.source_system:
            raise ValueError("source 与 source_system 过渡期必须同值（F2-A01）")
        if self.object_ref.object_type != self.object_type or self.object_ref.object_id != self.object_id:
            raise ValueError("object_ref 必须与 object_type/object_id 一致（F1-A06）")
        if self.evidence_refs != self.evidence_ids:
            raise ValueError("evidence_refs 与 evidence_ids 过渡期必须逐项相等（F2-A03）")
        return self

    @property
    def contract_id(self) -> str:
        return self.result_id


class AeosExceptionContract(BaseModel):
    """AEOS.Exception.V1 —— 异常/风险（L2 增补字段 V1.x，F2-A02）。"""

    model_config = ConfigDict(extra="allow")

    contract_version: Literal["AEOS.Exception.V1"]
    exception_id: str = Field(min_length=1, max_length=100)
    source: str = Field(min_length=1, max_length=30)
    source_system: str = Field(min_length=1, max_length=30)
    version: str = Field(min_length=1, max_length=100)
    object_ref: AeosObjectRef
    object_type: str = Field(min_length=1, max_length=50)
    object_id: str = Field(min_length=1, max_length=100)
    severity: str
    reason_code: str = Field(min_length=1, max_length=50)
    status: str
    evidence_ids: list[str]
    evidence_refs: list[str]
    trace_id: str = Field(min_length=1, max_length=100)
    occurred_at: datetime

    @model_validator(mode="after")
    def _validate_enums(self) -> AeosExceptionContract:
        if self.severity not in SEVERITY_LEVELS:
            raise ValueError(f"severity 取值越界，允许: {list(SEVERITY_LEVELS)}")
        if self.status not in EXCEPTION_STATUSES:
            raise ValueError(f"status 取值越界，允许: {list(EXCEPTION_STATUSES)}")
        if self.source != self.source_system:
            raise ValueError("source 与 source_system 过渡期必须同值（F2-A02）")
        if self.object_ref.object_type != self.object_type or self.object_ref.object_id != self.object_id:
            raise ValueError("object_ref 必须与 object_type/object_id 一致（F1-A06）")
        if self.evidence_refs != self.evidence_ids:
            raise ValueError("evidence_refs 与 evidence_ids 过渡期必须逐项相等（F2-A03）")
        return self

    @property
    def contract_id(self) -> str:
        return self.exception_id


# 契约模型注册表在文件末尾（Event 契约类定义之后）统一组装，见 `_CONTRACT_MODELS`。


def _error_data(exc: PydanticValidationError) -> list[dict[str, Any]]:
    return [
        {"field": ".".join(str(p) for p in err["loc"]), "type": err["type"], "message": err["msg"]}
        for err in exc.errors()
    ]


# ---------------------------------------------------------------------------
# 值域校验（F7-A03/F7-A04）：schema 为唯一权威
#
# order_risk_level 采用双口径（Q11）：出站仍只有 3 值（blue/yellow/red），
# 入站接受 schema 6 值并由 contracts.compat 映射到内部 3 值。
# ---------------------------------------------------------------------------

def validate_contract(payload: Mapping[str, Any], *, direction: str = "outbound") -> AeosContract:
    """按 contract_version 分派校验，返回强类型契约对象。

    - ``direction="outbound"``：出站构造，缺 L2 字段即拒（F2-A01）；
    - ``direction="inbound"``：入站兼容，调用方须先经 ``contracts.compat`` 归一。
    值域越界（F7-A04）返回字段路径 + 实际值，HTTP 422。
    """
    version = payload.get("contract_version")
    model = _CONTRACT_MODELS.get(version) if isinstance(version, str) else None
    if model is None:
        raise ContractValidationError(
            f"未知契约版本: {version!r}",
            {"supported_versions": sorted(_CONTRACT_MODELS)},
        )
    try:
        contract = model.model_validate(payload)
    except PydanticValidationError as exc:
        raise ContractValidationError("契约字段校验失败", _error_data(exc)) from exc

    if isinstance(contract, (AeosEventContract, AeosEventV2Contract)):
        event_type = str(payload.get("event_type", ""))
        if isinstance(contract, AeosEventV2Contract) and not is_registered(event_type, L2_CHANNEL):
            raise ContractValidationError(
                "L2 事件类型未在台账登记（F1-A05）",
                [{"field": "event_type", "type": "value_error", "message": f"未登记: {event_type!r}"}],
            )
        violations = _domain_violations(event_type, payload.get("payload") or {}, direction)
        if violations:
            raise ContractValidationError("契约值域校验失败", violations)
    return contract


def unknown_fields(payload: Mapping[str, Any]) -> list[str]:
    """返回契约未声明的顶层字段（联调期用于暴露漂移，不影响投递）。"""
    version = payload.get("contract_version")
    model = _CONTRACT_MODELS.get(version) if isinstance(version, str) else None
    if model is None:
        return sorted(str(k) for k in payload)
    declared = set(model.model_fields)
    return sorted(str(k) for k in payload if k not in declared)


def to_wire(contract: AeosContract) -> dict[str, Any]:
    """序列化为跨系统线格式：日期 `YYYY-MM-DD`、时间戳含时区偏移。"""
    return contract.model_dump(mode="json")


def build_result_contract(
    *,
    result_id: str,
    source_system: str,
    object_type: str,
    object_id: str,
    period_start: date,
    period_end: date,
    metric_code: str,
    metric_value: float,
    metric_unit: str,
    calculation_version: str,
    evidence_ids: list[str],
    trace_id: str,
    occurred_at: datetime,
    status: str = RESULT_STATUSES[0],
    source: str | None = None,
    version: str | None = None,
    evidence_refs: list[str] | None = None,
    extra: Mapping[str, Any] | None = None,
) -> AeosResultContract:
    """构造并校验 Result 契约，保证产出即合规。

    L2 增补字段自动补齐：``source``=source_system、``version``=契约版本、
    ``object_ref``=扁平两字段、``evidence_refs``=evidence_ids（F2-A01/A03）。
    """
    refs = list(evidence_refs) if evidence_refs is not None else list(evidence_ids)
    payload: dict[str, Any] = {
        "contract_version": RESULT_CONTRACT_VERSION,
        "result_id": result_id,
        "source": source or source_system,
        "source_system": source_system,
        "version": version or RESULT_CONTRACT_VERSION,
        "object_ref": {"object_type": object_type, "object_id": object_id},
        "object_type": object_type,
        "object_id": object_id,
        "period": {"start": period_start, "end": period_end},
        "metric": {
            "code": metric_code,
            "value": metric_value,
            "unit": metric_unit,
            "calculation_version": calculation_version,
        },
        "status": status,
        "evidence_ids": list(evidence_ids),
        "evidence_refs": refs,
        "trace_id": trace_id,
        "occurred_at": occurred_at,
    }
    if extra:
        payload.update(extra)
    return validate_contract(payload)  # type: ignore[return-value]


def build_exception_contract(
    *,
    exception_id: str,
    source_system: str,
    object_type: str,
    object_id: str,
    severity: str,
    reason_code: str,
    evidence_ids: list[str],
    trace_id: str,
    occurred_at: datetime,
    status: str = EXCEPTION_STATUSES[0],
    source: str | None = None,
    version: str | None = None,
    evidence_refs: list[str] | None = None,
    extra: Mapping[str, Any] | None = None,
) -> AeosExceptionContract:
    """构造并校验 Exception 契约（L2 增补字段自动补齐，F2-A02/A03）。"""
    refs = list(evidence_refs) if evidence_refs is not None else list(evidence_ids)
    payload: dict[str, Any] = {
        "contract_version": EXCEPTION_CONTRACT_VERSION,
        "exception_id": exception_id,
        "source": source or source_system,
        "source_system": source_system,
        "version": version or EXCEPTION_CONTRACT_VERSION,
        "object_ref": {"object_type": object_type, "object_id": object_id},
        "object_type": object_type,
        "object_id": object_id,
        "severity": severity,
        "reason_code": reason_code,
        "status": status,
        "evidence_ids": list(evidence_ids),
        "evidence_refs": refs,
        "trace_id": trace_id,
        "occurred_at": occurred_at,
    }
    if extra:
        payload.update(extra)
    return validate_contract(payload)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# AEOS.Event.V1 —— 实体同步信封（PAND-249：CRM ↔ EBMS 双向同步）
#
# 契约冻结版 §4：13 种事件 = 6 个业务实体 × {upserted, deleted} + dictionary.upserted。
# 幂等键 = {target_system}:{event_type}:{object_id}:{fingerprint}；
# fingerprint = sha1(canonical(event 去掉 occurred_at/event_id/trace_id/idempotency_key))[:16]，
# canonical = UTF-8、键排序、无空格，标量原样保留（仅 datetime/date 转 ISO 字符串）。
# ---------------------------------------------------------------------------

#: 可同步的对象类型（PascalCase，契约 §4.1 冻结；dictionary 仅 upserted，不产生 deleted）
EVENT_OBJECT_TYPES: tuple[str, ...] = (
    "Customer",
    "Inquiry",
    "QuoteLibrary",
    "Order",
    "Sample",
    "Feedback",
    "Dictionary",
)

#: object_type（PascalCase）→ event_type 前缀（小写，§4.1 冻结 13 事件）
_OBJECT_EVENT_BASE: dict[str, str] = {
    "Customer": "customer",
    "Inquiry": "inquiry",
    "QuoteLibrary": "quote_library",
    "Order": "order",
    "Sample": "sample",
    "Feedback": "feedback",
    "Dictionary": "dictionary",
}

ENTITY_UPSERT_EVENTS: tuple[str, ...] = tuple(f"{_OBJECT_EVENT_BASE[t]}.upserted" for t in EVENT_OBJECT_TYPES)
ENTITY_DELETE_EVENTS: tuple[str, ...] = tuple(
    f"{_OBJECT_EVENT_BASE[t]}.deleted" for t in EVENT_OBJECT_TYPES if t != "Dictionary"
)
EVENT_TYPES: tuple[str, ...] = ENTITY_UPSERT_EVENTS + ENTITY_DELETE_EVENTS


def upsert_event_for(object_type: str) -> str:
    base = _OBJECT_EVENT_BASE.get(object_type)
    if base is None:
        raise ValueError(f"未知对象类型: {object_type!r}")
    return f"{base}.upserted"


def delete_event_for(object_type: str) -> str:
    if object_type not in EVENT_OBJECT_TYPES or object_type == "Dictionary":
        raise ValueError(f"{object_type!r} 不产生 deleted 事件")
    return f"{_OBJECT_EVENT_BASE[object_type]}.deleted"


#: 取值域（单一事实来源 = app.domain.state_machine）
EVENT_VALUE_DOMAINS: dict[str, tuple[str, ...]] = {
    "customer_level": tuple(CUSTOMER_LEVELS),
    "sales_mode": tuple(SALES_MODES),
    "customer_status": tuple(CUSTOMER_STATUSES),
    "inquiry_certificate_level": tuple(INQUIRY_CERTIFICATE_LEVELS),
    "quote_library_certificate_level": tuple(QUOTE_LIBRARY_CERTIFICATE_LEVELS),
    "inquiry_status": tuple(INQUIRY_STATUSES_V2),
    "order_status": tuple(ORDER_STATUSES),
    "order_risk_level": tuple(ORDER_RISK_FILTER),
    "sample_status": tuple(SAMPLE_STATUSES),
    "feedback_type": tuple(FEEDBACK_TYPES),
    "feedback_priority": tuple(FEEDBACK_PRIORITIES),
    "feedback_status": tuple(FEEDBACK_STATUSES),
}


#: 入站接受域：除 order_risk_level 外与出站一致
INBOUND_VALUE_DOMAINS: dict[str, tuple[str, ...]] = {
    **EVENT_VALUE_DOMAINS,
    "order_risk_level": ("blue", "yellow", "red", "low", "medium", "high"),
}

#: event_type → {payload 字段路径: 值域键}；`items[].xxx` 表示逐个明细行校验
PAYLOAD_DOMAIN_FIELDS: dict[str, dict[str, str]] = {
    "customer.upserted": {
        "customer_level": "customer_level",
        "sales_mode": "sales_mode",
        "customer_status": "customer_status",
    },
    "inquiry.upserted": {
        "status": "inquiry_status",
        "items[].certificate_level": "inquiry_certificate_level",
    },
    "quote_library.upserted": {"certificate_level": "quote_library_certificate_level"},
    "order.upserted": {"status": "order_status", "risk_level": "order_risk_level"},
    "sample.upserted": {"status": "sample_status"},
    "feedback.upserted": {
        "type": "feedback_type",
        "priority": "feedback_priority",
        "status": "feedback_status",
    },
}


def _domain_violations(event_type: str, payload: Mapping[str, Any], direction: str) -> list[dict[str, Any]]:
    domains = INBOUND_VALUE_DOMAINS if direction == "inbound" else EVENT_VALUE_DOMAINS
    spec = PAYLOAD_DOMAIN_FIELDS.get(event_type)
    if not spec:
        return []
    errors: list[dict[str, Any]] = []
    for path, domain_key in spec.items():
        allowed = domains.get(domain_key, ())
        if "[]." in path:
            field, sub = path.split("[].", 1)
            rows = payload.get(field)
            if not isinstance(rows, list):
                continue
            targets = [(f"{field}[{idx}].{sub}", row.get(sub)) for idx, row in enumerate(rows) if isinstance(row, dict)]
        else:
            if path not in payload:
                continue
            targets = [(path, payload.get(path))]
        for field_path, value in targets:
            if value is None:
                continue
            if value not in allowed:
                errors.append(
                    {
                        "field": f"payload.{field_path}",
                        "type": "value_error",
                        "message": f"取值越界: {value!r}，允许: {list(allowed)}",
                    }
                )
    return errors


class AeosEventContract(BaseModel):
    """AEOS.Event.V1 —— 实体增删改事件（含完整实体 payload）。"""

    model_config = ConfigDict(extra="allow")

    contract_version: Literal["AEOS.Event.V1"]
    event_id: str = Field(min_length=1, max_length=100)
    event_type: str = Field(min_length=1, max_length=100)
    source_system: str = Field(min_length=1, max_length=30)
    object_type: str = Field(min_length=1, max_length=50)
    object_id: str = Field(min_length=1, max_length=100)
    operation: Literal["UPSERT", "DELETE"]
    occurred_at: datetime
    trace_id: str = Field(min_length=1, max_length=100)
    payload: dict[str, Any]
    #: 幂等键（{target}:{event_type}:{object_id}:{fingerprint}），随报文体下发（EBMS 头/体一致）
    idempotency_key: str | None = None

    @model_validator(mode="after")
    def _validate_enums(self) -> AeosEventContract:
        if self.object_type not in EVENT_OBJECT_TYPES:
            raise ValueError(f"object_type 取值越界: {self.object_type!r}")
        if self.event_type not in EVENT_TYPES:
            raise ValueError(f"event_type 取值越界: {self.event_type!r}")
        suffix = "upserted" if self.operation == "UPSERT" else "deleted"
        expected = f"{_OBJECT_EVENT_BASE[self.object_type]}.{suffix}"
        if self.event_type != expected:
            raise ValueError(f"event_type 与 object_type/operation 不一致: 期望 {expected!r}, 实际 {self.event_type!r}")
        return self

    @property
    def contract_id(self) -> str:
        return self.event_id


def build_event_contract(
    *,
    event_id: str,
    event_type: str,
    source_system: str,
    object_type: str,
    object_id: str,
    operation: str,
    payload: Mapping[str, Any],
    trace_id: str,
    occurred_at: datetime,
) -> AeosEventContract:
    """构造并校验 Event 契约，保证产出即合规。"""
    return validate_contract(  # type: ignore[return-value]
        {
            "contract_version": EVENT_CONTRACT_VERSION,
            "event_id": event_id,
            "event_type": event_type,
            "source_system": source_system,
            "object_type": object_type,
            "object_id": object_id,
            "operation": operation,
            "occurred_at": occurred_at,
            "trace_id": trace_id,
            "payload": dict(payload),
        }
    )


# ---------------------------------------------------------------------------
# AEOS.Event.V2 —— L2 业务事件独立信封（F1-A01，架构 §2.2）
#
# 与 L1 信封永久并行：V1 继续承载 CRM↔EBMS 6 实体同步（13 事件），V2 承载 L2
# 业务事件（PascalCase，须在 domain/aeos_ledger.py 登记后方可发布）。
# ---------------------------------------------------------------------------


class AeosEventV2Contract(BaseModel):
    """AEOS.Event.V2 —— L2 业务事件（12 项必填 + 可选 ``trace_id`` 技术调用链）。"""

    model_config = ConfigDict(extra="allow")

    contract_version: Literal["AEOS.Event.V2"]
    event_id: str = Field(min_length=1, max_length=100)
    event_type: str = Field(min_length=1, max_length=100)
    occurred_at: datetime
    #: 线格式只用 module_id（F6-A04）；``CRM`` 仅用于文档/台账
    source_system: Literal["M05"]
    object_ref: AeosObjectRef
    correlation_id: str = Field(min_length=1, max_length=100)
    causation_id: str | None = None
    actor_id: str = Field(min_length=1, max_length=100)
    payload_version: str = Field(min_length=1, max_length=100)
    payload: dict[str, Any]
    evidence_refs: list[str]
    idempotency_key: str = Field(min_length=1, max_length=300)
    #: 技术调用链（F1-A04 补充：与 correlation_id 语义并存）
    trace_id: str | None = Field(default=None, max_length=100)

    @property
    def contract_id(self) -> str:
        return self.event_id


def build_event_v2_contract(
    *,
    event_id: str,
    event_type: str,
    object_type: str,
    object_id: str,
    payload: Mapping[str, Any],
    occurred_at: datetime,
    correlation_id: str,
    actor_id: str,
    payload_version: str,
    evidence_refs: list[str] | None = None,
    causation_id: str | None = None,
    trace_id: str | None = None,
    source_system: str = "M05",
    idempotency_key: str | None = None,
    target_system: str = "EBMS",
) -> AeosEventV2Contract:
    """构造并校验 L2 事件；未提供幂等键时按 V2 公式自动计算。"""
    payload_dict: dict[str, Any] = {
        "contract_version": EVENT_CONTRACT_VERSION_V2,
        "event_id": event_id,
        "event_type": event_type,
        "occurred_at": occurred_at,
        "source_system": source_system,
        "object_ref": {"object_type": object_type, "object_id": object_id},
        "correlation_id": correlation_id,
        "causation_id": causation_id,
        "actor_id": actor_id,
        "payload_version": payload_version,
        "payload": dict(payload),
        "evidence_refs": list(evidence_refs or []),
        "idempotency_key": idempotency_key or "",
        "trace_id": trace_id,
    }
    if not payload_dict["idempotency_key"]:
        payload_dict["idempotency_key"] = event_v2_idempotency_key(target_system, payload_dict)
    return validate_contract(payload_dict)  # type: ignore[return-value]


def _canonicalize(value: Any) -> Any:
    """规整为稳定可序列化形态：键排序，datetime/date → ISO 字符串，其余标量原样保留。

    对齐 EBMS 整包口径：bool/None/int/str/float 均以 JSON 原生字面量参与指纹，
    不做字符串化（避免两侧序列化差异导致指纹不一致）。
    """
    if isinstance(value, dict):
        return {str(k): _canonicalize(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [_canonicalize(v) for v in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def canonical_json(payload: Mapping[str, Any]) -> str:
    """指纹 canonical 序列化：UTF-8、递归键排序、无空格、非 ASCII 原样、JSON 原生类型。"""
    return json.dumps(_canonicalize(payload), ensure_ascii=False, separators=(",", ":"))


#: 指纹计算需剔除的易变/派生字段（对齐 EBMS 整包口径 §4.1）
_FINGERPRINT_EXCLUDED_FIELDS = frozenset({"occurred_at", "event_id", "trace_id", "idempotency_key"})


def event_fingerprint(event: Mapping[str, Any]) -> str:
    """事件内容指纹：整包口径，剔除 occurred_at / event_id / trace_id / idempotency_key。"""
    stable = {k: v for k, v in event.items() if k not in _FINGERPRINT_EXCLUDED_FIELDS}
    return hashlib.sha1(canonical_json(stable).encode("utf-8")).hexdigest()[:16]


def event_idempotency_key(target_system: str, event: Mapping[str, Any]) -> str:
    """幂等键 = {target_system}:{event_type}:{object_id}:{fingerprint}。

    L1/V2 共用同一公式（F8-A02）：V2 的 object_id 取自 ``object_ref.object_id``，
    指纹剔除集仍为 ``occurred_at/event_id/trace_id/idempotency_key``。
    """
    return ":".join(
        [
            target_system,
            str(event.get("event_type", "")),
            str(event.get("object_id", "")),
            event_fingerprint(event),
        ]
    )


def event_v2_idempotency_key(target_system: str, event: Mapping[str, Any]) -> str:
    """L2 事件幂等键：公式不变，``object_id`` 由 ``object_ref`` 派生。"""
    ref = event.get("object_ref")
    object_id = ref.get("object_id", "") if isinstance(ref, Mapping) else ""
    return ":".join(
        [
            target_system,
            str(event.get("event_type", "")),
            str(object_id),
            event_fingerprint(event),
        ]
    )


# ---------------------------------------------------------------------------
# 契约模型注册表（所有契约类定义完毕后再组装）
# ---------------------------------------------------------------------------

AeosContract = AeosResultContract | AeosExceptionContract | AeosEventContract | AeosEventV2Contract

_CONTRACT_MODELS: dict[str, Any] = {
    RESULT_CONTRACT_VERSION: AeosResultContract,
    EXCEPTION_CONTRACT_VERSION: AeosExceptionContract,
    EVENT_CONTRACT_VERSION: AeosEventContract,
    EVENT_CONTRACT_VERSION_V2: AeosEventV2Contract,
}
