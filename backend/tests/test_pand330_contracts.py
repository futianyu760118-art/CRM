"""PAND-330 契约层自检：V2 信封 / 兼容层 / 值域双口径 / 台账 / 漂移检查。

覆盖架构 PAND-329 的 M2（F1/F2/F7）与 M3（F7-A03/A05）；不需要数据库。
"""

from __future__ import annotations

from datetime import timedelta, timezone

import pytest

from app.contracts.aeos import (
    EVENT_CONTRACT_VERSION,
    EVENT_CONTRACT_VERSION_V2,
    EXCEPTION_CONTRACT_VERSION,
    RESULT_CONTRACT_VERSION,
    ContractValidationError,
    build_event_v2_contract,
    event_v2_idempotency_key,
    to_wire,
    validate_contract,
)
from app.contracts.compat import (
    COMPAT_L2,
    COMPAT_LEGACY,
    COMPAT_V1X,
    apply_legacy_defaults,
    compat_marker,
    merge_evidence,
    normalize_event_v1,
    normalize_exception,
    normalize_result,
    to_inbound_risk,
    to_outbound_risk,
)
from app.contracts.drift import SCHEMA_PATH, assert_no_drift, check_drift, load_schema
from app.domain.aeos_ledger import (
    L1_CHANNEL,
    L1_EVENT_TYPES,
    L2_CHANNEL,
    L2_EVENT_TYPES,
    channel_of,
    is_registered,
)
from app.domain.aeos_registry import OBJECTS, SYSTEMS, objects_with_owner_fields
from app.domain.state_machine import (
    CUSTOMER_LEVELS,
    ORDER_RISK_FILTER,
    SAMPLE_STATUSES,
)

CN_TZ = timezone(timedelta(hours=8))


def _l1_event(*, event_type="customer.upserted", object_type="Customer", operation="UPSERT", payload=None):
    return {
        "contract_version": EVENT_CONTRACT_VERSION,
        "event_id": "EVT-L1-1",
        "event_type": event_type,
        "source_system": "M05",
        "object_type": object_type,
        "object_id": "C-1",
        "operation": operation,
        "occurred_at": "2026-10-01T09:00:00+08:00",
        "trace_id": "TRACE-L1-1",
        "payload": payload if payload is not None else {},
    }


class TestV2Envelope:
    def test_l1_event_required_fields_are_unchanged(self) -> None:
        contract = validate_contract(_l1_event())
        assert set(type(contract).model_fields) == {
            "contract_version",
            "event_id",
            "event_type",
            "source_system",
            "object_type",
            "object_id",
            "operation",
            "occurred_at",
            "trace_id",
            "payload",
            "idempotency_key",
        }

    def test_v2_contract_builds_with_auto_idempotency_key(self) -> None:
        contract = build_event_v2_contract(
            event_id="EVT-V2-1",
            event_type="SalesResultVerified",
            object_type="SalesResult",
            object_id="RES-M05-1",
            payload={"result_id": "RES-M05-1", "status": "verified"},
            occurred_at="2026-10-07T10:00:00+08:00",  # type: ignore[arg-type]
            correlation_id="CORR-RES-M05-1",
            actor_id="M05",
            payload_version=RESULT_CONTRACT_VERSION,
            evidence_refs=["E1"],
        )
        assert contract.contract_version == EVENT_CONTRACT_VERSION_V2
        assert contract.object_ref.model_dump() == {"object_type": "SalesResult", "object_id": "RES-M05-1"}
        assert contract.idempotency_key == event_v2_idempotency_key("EBMS", to_wire(contract))

    def test_v2_rejects_unregistered_event_type(self) -> None:
        with pytest.raises(ContractValidationError) as exc:
            build_event_v2_contract(
                event_id="EVT-V2-X",
                event_type="NotInLedger",
                object_type="SalesResult",
                object_id="RES-1",
                payload={},
                occurred_at="2026-10-07T10:00:00+08:00",  # type: ignore[arg-type]
                correlation_id="CORR-1",
                actor_id="M05",
                payload_version=RESULT_CONTRACT_VERSION,
            )
        assert "未在台账登记" in exc.value.message

    def test_v2_requires_correlation_and_actor(self) -> None:
        with pytest.raises(ContractValidationError):
            validate_contract(
                {
                    "contract_version": EVENT_CONTRACT_VERSION_V2,
                    "event_id": "EVT-V2-2",
                    "event_type": "SalesResultVerified",
                    "occurred_at": "2026-10-07T10:00:00+08:00",
                    "source_system": "M05",
                    "object_ref": {"object_type": "SalesResult", "object_id": "RES-1"},
                    "payload_version": RESULT_CONTRACT_VERSION,
                    "payload": {},
                    "evidence_refs": [],
                    "idempotency_key": "k",
                }
            )


class TestCompatLayer:
    def test_legacy_event_is_filled_then_marked_v1x(self) -> None:
        raw = _l1_event()
        assert compat_marker(raw) == COMPAT_LEGACY

        normalized = normalize_event_v1(raw)
        assert normalized["object_ref"] == {"object_type": "Customer", "object_id": "C-1"}
        assert normalized["correlation_id"] == "TRACE-L1-1"
        assert normalized["actor_id"] == "M05"
        assert normalized["payload_version"] == EVENT_CONTRACT_VERSION
        assert normalized["evidence_refs"] == []
        assert compat_marker(normalized) == COMPAT_V1X

        contract = validate_contract(normalized, direction="inbound")
        assert contract.contract_version == EVENT_CONTRACT_VERSION

    def test_v2_event_is_marked_l2_and_passed_through(self) -> None:
        contract = build_event_v2_contract(
            event_id="EVT-V2-3",
            event_type="SalesResultVerified",
            object_type="SalesResult",
            object_id="RES-2",
            payload={},
            occurred_at="2026-10-07T10:00:00+08:00",  # type: ignore[arg-type]
            correlation_id="CORR-2",
            actor_id="M05",
            payload_version=RESULT_CONTRACT_VERSION,
        )
        wire = to_wire(contract)
        assert compat_marker(wire) == COMPAT_L2
        assert normalize_event_v1(wire) == wire

    def test_apply_legacy_defaults_does_not_override_existing(self) -> None:
        raw = {**_l1_event(), "object_ref": {"object_type": "Customer", "object_id": "KEEP"}}
        assert apply_legacy_defaults(raw)["object_ref"]["object_id"] == "KEEP"

    def test_merge_evidence_maps_either_side(self) -> None:
        assert merge_evidence(["a"], []) == (["a"], ["a"])
        assert merge_evidence([], ["b"]) == (["b"], ["b"])
        assert merge_evidence(["a"], ["b"]) == (["a"], ["b"])

    def test_legacy_result_and_exception_normalization(self) -> None:
        result = normalize_result(
            {
                "contract_version": RESULT_CONTRACT_VERSION,
                "result_id": "RES-1",
                "source_system": "M09",
                "object_type": "BusinessMetric",
                "object_id": "m",
                "period": {"start": "2026-09-01", "end": "2026-09-30"},
                "metric": {"code": "m", "value": 1, "unit": "percent", "calculation_version": "V1"},
                "status": "VERIFIED",
                "evidence_ids": [],
                "trace_id": "T",
                "occurred_at": "2026-10-01T09:00:00+08:00",
            }
        )
        assert result["source"] == "M09"
        assert result["object_ref"] == {"object_type": "BusinessMetric", "object_id": "m"}
        assert result["evidence_refs"] == []
        assert validate_contract(result).contract_version == RESULT_CONTRACT_VERSION

        exception = normalize_exception(
            {
                "contract_version": EXCEPTION_CONTRACT_VERSION,
                "exception_id": "EXC-1",
                "source_system": "M05",
                "object_type": "SalesOrder",
                "object_id": "Q-1",
                "severity": "low",
                "reason_code": "X",
                "status": "OPEN",
                "evidence_ids": ["e"],
                "trace_id": "T",
                "occurred_at": "2026-10-01T09:00:00+08:00",
            }
        )
        assert exception["object_ref"]["object_id"] == "Q-1"
        assert exception["evidence_refs"] == ["e"]

    def test_risk_domain_dual_track(self) -> None:
        assert to_outbound_risk("low") == "blue"
        assert to_outbound_risk("high") == "red"
        assert to_outbound_risk("red") == "red"
        assert to_inbound_risk("medium") == "yellow"
        assert set(ORDER_RISK_FILTER) == {"blue", "yellow", "red"}


def _event_payload(event_type: str, object_type: str, payload: dict):
    return _l1_event(event_type=event_type, object_type=object_type, payload=payload)


class TestValueDomains:
    def test_outbound_domain_violation_reports_field_path(self) -> None:
        event = _event_payload(
            "customer.upserted",
            "Customer",
            {"name": "ACME", "customer_level": "Z级", "sales_mode": "外销", "customer_status": "潜在客户"},
        )
        with pytest.raises(ContractValidationError) as exc:
            validate_contract(event)
        errors = exc.value.data
        assert isinstance(errors, list)
        assert errors[0]["field"] == "payload.customer_level"
        assert "取值越界" in errors[0]["message"]

    def test_outbound_rejects_inbound_only_order_risk(self) -> None:
        event = _event_payload("order.upserted", "Order", {"status": "open", "risk_level": "high"})
        with pytest.raises(ContractValidationError) as exc:
            validate_contract(event, direction="outbound")
        assert exc.value.data[0]["field"] == "payload.risk_level"

    def test_inbound_accepts_schema_six_value_order_risk(self) -> None:
        for risk in ("blue", "yellow", "red", "low", "medium", "high"):
            event = _event_payload("order.upserted", "Order", {"status": "open", "risk_level": risk})
            assert validate_contract(event, direction="inbound").object_type == "Order"

    def test_inquiry_item_domain_violation_reports_index(self) -> None:
        event = _event_payload(
            "inquiry.upserted",
            "Inquiry",
            {
                "status": "new",
                "items": [
                    {"product_model": "OK", "certificate_level": "国标"},
                    {"product_model": "BAD", "certificate_level": "行标X"},
                ],
            },
        )
        with pytest.raises(ContractValidationError) as exc:
            validate_contract(event)
        assert exc.value.data[0]["field"] == "payload.items[1].certificate_level"

    def test_missing_optional_payload_fields_are_not_validated(self) -> None:
        event = _event_payload("sample.upserted", "Sample", {"sample_no": "S-1"})
        assert validate_contract(event).object_type == "Sample"

    def test_domain_constant_matches_state_machine(self) -> None:
        event = _event_payload("customer.upserted", "Customer", {"customer_level": CUSTOMER_LEVELS[-1]})
        assert validate_contract(event).payload["customer_level"] == CUSTOMER_LEVELS[-1]
        sample = _event_payload("sample.upserted", "Sample", {"status": SAMPLE_STATUSES[0]})
        assert validate_contract(sample).payload["status"] == SAMPLE_STATUSES[0]


class TestDriftCheck:
    def test_snapshot_is_vendored_and_pinned(self) -> None:
        assert SCHEMA_PATH.exists()
        schema = load_schema()
        assert schema["contract_version"] == "AEOS.Contracts.V1"
        provenance = SCHEMA_PATH.with_name("PROVENANCE.md").read_text(encoding="utf-8")
        assert "1d10853" in provenance

    def test_no_drift_against_frozen_schema(self) -> None:
        report = check_drift()
        assert report.ok, report.diffs
        assert report.checked == 17
        assert_no_drift()

    def test_drift_is_detected_when_schema_changes(self) -> None:
        schema = load_schema()
        schema["$defs"]["customer_level"]["enum"] = [
            v for v in schema["$defs"]["customer_level"]["enum"] if v != CUSTOMER_LEVELS[0]
        ]
        report = check_drift(schema)
        assert not report.ok
        assert any(d.domain == "customer_level" for d in report.diffs)


class TestLedgerAndRegistry:
    def test_ledger_sizes_and_channels(self) -> None:
        assert len(L1_EVENT_TYPES) == 13
        assert len(L2_EVENT_TYPES) == 18
        assert all(is_registered(e, L1_CHANNEL) for e in L1_EVENT_TYPES)
        assert all(is_registered(e, L2_CHANNEL) for e in L2_EVENT_TYPES)
        assert not is_registered("NotInLedger")
        assert channel_of("SalesResultVerified") == L2_CHANNEL
        assert channel_of("customer.upserted") == L1_CHANNEL

    def test_registry_covers_key_objects(self) -> None:
        assert SYSTEMS["M05"].system_code == "CRM"
        for entity in (
            "Lead",
            "Customer",
            "Contact",
            "Opportunity",
            "Inquiry",
            "Quotation",
            "CommercialOrder",
            "QuoteLibrary",
            "Sample",
            "Feedback",
            "SalesResult",
            "Verification",
        ):
            assert entity in OBJECTS
        assert OBJECTS["CommercialOrder"].l1_object_type == "Order"
        owned = objects_with_owner_fields()
        assert {"Customer", "Inquiry", "CommercialOrder", "SalesResult"} <= set(owned)
        assert "Verification" not in owned


class TestPermissionSeparation:
    def test_view_operation_verify_are_independent_codes(self) -> None:
        from app.core.permissions import PERMISSIONS

        codes = {p["code"] for p in PERMISSIONS if p["code"].startswith("result:")}
        assert codes == {"result:view", "result:operation", "result:verify"}

    def test_verifier_role_has_no_business_write(self) -> None:
        from app.core.permissions import ROLE_TEMPLATES

        verifier = set(ROLE_TEMPLATES["verifier"]["permissions"])
        assert verifier == {"dashboard:view", "result:view", "result:verify"}
        assert "result:operation" not in verifier

    def test_boss_has_all_result_codes(self) -> None:
        from app.core.permissions import ROLE_TEMPLATES

        boss = set(ROLE_TEMPLATES["boss"]["permissions"])
        assert {"result:view", "result:operation", "result:verify"} <= boss
