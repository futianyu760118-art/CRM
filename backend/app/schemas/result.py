"""经营结果 / 验证（AEOS Verification，F5）Schema。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class VerifyIn(BaseModel):
    """``verify`` 动作入参（F5-A01）。"""

    status: str = Field(description="passed / failed / exempt")
    reason: str | None = Field(default=None, description="failed/exempt 必填")
    evidence_refs: list[str] = Field(default_factory=list, description="证据引用；exempt 允许 []")
    comment: str | None = None


class VerificationOut(BaseModel):
    verification_id: str
    subject_type: str
    subject_id: str
    subject_revision: int
    object_ref: dict[str, Any]
    verifier: str | None = None
    verifier_role: str | None = None
    verified_at: str | None = None
    status: str
    reason: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    comment: str | None = None
    tenant_id: str
    revision: int
