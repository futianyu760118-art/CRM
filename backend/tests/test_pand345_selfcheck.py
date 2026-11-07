"""PAND-345 返工自检：联系人同人判定剥国家码（P0）+ 设主保留关系类型（P1）。

覆盖：
1. 库内存储 ``+86 138-...`` 时，入参 ``138...`` 同人命中 409（反向亦然），
   ``data.existing`` 指向既有联系人。
2. 设主后既有关系类型保留（不重置「其他」）：``PUT /contacts/{id}/primary``
   与 ``PUT /contacts/{id}`` 带 ``is_primary`` 两条路径。
3. 新建关联仍默认关系类型「其他」。

DB 用例依赖 ``CRM_TEST_DATABASE_URL``（未设置时跳过）。

运行：
    CRM_TEST_DATABASE_URL=postgresql+asyncpg://crm:crm123456@localhost:55433/crm \\
    python -m pytest tests/test_pand345_selfcheck.py -v
"""

from __future__ import annotations

import os
import uuid

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.endpoints import contacts as contacts_endpoints
from app.core.config import settings
from app.core.deps import get_current_user
from app.core.exceptions import register_exception_handlers
from app.db.session import get_db
from app.models.business import Company, Contact, ContactCompanyLink

TEST_DB_URL = os.environ.get("CRM_TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not TEST_DB_URL, reason="需设置 CRM_TEST_DATABASE_URL 指向已迁移的测试库")

PREFIX = "PAND345-"
PHONE_A = "13800004501"
PHONE_B = "13800004502"
PHONE_C = "13800004503"


class _StubUser:
    """超级用户桩：令 require_permission 直接放行。"""

    id = uuid.uuid4()
    is_superuser = True
    is_active = True
    department_id = None
    permission_codes: list[str] = ["*"]


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
                    or_(
                        Contact.company_id.in_(cids),
                        Contact.mobile.like("138000045%"),
                        Contact.phone.like("%138-0000-45%"),
                    )
                )
            )
        )
        .scalars()
        .all()
    )
    if contact_ids:
        await session.execute(
            delete(ContactCompanyLink).where(ContactCompanyLink.contact_id.in_(contact_ids))
        )
        await session.execute(delete(Contact).where(Contact.id.in_(contact_ids)))
    if cids:
        await session.execute(delete(Company).where(Company.id.in_(cids)))
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
    app.include_router(contacts_endpoints.router, prefix=settings.API_V1_PREFIX)
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


async def _link(session, contact_id: uuid.UUID) -> ContactCompanyLink:
    return (
        await session.execute(
            select(ContactCompanyLink).where(
                ContactCompanyLink.contact_id == contact_id,
                ContactCompanyLink.deleted_at.is_(None),
            )
        )
    ).scalar_one()


# ------------------------------------------------------------------ P0：国家码剥离
@needs_db
async def test_duplicate_person_matches_across_country_code(client, session) -> None:
    """库内 ``+86 138-0000-4501``，入参 ``13800004501`` → 409 命中既有联系人。"""
    company = await _make_company(session, "C1")
    first = await client.post(
        "/api/v1/contacts",
        json={"company_id": str(company.id), "name": "张三", "phone": "+86 138-0000-4501"},
    )
    assert first.status_code == 201, first.text
    first_id = first.json()["data"]["id"]

    response = await client.post(
        "/api/v1/contacts",
        json={"company_id": str(company.id), "name": "张三B", "mobile": PHONE_A},
    )
    assert response.status_code == 409, response.text
    existing = response.json()["data"]["existing"]
    assert existing["id"] == first_id


@needs_db
async def test_duplicate_person_matches_reverse_direction(client, session) -> None:
    """库内 ``13800004502``，入参 ``+86 138-0000-4502`` → 409 命中既有联系人。"""
    company = await _make_company(session, "C2")
    first = await client.post(
        "/api/v1/contacts",
        json={"company_id": str(company.id), "name": "李四", "mobile": PHONE_B},
    )
    assert first.status_code == 201, first.text
    first_id = first.json()["data"]["id"]

    response = await client.post(
        "/api/v1/contacts",
        json={"company_id": str(company.id), "name": "李四B", "phone": "+86 138-0000-4502"},
    )
    assert response.status_code == 409, response.text
    assert response.json()["data"]["existing"]["id"] == first_id


# ------------------------------------------------------------------ P1：设主保留关系类型
@needs_db
async def test_set_primary_keeps_relation_type(client, session) -> None:
    """PUT /contacts/{id}/primary 后原「决策人」关系保留。"""
    company = await _make_company(session, "C3")
    created = await client.post(
        "/api/v1/contacts",
        json={
            "company_id": str(company.id),
            "name": "王五",
            "mobile": PHONE_C,
            "relation_type": "DECISION_MAKER",
        },
    )
    assert created.status_code == 201, created.text
    contact_id = uuid.UUID(created.json()["data"]["id"])

    response = await client.put(
        f"/api/v1/contacts/{contact_id}/primary", json={"company_id": str(company.id)}
    )
    assert response.status_code == 200, response.text
    assert (await _link(session, contact_id)).relation_type == "DECISION_MAKER"


@needs_db
async def test_update_contact_primary_keeps_relation_type(client, session) -> None:
    """PUT /contacts/{id} 带 is_primary（未传 relation_type）不重置关系类型。"""
    company = await _make_company(session, "C4")
    created = await client.post(
        "/api/v1/contacts",
        json={
            "company_id": str(company.id),
            "name": "赵六",
            "mobile": PHONE_A,
            "relation_type": "PURCHASING",
        },
    )
    assert created.status_code == 201, created.text
    contact_id = uuid.UUID(created.json()["data"]["id"])

    response = await client.put(f"/api/v1/contacts/{contact_id}", json={"is_primary": True})
    assert response.status_code == 200, response.text
    link = await _link(session, contact_id)
    assert link.relation_type == "PURCHASING"
    assert link.is_primary is True


@needs_db
async def test_new_link_defaults_to_other(client, session) -> None:
    """新建关联仍默认「其他」。"""
    company = await _make_company(session, "C5")
    contact = Contact(name="孙七", mobile=PHONE_B)
    session.add(contact)
    await session.commit()

    response = await client.post(
        f"/api/v1/contacts/{contact.id}/links", json={"company_id": str(company.id)}
    )
    assert response.status_code == 200, response.text
    assert (await _link(session, contact.id)).relation_type == "OTHER"
