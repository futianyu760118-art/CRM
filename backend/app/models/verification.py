"""AEOS Verification 实体（PAND-330，架构 §4.4 / F5-A01）。

不继承 ``BusinessModel``：验证记录没有「业务负责人」语义，验证责任人由 ``verifier``
字段承载（架构 §4.1 台账「不适用 Owner 五字段」）。``tenant_id``/``revision`` 仍在
Object 口径内，直接落列。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel, utcnow


class Verification(BaseModel):
    """一次结果验证（F5-A01）。

    幂等（F5-A03）：同一 ``(subject_type, subject_id, subject_revision)`` 唯一。
    ``subject_revision`` 是架构两列唯一键的细化——结果指标随业务变化重新聚合时
    ``revision`` 递增，需允许对新版本重新验证，同时保证「重复 verify 返回同一条」。
    """

    __tablename__ = "verification"
    __table_args__ = (
        UniqueConstraint("subject_type", "subject_id", "subject_revision", name="uq_verification_subject"),
    )

    verification_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, unique=True, default=uuid.uuid4
    )
    subject_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    subject_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    subject_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    object_ref_type: Mapped[str] = mapped_column(String(50), nullable=False)
    object_ref_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    verifier: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    verifier_role: Mapped[str | None] = mapped_column(String(50), nullable=True)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_refs: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    tenant_id: Mapped[str] = mapped_column(String(50), nullable=False, default="default", server_default="default")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
