"""销售中心 6 模块与 EBMS 双向同步——纯逻辑单测（PAND-249）。

覆盖：AEOS.Event.V1 契约校验/构造/指纹/幂等键、订单/样品/反馈状态机、
编号规则、出站序列化与字段 Owner 边界、入站幂等键与字段规整。
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.contracts.aeos import (
    EVENT_CONTRACT_VERSION,
    EVENT_TYPES,
    AeosEventContract,
    ContractValidationError,
    build_event_contract,
    canonical_json,
    delete_event_for,
    event_fingerprint,
    event_idempotency_key,
    upsert_event_for,
    validate_contract,
)
from app.domain.state_machine import (
    FEEDBACK_STATUSES,
    SAMPLE_STATUSES,
    allowed_order_transitions,
)
from app.services.ebms_ingest import _coerce, _differs
from app.services.ebms_sync import _ser, natural_id
from app.services.number_sequence import format_number

# ------------------------------------------------------------------ AEOS.Event.V1


def _event(**overrides: object) -> dict:
    base: dict = {
        "contract_version": EVENT_CONTRACT_VERSION,
        "event_id": "EVT-TEST-001",
        "event_type": "customer.upserted",
        "source_system": "CRM",
        "object_type": "customer",
        "object_id": "HJ003-176-576",
        "occurred_at": datetime(2026, 10, 16, 8, 0, 0, tzinfo=UTC),
        "trace_id": "TRACE-TEST",
        "payload": {"code": "HJ003-176-576", "name": "测试客户", "currency": "USD"},
    }
    base.update(overrides)
    return base


class TestEventContract:
    def test_13_event_types_exist(self) -> None:
        # 6 实体 × {upserted, deleted} + dictionary.upserted = 13
        assert len(EVENT_TYPES) == 13
        assert "customer.upserted" in EVENT_TYPES
        assert "customer.deleted" in EVENT_TYPES
        assert "dictionary.upserted" in EVENT_TYPES
        assert "dictionary.deleted" not in EVENT_TYPES

    def test_upsert_and_delete_event_for(self) -> None:
        assert upsert_event_for("order") == "order.upserted"
        assert delete_event_for("order") == "order.deleted"
        with pytest.raises(ValueError):
            delete_event_for("dictionary")

    def test_event_contract_validates_and_roundtrips(self) -> None:
        contract = validate_contract(_event())
        assert isinstance(contract, AeosEventContract)
        assert contract.contract_id == "EVT-TEST-001"
        assert contract.payload["name"] == "测试客户"

    def test_build_event_contract_emits_valid_contract(self) -> None:
        contract = build_event_contract(
            event_id="EVT-2",
            event_type="sample.upserted",
            source_system="CRM",
            object_type="sample",
            object_id="SMP-0001",
            payload={"sample_no": "SMP-0001"},
            trace_id="T2",
            occurred_at=datetime(2026, 10, 16, 8, 0, 0, tzinfo=UTC),
        )
        assert contract.contract_version == EVENT_CONTRACT_VERSION
        assert contract.event_type == "sample.upserted"

    def test_unknown_event_type_rejected(self) -> None:
        with pytest.raises(ContractValidationError):
            validate_contract(_event(event_type="customer.renamed"))

    def test_unknown_object_type_rejected(self) -> None:
        with pytest.raises(ContractValidationError):
            validate_contract(_event(object_type="invoice"))


class TestFingerprintAndIdempotency:
    def test_fingerprint_ignores_occurred_at(self) -> None:
        a = _event(occurred_at=datetime(2026, 10, 16, 8, 0, 0, tzinfo=UTC))
        b = _event(occurred_at=datetime(2026, 10, 16, 9, 30, 0, tzinfo=UTC))
        assert event_fingerprint(a) == event_fingerprint(b)

    def test_fingerprint_stable_under_key_reorder(self) -> None:
        a = _event(payload={"code": "X", "name": "Y"})
        b = _event(payload={"name": "Y", "code": "X"})
        assert event_fingerprint(a) == event_fingerprint(b)

    def test_fingerprint_changes_when_payload_changes(self) -> None:
        assert event_fingerprint(_event(payload={"code": "A"})) != event_fingerprint(
            _event(payload={"code": "B"})
        )

    def test_canonical_json_sorted_and_no_spaces(self) -> None:
        # 标量一律字符串化（int → "1"），键排序、无空格
        wire = canonical_json({"b": 1, "a": {"z": 1, "y": 2}})
        assert wire == '{"a":{"y":"2","z":"1"},"b":"1"}'
        assert " " not in wire

    def test_idempotency_key_format(self) -> None:
        key = event_idempotency_key("CRM", _event())
        prefix, event_type, object_id, fp = key.split(":")
        assert prefix == "CRM"
        assert event_type == "customer.upserted"
        assert object_id == "HJ003-176-576"
        assert len(fp) == 16


# ------------------------------------------------------------------ 状态机


class TestOrderStateMachine:
    def test_order_forward_progression(self) -> None:
        assert allowed_order_transitions("open") == ["confirmed", "closed", "cancelled"]
        assert allowed_order_transitions("shipped") == ["completed", "closed", "cancelled"]

    def test_terminal_states_have_no_transition(self) -> None:
        assert allowed_order_transitions("completed") == []
        assert allowed_order_transitions("cancelled") == []
        assert allowed_order_transitions("closed") == []

    def test_linear_sample_and_feedback_statuses(self) -> None:
        assert SAMPLE_STATUSES == ["pending", "confirmed", "producing", "sent", "customer_confirmed", "completed"]
        assert FEEDBACK_STATUSES == ["open", "processing", "resolved", "closed"]


# ------------------------------------------------------------------ 编号规则


class TestNumberFormats:
    def test_inquiry_format_matches_ac_m2_2(self) -> None:
        no = format_number("inquiry", datetime(2026, 9, 16, tzinfo=UTC), 1)
        assert re.fullmatch(r"JFX\d{8}\d{3}", no), no
        assert no == "JFX20260916001"

    def test_sample_format_global_seq(self) -> None:
        assert format_number("sample", datetime(2026, 10, 16, tzinfo=UTC), 7) == "SMP-0007"

    def test_feedback_format_daily_seq(self) -> None:
        no = format_number("feedback", datetime(2026, 10, 16, tzinfo=UTC), 12)
        assert no == "FB20261016012"


# ------------------------------------------------------------------ 同步纯逻辑


class TestSyncPrimitives:
    def test_ser_normalizes_decimal_datetime_uuid(self) -> None:
        assert _ser(Decimal("12.3400")) == 12.34
        assert _ser(datetime(2026, 10, 16, 8, 0, 0, tzinfo=UTC)) == "2026-10-16T08:00:00+00:00"
        assert _ser(date(2026, 10, 16)) == "2026-10-16"
        uid = uuid.uuid4()
        assert _ser(uid) == str(uid)
        assert _ser(None) is None

    def test_coerce_uuid_columns(self) -> None:
        uid = uuid.uuid4()
        assert _coerce("company_id", str(uid)) == uid
        assert _coerce("company_id", uid) == uid
        assert _coerce("company_id", "not-a-uuid") is None
        assert _coerce("screenshots", ["a", "b"]) == ["a", "b"]

    def test_differs_uses_ser_semantics(self) -> None:
        assert _differs(Decimal("1.5"), 1.5) is False
        assert _differs(Decimal("1.5"), 1.6) is True
        assert _differs(None, None) is False

    def test_natural_id_per_object_type(self) -> None:
        customer = SimpleNamespace(code="HJ-001")
        inquiry = SimpleNamespace(inquiry_no="JFX20261016001")
        quote = SimpleNamespace(external_model="M-1", certificate_level="CE")
        order = SimpleNamespace(order_no="SO-1")
        sample = SimpleNamespace(sample_no="SMP-0001")
        feedback = SimpleNamespace(feedback_no="FB20261016001")

        assert natural_id("customer", customer) == "HJ-001"
        assert natural_id("inquiry", inquiry) == "JFX20261016001"
        assert natural_id("quote_library", quote) == "M-1::CE"
        assert natural_id("order", order) == "SO-1"
        assert natural_id("sample", sample) == "SMP-0001"
        assert natural_id("feedback", feedback) == "FB20261016001"
