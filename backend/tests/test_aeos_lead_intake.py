from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.aeos_lead import AeosLeadIntake


def payload() -> dict:
    return {
        "contract_version": "LeadIntakeV1",
        "intake_id": "lead_001",
        "source_system": "PUBLIC_BFF",
        "submitted_at": datetime.now(UTC).isoformat(),
        "contact": {"name": "官网客户", "email_or_phone": "demo@example.com"},
        "interest": "工业照明",
        "consent": {
            "granted": True,
            "version": "privacy-v1",
            "purpose": "业务联系",
            "retention_until": "2028-01-01T00:00:00Z",
        },
        "trace_id": "trace-1",
        "idempotency_key": "web-001",
    }


def test_aeos_lead_intake_contract_is_strict() -> None:
    model = AeosLeadIntake.model_validate(payload())
    assert model.source_system == "PUBLIC_BFF"
    assert model.contact.email_or_phone == "demo@example.com"


@pytest.mark.parametrize("change", [{"source_system": "CRM"}, {"internal_id": "x"}])
def test_aeos_lead_intake_rejects_boundary_drift(change: dict) -> None:
    data = payload()
    data.update(change)
    with pytest.raises(ValidationError):
        AeosLeadIntake.model_validate(data)
