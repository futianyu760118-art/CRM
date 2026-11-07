"""AEOS 契约校验单测：字段集 / 取值域对齐 EBMS contracts 基线。

基线来源（未改写）：
- ``EBMS/contracts/aeos-contracts-v1.examples.json``  —— 字段集权威基线
- ``EBMS/contracts/README.md``                        —— 通用字段「至少包含」约束

下方 ``BASELINE_*_KEYS`` 是从 examples.json **逐键抄录**的字段集；测试同时做
「模型 → 基线」与「基线 → 模型」双向断言，任一侧增删字段都会失败。
"""

from __future__ import annotations

import pytest

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
    build_exception_contract,
    build_result_contract,
    to_wire,
    unknown_fields,
    validate_contract,
)

# --- 逐键抄录自 EBMS/contracts/aeos-contracts-v1.examples.json -------------------

# L1 必填集逐字不变；PAND-330 M2 按架构 F2-A01/A02/A03 在原位增补
# source/version/object_ref/evidence_refs（V1.x，不升版本号）。
L2_RESULT_ADDITIONS = {"source", "version", "object_ref", "evidence_refs"}

BASELINE_RESULT_KEYS = {
    "contract_version",
    "result_id",
    "source_system",
    "object_type",
    "object_id",
    "period",
    "metric",
    "status",
    "evidence_ids",
    "trace_id",
    "occurred_at",
} | L2_RESULT_ADDITIONS
BASELINE_EXCEPTION_KEYS = {
    "contract_version",
    "exception_id",
    "source_system",
    "object_type",
    "object_id",
    "severity",
    "reason_code",
    "status",
    "evidence_ids",
    "trace_id",
    "occurred_at",
} | L2_RESULT_ADDITIONS
BASELINE_PERIOD_KEYS = {"start", "end"}
BASELINE_METRIC_KEYS = {"code", "value", "unit", "calculation_version"}

VALID_RESULT = {
    "contract_version": RESULT_CONTRACT_VERSION,
    "result_id": "RES-EXAMPLE",
    "source": "M09",
    "source_system": "M09",
    "version": RESULT_CONTRACT_VERSION,
    "object_ref": {"object_type": "BusinessMetric", "object_id": "gross_margin"},
    "object_type": "BusinessMetric",
    "object_id": "gross_margin",
    "period": {"start": "2026-09-01", "end": "2026-09-30"},
    "metric": {
        "code": "gross_margin",
        "value": 0,
        "unit": "percent",
        "calculation_version": "M09-GM-V1",
    },
    "status": "VERIFIED",
    "evidence_ids": ["EVD-EXAMPLE"],
    "evidence_refs": ["EVD-EXAMPLE"],
    "trace_id": "TRACE-EXAMPLE",
    "occurred_at": "2026-10-01T09:00:00+08:00",
}

VALID_EXCEPTION = {
    "contract_version": EXCEPTION_CONTRACT_VERSION,
    "exception_id": "EXC-EXAMPLE",
    "source": "M06",
    "source_system": "M06",
    "version": EXCEPTION_CONTRACT_VERSION,
    "object_ref": {"object_type": "DeliveryOrder", "object_id": "ORDER-EXAMPLE"},
    "object_type": "DeliveryOrder",
    "object_id": "ORDER-EXAMPLE",
    "severity": "high",
    "reason_code": "DELIVERY_RISK",
    "status": "OPEN",
    "evidence_ids": [],
    "evidence_refs": [],
    "trace_id": "TRACE-EXAMPLE",
    "occurred_at": "2026-10-01T09:00:00+08:00",
}


class TestFieldAlignmentWithBaseline:
    def test_result_required_fields_equal_baseline(self) -> None:
        assert set(AeosResultContract.model_fields) == BASELINE_RESULT_KEYS

    def test_exception_required_fields_equal_baseline(self) -> None:
        assert set(AeosExceptionContract.model_fields) == BASELINE_EXCEPTION_KEYS

    def test_period_and_metric_fields_equal_baseline(self) -> None:
        assert set(AeosPeriod.model_fields) == BASELINE_PERIOD_KEYS
        assert set(AeosMetric.model_fields) == BASELINE_METRIC_KEYS

    def test_contract_versions_match_baseline_strings(self) -> None:
        assert RESULT_CONTRACT_VERSION == "AEOS.Result.V1"
        assert EXCEPTION_CONTRACT_VERSION == "AEOS.Exception.V1"

    def test_status_and_severity_domains_cover_baseline_values(self) -> None:
        # 取值域只采用基线样例中实际出现的取值（severity 另见下方推断说明测试）
        assert RESULT_STATUSES == ("VERIFIED",)
        assert EXCEPTION_STATUSES == ("OPEN",)
        assert "high" in SEVERITY_LEVELS

    def test_common_fields_from_readme_are_all_present(self) -> None:
        # README 通用字段：contract_version/id/source_system/object_type/object_id/
        # occurred_at/status/trace_id/evidence_ids（id 由 <type>_id 承载）
        common = {
            "contract_version",
            "source_system",
            "object_type",
            "object_id",
            "occurred_at",
            "status",
            "trace_id",
            "evidence_ids",
        }
        assert common <= set(AeosResultContract.model_fields)
        assert common <= set(AeosExceptionContract.model_fields)


class TestValidContracts:
    def test_result_example_validates(self) -> None:
        contract = validate_contract(VALID_RESULT)
        assert isinstance(contract, AeosResultContract)
        assert contract.contract_id == "RES-EXAMPLE"
        assert contract.metric.calculation_version == "M09-GM-V1"

    def test_exception_example_validates(self) -> None:
        contract = validate_contract(VALID_EXCEPTION)
        assert isinstance(contract, AeosExceptionContract)
        assert contract.contract_id == "EXC-EXAMPLE"
        assert contract.severity == "high"
        assert contract.evidence_ids == []

    def test_wire_serialization_uses_date_and_offset_formats(self) -> None:
        wire = to_wire(validate_contract(VALID_RESULT))
        assert wire["period"]["start"] == "2026-09-01"
        assert wire["occurred_at"] == "2026-10-01T09:00:00+08:00"

    def test_extension_fields_are_preserved_not_dropped(self) -> None:
        payload = {**VALID_EXCEPTION, "days_overdue": 12}
        wire = to_wire(validate_contract(payload))
        assert wire["days_overdue"] == 12
        assert unknown_fields(payload) == ["days_overdue"]


class TestRejections:
    def test_unknown_contract_version_rejected(self) -> None:
        with pytest.raises(ContractValidationError) as exc:
            validate_contract({**VALID_RESULT, "contract_version": "AEOS.Result.V9"})
        assert "未知契约版本" in exc.value.message

    @pytest.mark.parametrize(
        "missing",
        [
            "result_id",
            "period",
            "metric",
            "evidence_ids",
            "trace_id",
            "source",
            "version",
            "object_ref",
            "evidence_refs",
        ],
    )
    def test_missing_required_field_rejected(self, missing: str) -> None:
        payload = {k: v for k, v in VALID_RESULT.items() if k != missing}
        with pytest.raises(ContractValidationError) as exc:
            validate_contract(payload)
        fields = {e["field"] for e in exc.value.data}  # type: ignore[union-attr]
        assert missing in fields

    def test_result_status_out_of_domain_rejected(self) -> None:
        with pytest.raises(ContractValidationError):
            validate_contract({**VALID_RESULT, "status": "DRAFT"})

    def test_exception_severity_out_of_domain_rejected(self) -> None:
        with pytest.raises(ContractValidationError):
            validate_contract({**VALID_EXCEPTION, "severity": "urgent"})

    def test_exception_status_out_of_domain_rejected(self) -> None:
        with pytest.raises(ContractValidationError):
            validate_contract({**VALID_EXCEPTION, "status": "CLOSED"})

    def test_period_end_before_start_rejected(self) -> None:
        payload = {**VALID_RESULT, "period": {"start": "2026-09-30", "end": "2026-09-01"}}
        with pytest.raises(ContractValidationError):
            validate_contract(payload)

    def test_empty_evidence_ids_list_is_allowed(self) -> None:
        # 基线 exception 样例即为空数组 → 允许，但字段必须存在
        assert validate_contract(VALID_EXCEPTION).evidence_ids == []

    def test_evidence_ids_key_must_be_present(self) -> None:
        payload = {k: v for k, v in VALID_EXCEPTION.items() if k != "evidence_ids"}
        with pytest.raises(ContractValidationError):
            validate_contract(payload)

    def test_blank_trace_id_rejected(self) -> None:
        with pytest.raises(ContractValidationError):
            validate_contract({**VALID_EXCEPTION, "trace_id": ""})

    def test_result_source_must_equal_source_system(self) -> None:
        with pytest.raises(ContractValidationError):
            validate_contract({**VALID_RESULT, "source": "M06"})

    def test_result_object_ref_must_match_flat_fields(self) -> None:
        with pytest.raises(ContractValidationError):
            validate_contract(
                {**VALID_RESULT, "object_ref": {"object_type": "Other", "object_id": "gross_margin"}}
            )

    def test_result_evidence_refs_must_equal_evidence_ids(self) -> None:
        with pytest.raises(ContractValidationError):
            validate_contract({**VALID_RESULT, "evidence_refs": ["EVD-OTHER"]})

    def test_exception_source_must_equal_source_system(self) -> None:
        with pytest.raises(ContractValidationError):
            validate_contract({**VALID_EXCEPTION, "source": "M09"})


class TestL1BackwardCompatibility:
    """L1 报文（无 L2 增补字段）经 compat 归一后仍可解析（F2-A04）。"""

    def test_l1_result_normalizes_and_validates(self) -> None:
        from app.contracts.compat import normalize_result

        l1_result = {k: v for k, v in VALID_RESULT.items() if k not in L2_RESULT_ADDITIONS}
        contract = validate_contract(normalize_result(l1_result))
        assert isinstance(contract, AeosResultContract)
        assert contract.source == contract.source_system == "M09"
        assert contract.object_ref.object_id == "gross_margin"
        assert contract.evidence_refs == contract.evidence_ids

    def test_l1_exception_normalizes_and_validates(self) -> None:
        from app.contracts.compat import normalize_exception

        l1_exception = {k: v for k, v in VALID_EXCEPTION.items() if k not in L2_RESULT_ADDITIONS}
        contract = validate_contract(normalize_exception(l1_exception))
        assert isinstance(contract, AeosExceptionContract)
        assert contract.object_ref.object_type == "DeliveryOrder"

    def test_l2_additions_are_not_prefilled_by_model_defaults(self) -> None:
        # 出站方向不得依赖模型默认值补齐 L2 字段：缺字段即拒（F2-A01）。
        l1_result = {k: v for k, v in VALID_RESULT.items() if k not in L2_RESULT_ADDITIONS}
        with pytest.raises(ContractValidationError):
            validate_contract(l1_result)


class TestBuilders:
    def test_build_result_contract_emits_valid_contract(self) -> None:
        from datetime import date, datetime, timedelta, timezone

        contract = build_result_contract(
            result_id="RES-M05-TEST",
            source_system="M05",
            object_type="BusinessMetric",
            object_id="order_amount",
            period_start=date(2026, 9, 1),
            period_end=date(2026, 9, 30),
            metric_code="order_amount",
            metric_value=1234.5,
            metric_unit="currency",
            calculation_version="M05-ORDER-AMOUNT-V1",
            evidence_ids=["a", "b"],
            trace_id="TRACE-RES-M05-TEST",
            occurred_at=datetime(2026, 9, 30, 23, 59, 59, tzinfo=timezone(timedelta(hours=8))),
        )
        assert contract.contract_version == RESULT_CONTRACT_VERSION
        assert to_wire(contract)["metric"]["value"] == 1234.5

    def test_build_exception_contract_emits_valid_contract(self) -> None:
        from datetime import datetime, timedelta, timezone

        contract = build_exception_contract(
            exception_id="EXC-M05-Q1",
            source_system="M05",
            object_type="SalesOrder",
            object_id="Q-1",
            severity="medium",
            reason_code="DELIVERY_OVERDUE",
            evidence_ids=["q1"],
            trace_id="TRACE-EXC-M05-Q1",
            occurred_at=datetime(2026, 10, 1, 9, 0, 0, tzinfo=timezone(timedelta(hours=8))),
        )
        assert contract.contract_version == EXCEPTION_CONTRACT_VERSION
        assert contract.status == "OPEN"

    def test_builder_rejects_invalid_value(self) -> None:
        from datetime import date

        with pytest.raises(ContractValidationError):
            build_result_contract(
                result_id="RES-X",
                source_system="M05",
                object_type="BusinessMetric",
                object_id="order_amount",
                period_start=date(2026, 9, 1),
                period_end=date(2026, 9, 30),
                metric_code="order_amount",
                metric_value=1.0,
                metric_unit="currency",
                calculation_version="V1",
                evidence_ids=[],
                trace_id="T",
                occurred_at="not-a-datetime",  # type: ignore[arg-type]
            )
