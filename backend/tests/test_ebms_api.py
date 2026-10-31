"""EBMS 联调端点 HTTP 层测试（路由装配 / 鉴权依赖 / 响应结构 / 一并投递）。

与 test_ebms_channel_db.py 同样依赖 ``CRM_TEST_DATABASE_URL``；这里走 ASGI 请求，
覆盖端点装配、认证依赖链与响应序列化。只挂载 ebms 路由的**最小应用**，避免连带
AuditMiddleware / Redis / lifespan 等无关依赖。

隔离约定：本文件自建的报价单统一使用专用币种 ``PND163``，因此试点 A 的聚合口径
只可能命中本文件的数据；试点 B 因筛选条件（状态 + 时间）无法用币种隔离，改为
对目标报价单逐条定位断言，不假设全局总条数。
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.endpoints import ebms as ebms_endpoints
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.deps import get_current_user
from app.core.exceptions import AuthError, register_exception_handlers
from app.db.session import get_db
from app.models.business import Company
from app.models.integration import IntegrationLog, IntegrationOutbox
from app.models.pricing import Quotation
from app.models.sales import SalesOrder
from app.services import ebms

TEST_DB_URL = os.environ.get("CRM_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(not TEST_DB_URL, reason="需设置 CRM_TEST_DATABASE_URL 指向已迁移的测试库")

CODE_PREFIX = "PAND163-API-"
TEST_CURRENCY = "PND163"

VALID_RESULT_EXAMPLE = {
    "contract_version": "AEOS.Result.V1",
    "result_id": "RES-EXAMPLE",
    "source_system": "M09",
    "object_type": "BusinessMetric",
    "object_id": "gross_margin",
    "period": {"start": "2026-09-01", "end": "2026-09-30"},
    "metric": {"code": "gross_margin", "value": 0, "unit": "percent", "calculation_version": "M09-GM-V1"},
    "status": "VERIFIED",
    "evidence_ids": ["EVD-EXAMPLE"],
    "trace_id": "TRACE-EXAMPLE",
    "occurred_at": "2026-10-01T09:00:00+08:00",
}


class _StubUser:
    """超级用户桩：令 require_permission 直接放行。"""

    id = uuid.uuid4()
    is_superuser = True
    is_active = True
    permission_codes: list[str] = ["*"]


async def _clean(session) -> None:
    await session.execute(delete(IntegrationLog).where(IntegrationLog.system == "EBMS"))
    await session.execute(
        delete(IntegrationOutbox).where(IntegrationOutbox.event_type.in_((ebms.EVENT_RESULT, ebms.EVENT_EXCEPTION)))
    )
    await session.execute(delete(Quotation).where(Quotation.quotation_no.like(f"{CODE_PREFIX}%")))
    await session.execute(delete(SalesOrder).where(SalesOrder.order_no.like(f"{CODE_PREFIX}%")))
    await session.execute(delete(Company).where(Company.code.like(f"{CODE_PREFIX}%")))
    await session.flush()


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


@pytest.fixture
def api_app(session):
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(ebms_endpoints.router, prefix=settings.API_V1_PREFIX)
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_current_user] = lambda: _StubUser()
    return app


@pytest.fixture
async def client(api_app, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "EBMS_DELIVERY_MODE", "spool")
    monkeypatch.setattr(settings, "EBMS_SPOOL_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "EBMS_INGEST_URL", "")

    transport = httpx.ASGITransport(app=api_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _seed_quotation(session, *, approved_at: datetime) -> Quotation:
    company = Company(code=f"{CODE_PREFIX}{uuid.uuid4().hex[:6]}", name="PAND163 API 客户", currency=TEST_CURRENCY)
    session.add(company)
    await session.flush()
    quotation = Quotation(
        quotation_no=f"{CODE_PREFIX}{uuid.uuid4().hex[:8]}",
        company_id=company.id,
        currency=TEST_CURRENCY,
        total_amount=42.5,
        status="ACCEPTED",
        approved_at=approved_at,
    )
    session.add(quotation)
    await session.flush()
    return quotation


async def _seed_sales_order(session, *, created_at: datetime) -> SalesOrder:
    """16-06=B：交付逾期取 SalesOrder，无 promised_date 时回退 created_at + sla。"""
    order = SalesOrder(
        order_no=f"{CODE_PREFIX}{uuid.uuid4().hex[:8]}",
        line_no="1",
        customer_name="PAND163 API 订单",
        status="open",
    )
    order.created_at = created_at
    session.add(order)
    await session.flush()
    return order


@pytest.fixture
async def seeded(session):
    """试点 A 用：业务时间落在 2026-10-07（+08）。"""
    return await _seed_quotation(session, approved_at=datetime(2026, 10, 7, 10, 0, tzinfo=UTC))


@pytest.fixture
async def overdue(session):
    """试点 B 用：业务时间远早于 as_of，稳定逾期。"""
    return await _seed_sales_order(session, created_at=datetime(2026, 9, 1, 2, 0, tzinfo=UTC))


def test_ebms_routes_are_registered_on_real_router() -> None:
    paths = {getattr(r, "path", "") for r in api_router.routes}
    for expected in (
        "/integrations/ebms/contracts/baseline",
        "/integrations/ebms/contracts/validate",
        "/integrations/ebms/pilot-a/result",
        "/integrations/ebms/pilot-b/exception",
        "/integrations/ebms/deliver",
        "/integrations/ebms/reconcile",
        "/integrations/ebms/logs",
        "/integrations/ebms/outbox",
    ):
        assert expected in paths


async def test_contracts_baseline_lists_versions_and_enum_domains(client) -> None:
    resp = await client.get("/api/v1/integrations/ebms/contracts/baseline")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    contracts = body["data"]["contracts"]
    assert set(contracts) == {"AEOS.Result.V1", "AEOS.Exception.V1"}
    assert contracts["AEOS.Result.V1"]["status_values"] == ["VERIFIED"]
    assert contracts["AEOS.Exception.V1"]["severity_values"] == ["low", "medium", "high", "critical"]
    assert body["data"]["source_system"] == "M05"


async def test_validate_accepts_baseline_example(client) -> None:
    resp = await client.post("/api/v1/integrations/ebms/contracts/validate", json={"contract": VALID_RESULT_EXAMPLE})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["valid"] is True
    assert data["contract_id"] == "RES-EXAMPLE"
    assert data["normalized"]["period"]["start"] == "2026-09-01"
    assert data["errors"] == []


async def test_validate_reports_errors_without_raising(client) -> None:
    broken = {**VALID_RESULT_EXAMPLE, "status": "DRAFT", "unexpected_key": 1}
    resp = await client.post("/api/v1/integrations/ebms/contracts/validate", json={"contract": broken})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["valid"] is False
    assert data["unknown_fields"] == ["unexpected_key"]
    assert data["errors"]


async def test_validate_rejects_unknown_version(client) -> None:
    resp = await client.post(
        "/api/v1/integrations/ebms/contracts/validate",
        json={"contract": {**VALID_RESULT_EXAMPLE, "contract_version": "AEOS.Result.V9"}},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["valid"] is False
    assert "未知契约版本" in data["errors"][0]["message"]


async def test_pilot_a_end_to_end_through_http(client, session, seeded, tmp_path) -> None:
    resp = await client.post(
        "/api/v1/integrations/ebms/pilot-a/result",
        json={
            "period_start": "2026-10-07",
            "period_end": "2026-10-07",
            "metric_code": "order_amount",
            "currency": TEST_CURRENCY,
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["created"] is True
    assert data["metric_value"] == 42.5
    assert data["evidence_count"] == 1
    # 端点默认一并投递（联调一把过）
    assert data["delivery"]["delivered"] == 1
    assert data["delivery"]["mode"] == "spool"
    assert len(list((tmp_path / ebms.EVENT_RESULT).glob("*.json"))) == 1

    log = (await session.execute(select(IntegrationLog).where(IntegrationLog.system == "EBMS"))).scalar_one()
    assert log.status == "SUCCESS"
    assert log.business_id == data["contract_id"]


async def test_pilot_a_idempotent_on_repeat_call(client, seeded) -> None:
    body = {
        "period_start": "2026-10-07",
        "period_end": "2026-10-07",
        "metric_code": "order_amount",
        "currency": TEST_CURRENCY,
    }
    first = (await client.post("/api/v1/integrations/ebms/pilot-a/result", json=body)).json()["data"]
    second = (await client.post("/api/v1/integrations/ebms/pilot-a/result", json=body)).json()["data"]
    assert first["created"] is True
    assert second["created"] is False and second["skipped"] is True
    assert second["idempotency_key"] == first["idempotency_key"]


async def test_pilot_a_rejects_unknown_metric(client, seeded) -> None:
    resp = await client.post(
        "/api/v1/integrations/ebms/pilot-a/result",
        json={"period_start": "2026-10-07", "period_end": "2026-10-07", "metric_code": "gross_margin"},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == 40001


async def test_pilot_b_through_http(client, session, overdue) -> None:
    resp = await client.post(
        "/api/v1/integrations/ebms/pilot-b/exception",
        json={"sla_days": 0, "as_of": "2026-10-07T12:00:00+08:00"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["reason_code"] == "DELIVERY_OVERDUE"

    entry = next(e for e in data["emitted"] if e["object_id"] == overdue.order_no)
    assert entry["created"] is True
    # 业务时间 2026-09-01 02:00Z 距 as_of 约 36 天 → 超过 critical 阈值(30)
    assert entry["days_overdue"] == 36
    assert entry["severity"] == "critical"
    assert entry["contract_id"] == f"EXC-M05-{overdue.order_no}"

    log = (
        await session.execute(
            select(IntegrationLog).where(
                IntegrationLog.system == "EBMS",
                IntegrationLog.action == ebms.ACTION_EXCEPTION,
                IntegrationLog.business_id == entry["contract_id"],
            )
        )
    ).scalar_one()
    assert log.status == "SUCCESS"
    assert log.request_payload["contract_version"] == "AEOS.Exception.V1"
    assert log.request_payload["reason_code"] == "DELIVERY_OVERDUE"
    assert log.request_payload["object_type"] == "SalesOrder"
    assert log.request_payload["evidence_ids"] == [str(overdue.id)]


async def test_logs_and_outbox_are_paginated(client, seeded) -> None:
    await client.post(
        "/api/v1/integrations/ebms/pilot-a/result",
        json={
            "period_start": "2026-10-07",
            "period_end": "2026-10-07",
            "currency": TEST_CURRENCY,
            "deliver": False,
        },
    )

    logs = (await client.get("/api/v1/integrations/ebms/logs")).json()["data"]
    assert logs["total"] == 1
    assert logs["items"][0]["system"] == "EBMS"
    assert logs["items"][0]["action"] == ebms.ACTION_RESULT

    outbox = (await client.get("/api/v1/integrations/ebms/outbox")).json()["data"]
    assert outbox["total"] == 1
    assert outbox["items"][0]["event_type"] == ebms.EVENT_RESULT
    assert outbox["items"][0]["contract_id"].startswith("RES-M05-")
    assert outbox["items"][0]["status"] == "PENDING"

    filtered = (await client.get("/api/v1/integrations/ebms/outbox?status=DONE")).json()["data"]
    assert filtered["total"] == 0

    by_event = (await client.get(f"/api/v1/integrations/ebms/outbox?event_type={ebms.EVENT_EXCEPTION}")).json()["data"]
    assert by_event["total"] == 0


async def test_deliver_and_reconcile_endpoints(client, seeded) -> None:
    await client.post(
        "/api/v1/integrations/ebms/pilot-a/result",
        json={
            "period_start": "2026-10-07",
            "period_end": "2026-10-07",
            "currency": TEST_CURRENCY,
            "deliver": False,
        },
    )
    before = (await client.post("/api/v1/integrations/ebms/reconcile")).json()["data"]
    assert before["result"]["pending"] == 1
    assert before["result"]["delivered"] == 0
    assert before["consistent"] is False

    delivered = (await client.post("/api/v1/integrations/ebms/deliver", json={"limit": 10})).json()["data"]
    assert delivered["picked"] == 1 and delivered["delivered"] == 1

    after = (await client.post("/api/v1/integrations/ebms/reconcile")).json()["data"]
    assert after["result"] == {"produced": 1, "delivered": 1, "pending": 0, "failed": 0}
    assert after["consistent"] is True


async def test_retry_endpoint_on_successful_log_is_noop(client, session, seeded) -> None:
    await client.post(
        "/api/v1/integrations/ebms/pilot-a/result",
        json={"period_start": "2026-10-07", "period_end": "2026-10-07", "currency": TEST_CURRENCY},
    )
    log = (await session.execute(select(IntegrationLog).where(IntegrationLog.system == "EBMS"))).scalar_one()

    resp = await client.post(f"/api/v1/integrations/ebms/retry/{log.id}")
    assert resp.status_code == 200
    assert "无需重试" in resp.json()["data"]["message"]


async def test_retry_unknown_log_returns_404(client) -> None:
    resp = await client.post(f"/api/v1/integrations/ebms/retry/{uuid.uuid4()}")
    assert resp.status_code == 404
    assert resp.json()["code"] == 40004


async def test_endpoints_require_authentication(api_app, monkeypatch) -> None:
    async def _deny() -> _StubUser:
        raise AuthError("未提供认证凭证")

    api_app.dependency_overrides[get_current_user] = _deny
    transport = httpx.ASGITransport(app=api_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/integrations/ebms/logs")
    assert resp.status_code == 401
    assert resp.json()["code"] == 40101


async def test_pilot_b_validation_rejects_negative_sla(client, seeded) -> None:
    resp = await client.post("/api/v1/integrations/ebms/pilot-b/exception", json={"sla_days": -1})
    assert resp.status_code == 422
    assert resp.json()["code"] == 40002


async def test_pilot_a_validation_rejects_reversed_period(client, seeded) -> None:
    resp = await client.post(
        "/api/v1/integrations/ebms/pilot-a/result",
        json={"period_start": "2026-10-08", "period_end": "2026-10-07", "currency": TEST_CURRENCY},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == 40001
