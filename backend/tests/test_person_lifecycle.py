from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI

from app.api.v1.router import api_router
from app.db.session import get_db
from app.models.business import Lead, Task
from app.models.integration import IntegrationLog
from app.models.pricing import ApprovalTask
from app.models.user import User

SECRET = "crm-person-lifecycle-test-secret"
KEY_ID = "m01-kernel"


class _Result:
    def __init__(self, values: list[object]) -> None:
        self._values = values

    def scalars(self) -> _Result:
        return self

    def all(self) -> list[object]:
        return list(self._values)

    def scalar_one_or_none(self) -> object | None:
        if not self._values:
            return None
        if len(self._values) > 1:
            raise AssertionError("fake query returned more than one row")
        return self._values[0]


class _FakeDb:
    def __init__(self, users: list[User], rows: list[object]) -> None:
        self.users = users
        self.rows = rows
        self.logs: list[IntegrationLog] = []
        self.commit_count = 0

    @staticmethod
    def _entity(statement: object) -> object | None:
        descriptions = getattr(statement, "column_descriptions", [])
        return descriptions[0].get("entity") if descriptions else None

    @staticmethod
    def _where_value(statement: object, column_name: str) -> object | None:
        for clause in getattr(statement, "_where_criteria", ()):
            left = getattr(clause, "left", None)
            if getattr(left, "name", None) == column_name:
                return getattr(getattr(clause, "right", None), "value", None)
        return None

    async def execute(self, statement: object) -> _Result:
        if getattr(statement, "is_delete", False):
            return _Result([])

        entity = self._entity(statement)
        if entity is User:
            return _Result(self.users)
        if entity is IntegrationLog:
            return _Result(self.logs)
        return _Result([row for row in self.rows if isinstance(row, entity)])

    def add(self, row: object) -> None:
        if isinstance(row, IntegrationLog):
            self.logs.append(row)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.commit_count += 1


async def _override_db(db: _FakeDb) -> AsyncIterator[_FakeDb]:
    yield db


@pytest.fixture()
def harness(monkeypatch: pytest.MonkeyPatch) -> tuple[FastAPI, _FakeDb, User, Lead, Task, ApprovalTask]:
    monkeypatch.setenv("AEOS_PERSON_LIFECYCLE_SECRET", SECRET)
    monkeypatch.setenv("AEOS_PERSON_LIFECYCLE_KEY_ID", KEY_ID)

    user = User(
        id=uuid.uuid4(),
        username="alice",
        code="E001",
        password_hash="hash",
        name="Alice",
        status="ACTIVE",
    )
    lead = Lead(id=uuid.uuid4(), lead_no="L-001", name="客户线索", owner_id=user.id)
    task = Task(id=uuid.uuid4(), title="跟进客户", owner_id=user.id, assignee_id=user.id, status="PENDING")
    approval_task = ApprovalTask(
        id=uuid.uuid4(), instance_id=uuid.uuid4(), step=1, approver_id=user.id, status="PENDING"
    )
    db = _FakeDb([user], [lead, task, approval_task])

    app = FastAPI()
    app.include_router(api_router)

    async def override() -> AsyncIterator[_FakeDb]:
        async for item in _override_db(db):
            yield item

    app.dependency_overrides[get_db] = override
    return app, db, user, lead, task, approval_task


def _event(
    user: User,
    *,
    event_id: str = "evt-offboard-1",
    event_type: str = "person.offboarded",
    revision: int = 1,
) -> dict:
    reinstated = event_type == "person.reinstated"
    return {
        "event_id": event_id,
        "event_type": event_type,
        "event_version": 1,
        "tenant_id": "tenant-hengjian",
        "source_system": "M01_KERNEL",
        "object_type": "Person",
        "object_id": str(user.id),
        "revision": revision,
        "occurred_at": "2026-11-03T02:00:00Z",
        "effective_at": "2026-11-03T02:00:00Z",
        "correlation_id": event_id,
        "trace_id": event_id,
        "idempotency_key": f"tenant-hengjian:Person:{user.id}:{revision}:{event_type}",
        "person": {"person_id": str(user.id), "emp_code": user.code},
        "status": "active" if reinstated else "inactive",
        "employment_action": "rehire" if reinstated else "offboard",
        "occurred_by": "P_OWNER",
    }


async def _post(client: httpx.AsyncClient, payload: dict) -> httpx.Response:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    timestamp = str(int(time.time() * 1000))
    signature = hmac.new(SECRET.encode(), timestamp.encode() + b"." + raw, hashlib.sha256).hexdigest()
    return await client.post(
        "/internal/aeos/person-lifecycle",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-AEOS-Key-Id": KEY_ID,
            "X-AEOS-Timestamp": timestamp,
            "X-AEOS-Signature": signature,
        },
    )


@pytest.mark.asyncio
async def test_offboard_disables_user_and_releases_current_references(harness: tuple) -> None:
    app, _, user, lead, task, approval_task = harness
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await _post(client, _event(user))

    assert response.status_code == 200
    assert response.json()["data"]["state"] == "offboarded"
    assert user.status == "INACTIVE"
    assert not user.is_active
    assert lead.owner_id is None
    assert task.owner_id is None
    assert task.assignee_id is None
    assert task.status == "PENDING_REASSIGNMENT"
    assert approval_task.approver_id is None
    assert approval_task.status == "PENDING_REASSIGNMENT"


@pytest.mark.asyncio
async def test_reinstate_restores_basic_login_only_and_requires_confirmation(harness: tuple) -> None:
    app, _, user, lead, task, approval_task = harness
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await _post(client, _event(user))).status_code == 200
        response = await _post(
            client,
            _event(user, event_id="evt-reinstate-1", event_type="person.reinstated", revision=2),
        )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "pending_confirmation"
    assert response.json()["data"]["pending_confirmation"] == {"permissions": 1, "assignments": 3}
    assert user.status == "ACTIVE"
    assert user.is_active
    assert lead.owner_id is None
    assert task.owner_id is None
    assert task.assignee_id is None
    assert approval_task.approver_id is None


@pytest.mark.asyncio
async def test_duplicate_event_returns_original_result_without_repeating_changes(harness: tuple) -> None:
    app, db, user, lead, task, approval_task = harness
    payload = _event(user)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first = await _post(client, payload)
        replay = await _post(client, payload)

    assert first.status_code == 200
    assert replay.status_code == 200
    assert replay.json()["data"]["duplicate"] is True
    assert replay.json()["data"]["event_id"] == first.json()["data"]["event_id"]
    assert len(db.logs) == 1
    assert lead.owner_id is None
    assert task.owner_id is None
    assert task.assignee_id is None
    assert approval_task.approver_id is None


@pytest.mark.asyncio
async def test_conflicting_person_id_and_employee_code_fails_closed(harness: tuple) -> None:
    app, db, user, lead, task, approval_task = harness
    other = User(
        id=uuid.uuid4(),
        username="bob",
        code="E002",
        password_hash="hash",
        name="Bob",
        status="ACTIVE",
    )
    db.users.append(other)
    payload = _event(user)
    payload["person"]["emp_code"] = other.code

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await _post(client, payload)

    assert response.status_code == 409
    assert "冲突" in response.json()["message"]
    assert user.status == "ACTIVE"
    assert other.status == "ACTIVE"
    assert lead.owner_id == user.id
    assert task.owner_id == user.id
    assert task.assignee_id == user.id
    assert approval_task.approver_id == user.id
