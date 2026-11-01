"""AEOS LeadIntakeV1 payload accepted from the EDP service boundary."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AeosLeadContact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    email_or_phone: str = Field(min_length=3, max_length=320)


class AeosLeadConsent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    granted: Literal[True]
    version: str = Field(min_length=1, max_length=80)
    purpose: str = Field(min_length=1, max_length=160)
    retention_until: datetime
    deletion_requested: bool = False


class AeosLeadIntake(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["LeadIntakeV1"]
    intake_id: str = Field(min_length=1, max_length=160)
    source_system: Literal["PUBLIC_BFF"]
    submitted_at: datetime
    contact: AeosLeadContact
    interest: str = Field(min_length=1, max_length=160)
    message: str | None = Field(default=None, max_length=4000)
    consent: AeosLeadConsent
    trace_id: str = Field(min_length=1, max_length=160)
    idempotency_key: str = Field(min_length=1, max_length=160)
    tenant_id: str | None = Field(default=None, min_length=1, max_length=160)


class AeosLeadIntakeResponse(BaseModel):
    lead_reference: str
    deduplicated: bool = False
