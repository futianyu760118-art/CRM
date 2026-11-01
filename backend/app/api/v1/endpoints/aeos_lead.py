"""EDP → CRM LeadIntakeV1 consumer boundary."""

from __future__ import annotations

import secrets
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core import response as resp
from app.core.config import settings
from app.core.deps import DbSession
from app.core.error_codes import ErrCode
from app.core.exceptions import ApiError
from app.db.base import utcnow
from app.models.business import Lead
from app.schemas.aeos_lead import AeosLeadIntake, AeosLeadIntakeResponse
from app.services.number_sequence import next_number

router = APIRouter(prefix="/integrations/aeos", tags=["AEOS-LeadIntake"])


def _verify_inbound_token(request: Request) -> None:
    configured = settings.AEOS_LEAD_INBOUND_TOKEN
    if not configured:
        raise ApiError(
            ErrCode.SERVICE_UNAVAILABLE,
            "AEOS LeadIntake 入站令牌未配置",
            http_status=503,
        )
    header = request.headers.get("Authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else ""
    if not token or not secrets.compare_digest(token, configured):
        raise ApiError(ErrCode.UNAUTHORIZED, "AEOS LeadIntake 入站令牌无效", http_status=401)


def _contact_parts(value: str) -> tuple[str | None, str | None]:
    contact = value.strip()
    return (contact, None) if "@" in contact else (None, contact)


@router.post("/lead-intake", status_code=202, summary="接收 EDP LeadIntakeV1")
async def receive_lead_intake(
    payload: AeosLeadIntake,
    db: DbSession,
    _: None = Depends(_verify_inbound_token),
) -> dict[str, Any]:
    email, phone = _contact_parts(payload.contact.email_or_phone)
    remark = f"官网需求：{payload.interest}"
    if payload.message:
        remark += f"\n{payload.message}"
    stmt = (
        pg_insert(Lead)
        .values(
            lead_no=await next_number("lead"),
            external_id=payload.intake_id,
            name=payload.contact.name,
            contact_name=payload.contact.name,
            email=email,
            phone=phone,
            source="WEBSITE",
            status="NEW",
            remark=remark,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        .on_conflict_do_nothing(
            index_elements=[Lead.external_id],
            index_where=Lead.external_id.is_not(None),
        )
        .returning(Lead.id)
    )
    inserted_id = (await db.execute(stmt)).scalar_one_or_none()
    if inserted_id is None:
        existing = (
            await db.execute(select(Lead).where(Lead.external_id == payload.intake_id))
        ).scalar_one()
        return resp.ok(
            AeosLeadIntakeResponse(
                lead_reference=existing.external_id or payload.intake_id,
                deduplicated=True,
            ).model_dump(mode="json")
        )
    return resp.ok(
        AeosLeadIntakeResponse(
            lead_reference=payload.intake_id, deduplicated=False
        ).model_dump(mode="json")
    )
