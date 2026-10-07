"""AEOS 契约族（Result / Exception）—— CRM 侧模型与校验。

## 契约基线来源

- `EBMS/contracts/aeos-contracts-v1.examples.json`（字段集权威基线）
- `EBMS/contracts/README.md`（通用字段：contract_version / id / source_system /
  object_type / object_id / occurred_at / status / trace_id / evidence_ids）

## 基线缺口（需总控确认）

EBMS 仓库当前**不存在** `contracts/aeos-contracts-v1.schema.json`，因此基线只提供
「单条样例」而非「取值域」。本模块的处理原则：

1. 字段集严格对齐 examples.json —— 样例出现的字段全部必填，不增不减。
2. 取值域只采用样例中**实际出现**的取值（见 `RESULT_STATUSES` / `EXCEPTION_STATUSES`），
   不臆造扩展值；`SEVERITY_LEVELS` 为唯一推断项（样例仅示 `high`），已显式标注。
3. 未知字段一律保留（README 定义通用字段为「至少包含」），不静默丢弃。
4. 待 EBMS 补全 schema.json 后，只需收敛下方取值域常量即可，无需改动模型结构。
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic import ValidationError as PydanticValidationError

from app.core.error_codes import ErrCode
from app.core.exceptions import ApiError

RESULT_CONTRACT_VERSION = "AEOS.Result.V1"
EXCEPTION_CONTRACT_VERSION = "AEOS.Exception.V1"

#: 基线 examples.json 中 Result.status 的实际取值（未做扩展）
RESULT_STATUSES: tuple[str, ...] = ("VERIFIED",)
#: 基线 examples.json 中 Exception.status 的实际取值（未做扩展）
EXCEPTION_STATUSES: tuple[str, ...] = ("OPEN",)
#: 基线样例仅示 "high"；四级刻度为投递侧推断，待总控确认
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


class AeosResultContract(BaseModel):
    """AEOS.Result.V1 —— 经营/专业结果。"""

    model_config = ConfigDict(extra="allow")

    contract_version: Literal["AEOS.Result.V1"]
    result_id: str = Field(min_length=1, max_length=100)
    source_system: str = Field(min_length=1, max_length=30)
    object_type: str = Field(min_length=1, max_length=50)
    object_id: str = Field(min_length=1, max_length=100)
    period: AeosPeriod
    metric: AeosMetric
    status: str
    evidence_ids: list[str]
    trace_id: str = Field(min_length=1, max_length=100)
    occurred_at: datetime

    @model_validator(mode="after")
    def _validate_status(self) -> AeosResultContract:
        if self.status not in RESULT_STATUSES:
            raise ValueError(f"status 取值越界，允许: {list(RESULT_STATUSES)}")
        return self

    @property
    def contract_id(self) -> str:
        return self.result_id


class AeosExceptionContract(BaseModel):
    """AEOS.Exception.V1 —— 异常/风险。"""

    model_config = ConfigDict(extra="allow")

    contract_version: Literal["AEOS.Exception.V1"]
    exception_id: str = Field(min_length=1, max_length=100)
    source_system: str = Field(min_length=1, max_length=30)
    object_type: str = Field(min_length=1, max_length=50)
    object_id: str = Field(min_length=1, max_length=100)
    severity: str
    reason_code: str = Field(min_length=1, max_length=50)
    status: str
    evidence_ids: list[str]
    trace_id: str = Field(min_length=1, max_length=100)
    occurred_at: datetime

    @model_validator(mode="after")
    def _validate_enums(self) -> AeosExceptionContract:
        if self.severity not in SEVERITY_LEVELS:
            raise ValueError(f"severity 取值越界，允许: {list(SEVERITY_LEVELS)}")
        if self.status not in EXCEPTION_STATUSES:
            raise ValueError(f"status 取值越界，允许: {list(EXCEPTION_STATUSES)}")
        return self

    @property
    def contract_id(self) -> str:
        return self.exception_id


AeosContract = AeosResultContract | AeosExceptionContract

_CONTRACT_MODELS: dict[str, type[AeosResultContract] | type[AeosExceptionContract]] = {
    RESULT_CONTRACT_VERSION: AeosResultContract,
    EXCEPTION_CONTRACT_VERSION: AeosExceptionContract,
}


def _error_data(exc: PydanticValidationError) -> list[dict[str, Any]]:
    return [
        {"field": ".".join(str(p) for p in err["loc"]), "type": err["type"], "message": err["msg"]}
        for err in exc.errors()
    ]


def validate_contract(payload: Mapping[str, Any]) -> AeosContract:
    """按 contract_version 分派校验，返回强类型契约对象。

    未知版本或字段/取值不合规时抛 `ContractValidationError`（HTTP 422）。
    """
    version = payload.get("contract_version")
    model = _CONTRACT_MODELS.get(version) if isinstance(version, str) else None
    if model is None:
        raise ContractValidationError(
            f"未知契约版本: {version!r}",
            {"supported_versions": sorted(_CONTRACT_MODELS)},
        )
    try:
        return model.model_validate(payload)
    except PydanticValidationError as exc:
        raise ContractValidationError("契约字段校验失败", _error_data(exc)) from exc


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
    extra: Mapping[str, Any] | None = None,
) -> AeosResultContract:
    """构造并校验 Result 契约，保证产出即合规。"""
    payload: dict[str, Any] = {
        "contract_version": RESULT_CONTRACT_VERSION,
        "result_id": result_id,
        "source_system": source_system,
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
    extra: Mapping[str, Any] | None = None,
) -> AeosExceptionContract:
    """构造并校验 Exception 契约，保证产出即合规。"""
    payload: dict[str, Any] = {
        "contract_version": EXCEPTION_CONTRACT_VERSION,
        "exception_id": exception_id,
        "source_system": source_system,
        "object_type": object_type,
        "object_id": object_id,
        "severity": severity,
        "reason_code": reason_code,
        "status": status,
        "evidence_ids": list(evidence_ids),
        "trace_id": trace_id,
        "occurred_at": occurred_at,
    }
    if extra:
        payload.update(extra)
    return validate_contract(payload)  # type: ignore[return-value]
