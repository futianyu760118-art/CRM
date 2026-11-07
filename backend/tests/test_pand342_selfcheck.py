"""PAND-342 回归：线索转化查重「空原因误报」。

缺陷：``check_company_duplicates`` 联系人循环无条件
``reasons.setdefault(row.company_id, [])``，免费邮箱域名命中 SQL 预筛但
``shares_email_domain`` 返回 False、电话也不等时，仍以 ``reason=""`` 进入
``suspected``，导致同免费邮箱域的第二条不同线索转化被 409 误拦。

覆盖：
1. 同免费邮箱域、名称/电话均不同 → 不产生候选（修复前为 reason="" 的疑似候选）。
2. 同手机号 → 仍报疑似且 reason 非空。
3. 真实 HTTP 链路：同免费邮箱域两条线索连续转化均 200，同手机第三条 409。

DB 用例依赖 ``CRM_TEST_DATABASE_URL``（未设置时跳过）。

运行：
    CRM_TEST_DATABASE_URL=postgresql+asyncpg://crm:crm123456@localhost:5432/crm \\
    python -m pytest tests/test_pand342_selfcheck.py -v
"""

from __future__ import annotations

import os
import uuid

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.endpoints import leads as leads_endpoints
from app.core.config import settings
from app.core.deps import get_current_user
from app.core.exceptions import register_exception_handlers
from app.db.session import get_db
from app.models.business import BusinessCode, Company, Contact, ContactCompanyLink, Lead
from app.services import dedup

TEST_DB_URL = os.environ.get("CRM_TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not TEST_DB_URL, reason="需设置 CRM_TEST_DATABASE_URL 指向已迁移的测试库")

PREFIX = "PAND342-"
FREE_DOMAIN = "outlook.com"
MOBILE_A = "13900004201"
MOBILE_B = "13900004202"


class _StubUser:
    """超级用户桩：令 require_permission 直接放行。"""

    id = uuid.uuid4()
    is_superuser = True
    is_active = True
    department_id = None
    permission_codes: list[str] = ["*"]


# ------------------------------------------------------------------ DB 夹具
async def _clean(session) -> None:
    company_ids = (
        (
            await session.execute(
                select(Company.id).where(or_(Company.code.like(f"{PREFIX}%"), Company.name.like(f"{PREFIX}%")))
            )
        )
        .scalars()
        .all()
    )
    contact_ids = (
        (
            await session.execute(
                select(Contact.id).where(or_(Contact.company_id.in_(company_ids), Contact.mobile.like("139000042%")))
            )
        )
        .scalars()
        .all()
    )
    if contact_ids:
        await session.execute(delete(ContactCompanyLink).where(ContactCompanyLink.contact_id.in_(contact_ids)))
        await session.execute(delete(Contact).where(Contact.id.in_(contact_ids)))
    if company_ids:
        await session.execute(delete(BusinessCode).where(BusinessCode.company_id.in_(company_ids)))
        await session.execute(delete(Company).where(Company.id.in_(company_ids)))
    await session.execute(delete(Lead).where(Lead.lead_no.like(f"{PREFIX}%")))
    await session.flush()


@pytest.fixture
async def session():
    engine = create_async_engine(TEST_DB_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with factory() as s:
        await _clean(s)
        yield s
        await s.rollback()
        await _clean(s)
        await s.commit()
    await engine.dispose()


@pytest.fixture
def api_app(session):
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(leads_endpoints.router, prefix=settings.API_V1_PREFIX)
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_current_user] = lambda: _StubUser()
    return app


@pytest.fixture
async def client(api_app):
    transport = httpx.ASGITransport(app=api_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _make_company_with_contact(session, suffix: str, *, email: str, mobile: str) -> Company:
    company = Company(code=f"{PREFIX}C-{suffix}", name=f"{PREFIX}客户{suffix}")
    session.add(company)
    await session.flush()
    session.add(Contact(company_id=company.id, name=f"联系人{suffix}", email=email, mobile=mobile))
    await session.commit()
    return company


# ------------------------------------------------------------------ 1. 空原因误报
@needs_db
async def test_same_free_mail_domain_is_not_duplicate(session) -> None:
    """同免费邮箱域、名称/电话不同：不得产生候选（修复前 reason="" 误判）。"""
    await _make_company_with_contact(session, "1", email=f"first@{FREE_DOMAIN}", mobile=MOBILE_A)

    result = await dedup.check_company_duplicates(
        session,
        name=f"{PREFIX}客户二",
        email=f"second@{FREE_DOMAIN}",
        phone=MOBILE_B,
    )

    assert result["total"] == 0
    assert result["suspected"] == []


@needs_db
async def test_same_phone_still_reported_with_reason(session) -> None:
    """真实重复（同手机号）仍为疑似候选，且 reason 非空。"""
    await _make_company_with_contact(session, "2", email=f"third@{FREE_DOMAIN}", mobile=MOBILE_A)

    result = await dedup.check_company_duplicates(
        session,
        name=f"{PREFIX}客户三",
        email="other@example.org",
        phone=MOBILE_A,
    )

    assert len(result["suspected"]) == 1
    reason = result["suspected"][0]["reason"]
    assert reason
    assert "联系人电话一致" in reason


# ------------------------------------------------------------------ 2. 转化链路
@needs_db
async def test_convert_two_leads_same_free_domain_then_real_duplicate(client, session, monkeypatch) -> None:
    """同免费邮箱域两条线索连续转化均 200；同手机第三条 409 且 reason 非空。"""
    codes = iter(range(1, 10))

    async def fake_next_code(owner):  # noqa: ANN001 - 避开编号序列依赖，聚焦查重逻辑
        seq = next(codes)
        return f"{PREFIX}CODE-{seq}", seq, seq

    monkeypatch.setattr(leads_endpoints.company_code, "next_company_code", fake_next_code)

    lead_a = Lead(
        lead_no=f"{PREFIX}LD-A",
        name=f"{PREFIX}公司甲",
        contact_name="甲方",
        email=f"alias-a@{FREE_DOMAIN}",
        phone=MOBILE_A,
    )
    lead_b = Lead(
        lead_no=f"{PREFIX}LD-B",
        name=f"{PREFIX}公司乙",
        contact_name="乙方",
        email=f"alias-b@{FREE_DOMAIN}",
        phone=MOBILE_B,
    )
    lead_c = Lead(
        lead_no=f"{PREFIX}LD-C",
        name=f"{PREFIX}公司丙",
        contact_name="丙方",
        email=f"alias-c@{FREE_DOMAIN}",
        phone=MOBILE_A,
    )
    session.add_all([lead_a, lead_b, lead_c])
    await session.commit()

    first = await client.post(f"/api/v1/leads/{lead_a.id}/convert", json={"create_contact": True})
    assert first.status_code == 200, first.text

    second = await client.post(f"/api/v1/leads/{lead_b.id}/convert", json={"create_contact": False})
    assert second.status_code == 200, second.text

    third = await client.post(f"/api/v1/leads/{lead_c.id}/convert", json={"create_contact": False})
    assert third.status_code == 409, third.text
    candidates = third.json()["data"]["candidates"]
    assert candidates
    assert all(candidate["reason"] for candidate in candidates)
