"""PAND-330 F5-A06：结果查询 / 验证权限相互独立（View / Operation / Verify）。

依赖已迁移测试库（``CRM_TEST_DATABASE_URL``），未设置时跳过。
"""

from __future__ import annotations

import os
import uuid
from datetime import date

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.endpoints import results as results_endpoints
from app.core.config import settings
from app.core.deps import get_current_user
from app.core.exceptions import register_exception_handlers
from app.db.session import get_db
from app.models.integration import IntegrationLog, IntegrationOutbox
from app.models.sales import SalesResult
from app.models.verification import Verification

TEST_DB_URL = os.environ.get("CRM_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(not TEST_DB_URL, reason="需设置 CRM_TEST_DATABASE_URL 指向已迁移的测试库")

CODE_PREFIX = "PAND330-API-"


class _StubUser:
    def __init__(self, *codes: str) -> None:
        self.id = uuid.uuid4()
        self.is_superuser = False
        self.is_active = True
        self.permission_codes = list(codes)
        self.roles: list = []
        self.department_id = None


@pytest.fixture
async def session():
    engine = create_async_engine(TEST_DB_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with factory() as s:
        await _clean(s)
        yield s
        await _clean(s)
        await s.commit()
    await engine.dispose()


async def _clean(session) -> None:
    await session.execute(delete(IntegrationLog).where(IntegrationLog.system == "EBMS"))
    await session.execute(
        delete(IntegrationOutbox).where(
            IntegrationOutbox.event_type.in_(("AEOS_RESULT_V1", "AEOS_EVENT_V2"))
        )
    )
    await session.execute(delete(Verification).where(Verification.subject_id.like(f"{CODE_PREFIX}%")))
    await session.execute(delete(SalesResult).where(SalesResult.result_id.like(f"{CODE_PREFIX}%")))
    await session.flush()


@pytest.fixture
async def result_row(session) -> SalesResult:
    row = SalesResult(
        result_id=f"{CODE_PREFIX}{uuid.uuid4().hex[:8]}",
        period_start=date(2026, 10, 1),
        period_end=date(2026, 10, 7),
        metric_code="order_amount",
        metric_value=100.0,
        metric_unit="currency",
        calculation_version="M05-ORDER-AMOUNT-V1",
        currency="RMB",
        order_count=1,
        object_ref_type="BusinessMetric",
        object_ref_id="order_amount",
        status="submitted",
        evidence_refs=[],
    )
    session.add(row)
    await session.flush()
    return row


@pytest.fixture
def api_app(session):
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(results_endpoints.router, prefix=settings.API_V1_PREFIX)
    app.dependency_overrides[get_db] = lambda: session
    return app


async def _client(api_app, *codes: str) -> httpx.AsyncClient:
    api_app.dependency_overrides[get_current_user] = lambda: _StubUser(*codes)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=api_app), base_url="http://test")


async def test_view_permission_can_read_but_not_verify(api_app, result_row) -> None:
    async with await _client(api_app, "result:view") as client:
        listing = await client.get("/api/v1/results")
        assert listing.status_code == 200
        detail = await client.get(f"/api/v1/results/{result_row.result_id}")
        assert detail.status_code == 200

        denied = await client.post(
            f"/api/v1/results/{result_row.result_id}/verify", json={"status": "passed"}
        )
        assert denied.status_code == 403


async def test_operation_permission_cannot_read_or_verify(api_app, result_row) -> None:
    async with await _client(api_app, "result:operation") as client:
        assert (await client.get("/api/v1/results")).status_code == 403
        denied = await client.post(
            f"/api/v1/results/{result_row.result_id}/verify", json={"status": "passed"}
        )
        assert denied.status_code == 403


async def test_verify_permission_verifies_without_view(api_app, result_row) -> None:
    async with await _client(api_app, "result:verify") as client:
        assert (await client.get("/api/v1/results")).status_code == 403

        ok = await client.post(
            f"/api/v1/results/{result_row.result_id}/verify", json={"status": "passed"}
        )
        assert ok.status_code == 200
        data = ok.json()["data"]
        assert data["duplicate"] is False
        assert data["result"]["status"] == "verified"
        assert data["verification"]["status"] == "passed"

        again = await client.post(
            f"/api/v1/results/{result_row.result_id}/verify", json={"status": "passed"}
        )
        assert again.json()["data"]["duplicate"] is True


async def test_verification_history_requires_view(api_app, result_row) -> None:
    async with await _client(api_app, "result:view", "result:verify") as client:
        await client.post(f"/api/v1/results/{result_row.result_id}/verify", json={"status": "passed"})
        history = await client.get(f"/api/v1/results/{result_row.result_id}/verifications")
        assert history.status_code == 200
        assert len(history.json()["data"]) == 1
