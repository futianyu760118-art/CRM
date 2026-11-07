"""PAND-340 返工自检：R4 两项联系人缺陷。

覆盖：
1. 线索转化 ``create_contact=true`` / ``POST /contacts`` 带 ``is_primary=true``
   不再触发 ``uq_contact_company_link`` 唯一冲突，且联系人确为主要联系人。
2. 同人冲突返回 409（而非 500），``data.existing`` 返回既有联系人，
   关联客户 ``company_id`` 为可 JSON 序列化的字符串。
3. 异常处理器对原始 ``uuid.UUID`` 兜底序列化（防止同类 500 回归）。

DB 用例依赖 ``CRM_TEST_DATABASE_URL``（未设置时跳过）；纯逻辑用例无需数据库。

运行：
    CRM_TEST_DATABASE_URL=postgresql+asyncpg://crm:crm123456@localhost:55433/crm \\
    python -m pytest tests/test_pand340_selfcheck.py -v
"""

from __future__ import annotations

import json
import os
import uuid

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.endpoints import contacts as contacts_endpoints
from app.api.v1.endpoints import leads as leads_endpoints
from app.core.config import settings
from app.core.deps import get_current_user
from app.core.error_codes import ErrCode
from app.core.exceptions import ApiError, register_exception_handlers
from app.db.session import get_db
from app.models.business import Company, Contact, ContactCompanyLink, Lead

TEST_DB_URL = os.environ.get("CRM_TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not TEST_DB_URL, reason="需设置 CRM_TEST_DATABASE_URL 指向已迁移的测试库")

PREFIX = "PAND340-"
MOBILE_A = "13900003401"
MOBILE_B = "13900003402"
MOBILE_C = "13900003403"


class _StubUser:
    """超级用户桩：令 require_permission 直接放行。"""

    id = uuid.uuid4()
    is_superuser = True
    is_active = True
    department_id = None
    permission_codes: list[str] = ["*"]


# ------------------------------------------------------------------ 纯逻辑
async def test_api_error_handler_serializes_uuid() -> None:
    """ApiError.data 含原始 UUID 时不得抛 500（缺陷②回归兜底）。"""
    app = FastAPI()
    register_exception_handlers(app)
    handler = app.exception_handlers[ApiError]
    company_id = uuid.uuid4()
    exc = ApiError(
        ErrCode.CONFLICT,
        "联系人冲突",
        http_status=409,
        data={"existing": {"company_id": company_id}},
    )
    response = await handler(None, exc)  # type: ignore[arg-type]
    body = json.loads(response.body)
    assert response.status_code == 409
    assert body["data"]["existing"]["company_id"] == str(company_id)


# ------------------------------------------------------------------ DB 夹具
async def _clean(session) -> None:
    cids = (
        (await session.execute(select(Company.id).where(Company.code.like(f"{PREFIX}%"))))
        .scalars()
        .all()
    )
    contact_ids = (
        (
            await session.execute(
                select(Contact.id).where(
                    or_(Contact.company_id.in_(cids), Contact.mobile.like("139000034%"))
                )
            )
        )
        .scalars()
        .all()
    )
    if contact_ids:
        await session.execute(delete(ContactCompanyLink).where(ContactCompanyLink.contact_id.in_(contact_ids)))
        await session.execute(delete(Contact).where(Contact.id.in_(contact_ids)))
    if cids:
        await session.execute(delete(Company).where(Company.id.in_(cids)))
    await session.execute(delete(Lead).where(Lead.lead_no.like(f"{PREFIX}%")))
    await session.flush()


@pytest.fixture
async def session():
    engine = create_async_engine(TEST_DB_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with factory() as s:
        await _clean(s)
        yield s
        await s.rollback()  # 失败用例可能遗留 aborted 事务
        await _clean(s)
        await s.commit()
    await engine.dispose()


@pytest.fixture
def api_app(session):
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(contacts_endpoints.router, prefix=settings.API_V1_PREFIX)
    app.include_router(leads_endpoints.router, prefix=settings.API_V1_PREFIX)
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_current_user] = lambda: _StubUser()
    return app


@pytest.fixture
async def client(api_app):
    transport = httpx.ASGITransport(app=api_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _make_company(session, suffix: str) -> Company:
    company = Company(code=f"{PREFIX}{suffix}", name=f"{PREFIX}客户{suffix}")
    session.add(company)
    await session.commit()
    return company


async def _links(session, contact_id: uuid.UUID) -> list[ContactCompanyLink]:
    return (
        (
            await session.execute(
                select(ContactCompanyLink).where(
                    ContactCompanyLink.contact_id == contact_id,
                    ContactCompanyLink.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )


# ------------------------------------------------------------------ 缺陷①：唯一冲突
@needs_db
async def test_create_contact_with_is_primary(client, session) -> None:
    """POST /contacts 带 is_primary=true：201，且仅一条 link 为主联系人。"""
    company = await _make_company(session, "C1")
    body = {"company_id": str(company.id), "name": "张主联系人", "mobile": MOBILE_A, "is_primary": True}
    response = await client.post("/api/v1/contacts", json=body)
    assert response.status_code == 201, response.text

    data = response.json()["data"]
    assert data["is_primary"] is True
    links = await _links(session, uuid.UUID(data["id"]))
    assert len(links) == 1
    assert links[0].is_primary is True
    assert links[0].company_id == company.id


@needs_db
async def test_convert_lead_with_create_contact_is_primary(client, session) -> None:
    """线索转化 create_contact=true：200，联系人成为主要联系人（原 500 路径）。"""
    company = await _make_company(session, "C2")
    lead = Lead(
        lead_no=f"{PREFIX}LEAD-1",
        name="转化线索客户",
        contact_name="李四",
        email="pand340-lead@example.com",
        phone=MOBILE_B,
    )
    session.add(lead)
    await session.commit()

    response = await client.post(
        f"/api/v1/leads/{lead.id}/convert",
        json={"create_contact": True, "link_company_id": str(company.id)},
    )
    assert response.status_code == 200, response.text
    contact_id = response.json()["data"]["contact_id"]
    assert contact_id

    contact = await session.get(Contact, uuid.UUID(contact_id))
    assert contact is not None
    assert contact.is_primary is True
    links = await _links(session, contact.id)
    assert len(links) == 1
    assert links[0].is_primary is True


@needs_db
async def test_update_contact_is_primary_same_company(client, session) -> None:
    """存量联系人（有主公司、无 link 行）PUT is_primary：同事务二次 attach 不冲突。"""
    company = await _make_company(session, "C3")
    legacy = Contact(company_id=company.id, name="王五", mobile=MOBILE_C)
    session.add(legacy)
    await session.commit()

    response = await client.put(
        f"/api/v1/contacts/{legacy.id}",
        json={"company_id": str(company.id), "is_primary": True},
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["is_primary"] is True
    links = await _links(session, legacy.id)
    assert len(links) == 1
    assert links[0].is_primary is True


@needs_db
async def test_add_link_with_is_primary(client, session) -> None:
    """POST /contacts/{id}/links 带 is_primary：新增关联并设主，不冲突。"""
    company = await _make_company(session, "C4")
    contact = Contact(name="赵六", mobile=MOBILE_C)
    session.add(contact)
    await session.commit()

    response = await client.post(
        f"/api/v1/contacts/{contact.id}/links",
        json={"company_id": str(company.id), "is_primary": True},
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["is_primary"] is True
    links = await _links(session, contact.id)
    assert len(links) == 1
    assert links[0].is_primary is True


@needs_db
async def test_set_primary_demotes_previous(client, session) -> None:
    """PUT /contacts/{id}/primary：新主置位、旧主取消。"""
    company = await _make_company(session, "C5")
    first = await client.post(
        "/api/v1/contacts",
        json={"company_id": str(company.id), "name": "主A", "mobile": MOBILE_A, "is_primary": True},
    )
    assert first.status_code == 201, first.text
    second = await client.post(
        "/api/v1/contacts",
        json={"company_id": str(company.id), "name": "主B", "mobile": MOBILE_B},
    )
    assert second.status_code == 201, second.text

    response = await client.put(
        f"/api/v1/contacts/{second.json()['data']['id']}/primary",
        json={"company_id": str(company.id)},
    )
    assert response.status_code == 200, response.text

    first_link = (await _links(session, uuid.UUID(first.json()["data"]["id"])))[0]
    second_link = (await _links(session, uuid.UUID(second.json()["data"]["id"])))[0]
    assert second_link.is_primary is True
    assert first_link.is_primary is False


# ------------------------------------------------------------------ 缺陷②：同人冲突 409
@needs_db
async def test_duplicate_person_returns_409(client, session) -> None:
    """同手机建联系人返回 409，data.existing 可序列化且含既有联系人。"""
    company = await _make_company(session, "C6")
    first = await client.post(
        "/api/v1/contacts",
        json={"company_id": str(company.id), "name": "原联系人", "mobile": MOBILE_A},
    )
    assert first.status_code == 201, first.text

    response = await client.post(
        "/api/v1/contacts",
        json={"company_id": str(company.id), "name": "同手机新人", "mobile": MOBILE_A},
    )
    assert response.status_code == 409, response.text

    body = response.json()
    existing = body["data"]["existing"]
    assert existing["name"] == "原联系人"
    assert isinstance(existing["companies"][0]["company_id"], str)
    assert existing["companies"][0]["company_id"] == str(company.id)
