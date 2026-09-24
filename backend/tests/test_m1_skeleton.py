"""M1 骨架核心逻辑单测：状态机 / 编号规则 / 数据范围纯函数。"""

from __future__ import annotations

import pytest

from app.domain.state_machine import (
    INQUIRY_TRANSITIONS,
    QUOTATION_TRANSITIONS,
    allowed_opportunity_transitions,
    can_transition,
    validate_opportunity_transition,
)


class TestOpportunityStateMachine:
    def test_forward_transitions(self) -> None:
        assert allowed_opportunity_transitions("NEW") == ["QUALIFIED", "LOST"]
        assert allowed_opportunity_transitions("WON") == []

    def test_lost_allowed_from_any_stage(self) -> None:
        for stage in ("NEW", "QUALIFIED", "REQUIREMENT", "INQUIRY", "PRICING", "QUOTATION"):
            assert "LOST" in allowed_opportunity_transitions(stage)

    def test_skip_stage_rejected(self) -> None:
        missing = validate_opportunity_transition("NEW", "QUOTATION", {})
        assert missing == ["__invalid_transition__"]

    def test_required_fields_enforced(self) -> None:
        missing = validate_opportunity_transition("NEW", "QUALIFIED", {})
        assert set(missing) == {"requirement", "estimated_amount"}

    def test_lost_requires_reason(self) -> None:
        assert validate_opportunity_transition("NEW", "LOST", {}) == ["lost_reason"]
        assert validate_opportunity_transition("NEW", "LOST", {"lost_reason": "价格"}) == []

    def test_valid_transition(self) -> None:
        payload = {"requirement": "保温杯", "estimated_amount": 10000}
        assert validate_opportunity_transition("NEW", "QUALIFIED", payload) == []


class TestInquiryAndQuotationStateMachine:
    def test_inquiry_flow(self) -> None:
        assert can_transition(INQUIRY_TRANSITIONS, "DRAFT", "SUBMITTED")
        assert not can_transition(INQUIRY_TRANSITIONS, "DRAFT", "QUOTED")

    def test_quotation_flow(self) -> None:
        assert can_transition(QUOTATION_TRANSITIONS, "DRAFT", "PENDING_APPROVAL")
        assert can_transition(QUOTATION_TRANSITIONS, "PENDING_APPROVAL", "APPROVED")
        assert not can_transition(QUOTATION_TRANSITIONS, "APPROVED", "PENDING_APPROVAL")


class TestNumberSequenceFormat:
    def test_format_month(self) -> None:
        from datetime import UTC, datetime

        from app.services.number_sequence import _format

        now = datetime(2026, 9, 17, tzinfo=UTC)
        assert _format("OPP", "MONTH", now, 1) == "OPP-202609-0001"
        assert _format("OPP", "MONTH", now, 1234) == "OPP-202609-1234"

    def test_format_never(self) -> None:
        from datetime import UTC, datetime

        from app.services.number_sequence import _format

        now = datetime(2026, 9, 17, tzinfo=UTC)
        assert _format("CUS", "NEVER", now, 7) == "CUS-0007"


@pytest.mark.parametrize(
    ("period", "expected"),
    [("MONTH", "202609"), ("YEAR", "2026"), ("DAY", "20260917"), ("NEVER", "0")],
)
def test_period_key(period: str, expected: str) -> None:
    from datetime import UTC, datetime

    from app.services.number_sequence import _period_key

    assert _period_key(period, datetime(2026, 9, 17, tzinfo=UTC)) == expected
