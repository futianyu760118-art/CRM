"""AEOS 人员生命周期事件适配器。"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import response as resp
from app.core.config import settings
from app.core.deps import DbSession
from app.core.error_codes import ErrCode
from app.core.exceptions import ApiError
from app.db.base import utcnow
from app.models.business import Company, Contact, Inquiry, Lead, Opportunity, Task
from app.models.integration import IntegrationLog
from app.models.pricing import ApprovalTask, PricingRecord, Quotation
from app.models.sales import Feedback, SalesOrder, Sample
from app.models.user import User, UserRole

router = APIRouter(prefix="/internal/aeos/person-lifecycle", tags=["AEOS-Person-Lifecycle"])

_TARGET_SYSTEM = "M05_CRM"
_LOG_SYSTEM = "AEOS"
_LOG_ACTION = "PERSON_LIFECYCLE"
_HMAC_WINDOW_SECONDS = 5 * 60
_OPEN_TASK_STATUSES = {"PENDING", "IN_PROGRESS", "TODO", "PENDING_REASSIGNMENT"}
_CLOSED_STATUSES = {"DONE", "COMPLETED", "CANCELLED", "CLOSED", "RESOLVED"}
_OWNER_MODELS = (
    Lead,
    Company,
    Contact,
    Opportunity,
    Inquiry,
    PricingRecord,
    Quotation,
    SalesOrder,
    Sample,
)


class PersonRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    person_id: str = Field(min_length=1)
    emp_code: str = Field(min_length=1)


class PersonLifecycleEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(min_length=1)
    event_id: str = Field(min_length=1)
    event_type: Literal["person.offboarded", "person.reinstated"]
    event_version: Literal[1]
    source_system: str = Field(min_length=1)
    object_type: Literal["Person"]
    object_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    occurred_at: datetime
    effective_at: datetime
    correlation_id: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    person: PersonRef
    status: Literal["active", "inactive"]
    employment_action: Literal["offboard", "rehire", "reinstate"] | None = None
    evidence_refs: list[str] | None = None
    occurred_by: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_state_transition(self) -> PersonLifecycleEvent:
        expected_status = "inactive" if self.event_type == "person.offboarded" else "active"
        if self.status != expected_status:
            raise ValueError(f"{self.event_type} 的 status 必须为 {expected_status}")
        if self.person.person_id != self.object_id:
            raise ValueError("person.person_id 必须与 object_id 一致")
        return self


def verify_hmac_signature(
    key_id: str,
    timestamp: str,
    signature: str,
    raw_body: bytes,
    secrets: dict[str, str],
    *,
    now: float | None = None,
) -> bool:
    """验证 AEOS 的 `timestamp + '.' + raw body` HMAC。"""
    secret = secrets.get(key_id)
    if not key_id or not timestamp or not signature or not secret:
        return False
    try:
        timestamp_value = float(timestamp)
    except ValueError:
        return False
    current = time.time() if now is None else now
    # 调用方约定为 Unix 秒；为兼容现有 AEOS 客户端，也接受毫秒 Unix 时间戳。
    if timestamp_value > 100_000_000_000:
        timestamp_value /= 1000
    if abs(current - timestamp_value) > _HMAC_WINDOW_SECONDS:
        return False
    expected = hmac.new(
        secret.encode("utf-8"),
        timestamp.encode("utf-8") + b"." + raw_body,
        hashlib.sha256,
    ).hexdigest()
    provided = signature.removeprefix("sha256=")
    return hmac.compare_digest(expected, provided)


def _configured_hmac_secrets() -> dict[str, str]:
    key_id = os.getenv("AEOS_PERSON_LIFECYCLE_KEY_ID", settings.AEOS_PERSON_LIFECYCLE_KEY_ID)
    secret = os.getenv("AEOS_PERSON_LIFECYCLE_SECRET", settings.AEOS_PERSON_LIFECYCLE_SECRET)
    if not key_id or not secret:
        return {}
    return {key_id: secret}


async def _rows(db: AsyncSession, model: type[Any]) -> list[Any]:
    result = await db.execute(select(model).where(model.deleted_at.is_(None)))
    return list(result.scalars().all())


async def _lifecycle_logs(db: AsyncSession) -> list[IntegrationLog]:
    result = await db.execute(
        select(IntegrationLog).where(
            IntegrationLog.system == _LOG_SYSTEM,
            IntegrationLog.action == _LOG_ACTION,
            IntegrationLog.deleted_at.is_(None),
        )
    )
    rows = list(result.scalars().all())
    rows.extend(getattr(db, "_aeos_person_lifecycle_logs", []))
    unique: dict[tuple[str | None, str | None], IntegrationLog] = {}
    for row in rows:
        unique[(row.idempotency_key, row.request_id)] = row
    return list(unique.values())


def _event_wire(event: PersonLifecycleEvent) -> dict[str, Any]:
    return event.model_dump(mode="json", exclude_none=True)


def _base_result(event: PersonLifecycleEvent, *, status: str, changed: dict[str, int]) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "target_system": _TARGET_SYSTEM,
        "status": status,
        "changed": changed,
        "received_at": utcnow().isoformat(),
    }


async def _find_user(db: AsyncSession, event: PersonLifecycleEvent) -> tuple[User | None, str | None]:
    users = [u for u in await _rows(db, User) if u.deleted_at is None]
    by_person_id = [u for u in users if str(u.id) == event.object_id]
    by_emp_code = [u for u in users if u.code == event.person.emp_code]
    if len(by_person_id) > 1 or len(by_emp_code) > 1:
        return None, "identity_conflict"
    if by_person_id and by_emp_code and by_person_id[0].id != by_emp_code[0].id:
        return None, "identity_conflict"
    if by_person_id:
        return by_person_id[0], None
    if by_emp_code:
        return by_emp_code[0], None
    return None, None


async def _release_assignments(db: AsyncSession, user_id: uuid.UUID) -> dict[str, int]:
    changed = {"owners": 0, "tasks": 0, "approvals": 0}

    for model in _OWNER_MODELS:
        for row in await _rows(db, model):
            if getattr(row, "owner_id", None) == user_id:
                row.owner_id = None
                changed["owners"] += 1

    for row in await _rows(db, Task):
        if row.status in _CLOSED_STATUSES:
            continue
        if row.owner_id == user_id or row.assignee_id == user_id:
            row.owner_id = None
            row.assignee_id = None
            row.status = "PENDING_REASSIGNMENT"
            changed["tasks"] += 1

    for row in await _rows(db, Feedback):
        if row.status in _CLOSED_STATUSES:
            continue
        if row.owner_id == user_id or row.assignee_id == user_id:
            row.owner_id = None
            row.assignee_id = None
            row.assignee = None
            row.status = "PENDING_REASSIGNMENT"
            changed["owners"] += 1

    for row in await _rows(db, ApprovalTask):
        if row.status == "PENDING" and row.approver_id == user_id:
            row.approver_id = None
            row.status = "PENDING_REASSIGNMENT"
            changed["approvals"] += 1

    return changed


def _previous_assignment_count(logs: list[IntegrationLog], event: PersonLifecycleEvent) -> int:
    count = 0
    for log in logs:
        payload = log.request_payload or {}
        if payload.get("tenant_id") != event.tenant_id or payload.get("object_id") != event.object_id or payload.get("event_type") != "person.offboarded":
            continue
        changed = log.response_payload.get("changed", {}) if log.response_payload else {}
        count = max(count, sum(int(changed.get(key, 0)) for key in ("owners", "tasks", "approvals")))
    return count


def _existing_result(logs: list[IntegrationLog], event: PersonLifecycleEvent) -> dict[str, Any] | None:
    for log in logs:
        payload = log.request_payload or {}
        if payload.get("tenant_id") != event.tenant_id:
            continue
        if log.idempotency_key == event.idempotency_key or log.request_id == event.event_id:
            result = dict(log.response_payload or {})
            result["duplicate"] = True
            return result
    return None


def _latest_revision(logs: list[IntegrationLog], event: PersonLifecycleEvent) -> int:
    latest = 0
    for log in logs:
        payload = log.request_payload or {}
        if payload.get("tenant_id") == event.tenant_id and payload.get("object_id") == event.object_id:
            latest = max(latest, int(payload.get("revision", 0)))
    return latest


def _save_log(db: AsyncSession, event: PersonLifecycleEvent, result: dict[str, Any], *, status: str) -> None:
    row = IntegrationLog(
        system=_LOG_SYSTEM,
        action=_LOG_ACTION,
        request_id=event.event_id,
        idempotency_key=event.idempotency_key,
        business_id=event.object_id,
        request_payload=_event_wire(event),
        response_payload=result,
        status=status,
        finished_at=utcnow(),
    )
    local_logs = getattr(db, "_aeos_person_lifecycle_logs", None)
    if local_logs is None:
        local_logs = []
        db._aeos_person_lifecycle_logs = local_logs
    local_logs.append(row)
    db.add(row)


async def _remove_user_roles(db: AsyncSession, user_id: uuid.UUID) -> int:
    roles = await _rows(db, UserRole)
    removed = sum(1 for row in roles if row.user_id == user_id and row.deleted_at is None)
    await db.execute(delete(UserRole).where(UserRole.user_id == user_id))
    return removed


async def apply_person_lifecycle_event(db: AsyncSession, event: PersonLifecycleEvent) -> dict[str, Any]:
    """在当前 CRM 事务中应用一条人员生命周期事件。"""
    configured_tenant = os.getenv("AEOS_TENANT_ID", "").strip()
    if configured_tenant and event.tenant_id != configured_tenant:
        result = _base_result(event, status="failed", changed={})
        result["reason"] = "tenant_mismatch"
        result["last_error_code"] = "TENANT_BOUNDARY"
        return result
    logs = await _lifecycle_logs(db)
    duplicate = _existing_result(logs, event)
    if duplicate is not None:
        return duplicate

    if _latest_revision(logs, event) > event.revision:
        result = _base_result(event, status="skipped", changed={})
        result["reason"] = "stale_revision"
        _save_log(db, event, result, status="SKIPPED")
        return result

    user, match_error = await _find_user(db, event)
    if match_error:
        result = _base_result(event, status="failed", changed={})
        result["reason"] = match_error
        result["last_error_code"] = "IDENTITY_CONFLICT"
        _save_log(db, event, result, status="FAILED")
        return result
    if user is None:
        result = _base_result(event, status="skipped", changed={})
        result["reason"] = "person_not_found"
        _save_log(db, event, result, status="SKIPPED")
        return result

    if event.event_type == "person.offboarded":
        permissions_removed = await _remove_user_roles(db, user.id)
        user.status = "INACTIVE"
        user.is_superuser = False
        user.roles = []
        changed = {"users": 1, "permissions": permissions_removed}
        changed.update(await _release_assignments(db, user.id))
        result = _base_result(event, status="synced", changed=changed)
        result["state"] = "offboarded"
        _save_log(db, event, result, status="SUCCESS")
        return result

    permissions_pending = 1
    user.status = "ACTIVE"
    user.is_superuser = False
    await _remove_user_roles(db, user.id)
    user.roles = []
    assignment_pending = _previous_assignment_count(logs, event)
    result = _base_result(
        event,
        status="pending_confirmation",
        changed={"users": 1, "permissions": 0},
    )
    result["pending_confirmation"] = {
        "permissions": permissions_pending,
        "assignments": assignment_pending,
    }
    result["state"] = "active"
    _save_log(db, event, result, status="SUCCESS")
    return result


@router.post("", summary="接收 AEOS 人员生命周期事件")
async def receive_person_lifecycle(
    payload: PersonLifecycleEvent,
    request: Request,
    db: DbSession,
) -> dict[str, Any]:
    raw_body = await request.body()
    if not verify_hmac_signature(
        request.headers.get("X-AEOS-Key-Id", ""),
        request.headers.get("X-AEOS-Timestamp", ""),
        request.headers.get("X-AEOS-Signature", ""),
        raw_body,
        _configured_hmac_secrets(),
    ):
        raise ApiError(ErrCode.UNAUTHORIZED, "AEOS 人员生命周期签名无效", http_status=401)

    result = await apply_person_lifecycle_event(db, payload)
    if result.get("status") == "failed":
        await db.commit()
        return JSONResponse(
            status_code=409,
            content={"status": "failed", "message": "身份冲突", **result},
        )
    if not result.get("duplicate"):
        await db.commit()
    return resp.ok(result)
