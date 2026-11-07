"""PAND-330 数据库自检：revision 监听器 / Object 六列 / Verification 闭环。

需指向已执行 ``alembic upgrade head`` 的测试库：

    CRM_TEST_DATABASE_URL=postgresql+asyncpg://crm:crm123456@localhost:55433/crm \
    python -m pytest tests/test_pand330_db.py

未设置时整文件跳过。
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.exceptions import ApiError
from app.models.business import Company, Contact, Inquiry, Lead, Opportunity
from app.models.integration import IntegrationLog, IntegrationOutbox
from app.models.pricing import Quotation
from app.models.sales import Feedback, QuoteLibrary, SalesOrder, SalesResult, Sample
from app.models.verification import Verification
from app.services import ebms
from app.services import verify as verify_service

TEST_DB_URL = os.environ.get("CRM_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(not TEST_DB_URL, reason="需设置 CRM_TEST_DATABASE_URL 指向已迁移的测试库")

AEOS_OBJECT_MODELS = (
    Company,
    Contact,
    Lead,
    Opportunity,
    Inquiry,
    Quotation,
    SalesOrder,
    Sample,
    QuoteLibrary,
    Feedback,
)
AEOS_COLUMNS = {"tenant_id", "revision", "fact_owner", "processor", "consumer", "verifier"}
CODE_PREFIX = "PAND330-"


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
            IntegrationOutbox.event_type.in_(
                (ebms.EVENT_RESULT, ebms.EVENT_EXCEPTION, ebms.EVENT_ENTITY, ebms.EVENT_ENTITY_V2)
            )
        )
    )
    await session.execute(delete(Verification).where(Verification.subject_type == verify_service.SUBJECT_TYPE_RESULT))
    await session.execute(delete(SalesResult).where(SalesResult.result_id.like("PAND330-%")))
    await session.execute(delete(Company).where(Company.code.like(f"{CODE_PREFIX}%")))
    await session.flush()


async def _seed_result(session, *, result_id: str | None = None, value: float = 100.0) -> SalesResult:
    row = SalesResult(
        result_id=result_id or f"{CODE_PREFIX}RES-{uuid.uuid4().hex[:8]}",
        period_start=date(2026, 10, 1),
        period_end=date(2026, 10, 7),
        metric_code="order_amount",
        metric_value=value,
        metric_unit="currency",
        calculation_version="M05-ORDER-AMOUNT-V1",
        currency="RMB",
        order_count=1,
        object_ref_type="BusinessMetric",
        object_ref_id="order_amount",
        status="submitted",
        evidence_refs=["E1"],
    )
    session.add(row)
    await session.flush()
    return row


class TestAeosObjectColumns:
    def test_all_ten_tables_have_six_columns(self) -> None:
        for model in AEOS_OBJECT_MODELS:
            columns = {c.name for c in model.__table__.columns}
            assert columns >= AEOS_COLUMNS, f"{model.__tablename__} 缺少 {AEOS_COLUMNS - columns}"

    def test_integration_log_has_compat_column(self) -> None:
        assert "compat" in {c.name for c in IntegrationLog.__table__.columns}


class TestRevisionListener:
    async def test_business_field_change_bumps_revision_once(self, session) -> None:
        company = Company(code=f"{CODE_PREFIX}{uuid.uuid4().hex[:8]}", name="PAND330 客户")
        session.add(company)
        await session.flush()
        assert company.revision == 1

        company.name = "PAND330 客户（改名）"
        await session.flush()
        assert company.revision == 2

    async def test_same_value_assignment_does_not_bump(self, session) -> None:
        company = Company(code=f"{CODE_PREFIX}{uuid.uuid4().hex[:8]}", name="PAND330 客户")
        session.add(company)
        await session.flush()

        company.name = company.name
        await session.flush()
        assert company.revision == 1

    async def test_sync_status_change_does_not_bump(self, session) -> None:
        company = Company(code=f"{CODE_PREFIX}{uuid.uuid4().hex[:8]}", name="PAND330 客户")
        session.add(company)
        await session.flush()

        company.sync_status = "SYNCED"
        company.last_sync_at = datetime.now(UTC)
        await session.flush()
        assert company.revision == 1

    async def test_multiple_business_fields_bump_only_once_per_flush(self, session) -> None:
        company = Company(code=f"{CODE_PREFIX}{uuid.uuid4().hex[:8]}", name="PAND330 客户")
        session.add(company)
        await session.flush()

        company.name = "改名"
        company.currency = "USD"
        await session.flush()
        assert company.revision == 2


class TestVerificationLifecycle:
    async def test_failed_without_reason_rejected(self, session) -> None:
        row = await _seed_result(session)
        with pytest.raises(ApiError):
            await verify_service.verify_result(
                session, subject_id=row.result_id, verifier=uuid.uuid4(), status="failed"
            )

    async def test_invalid_status_rejected(self, session) -> None:
        row = await _seed_result(session)
        with pytest.raises(ApiError):
            await verify_service.verify_result(
                session, subject_id=row.result_id, verifier=uuid.uuid4(), status="approved"
            )

    async def test_verifier_required(self, session) -> None:
        row = await _seed_result(session)
        with pytest.raises(ApiError):
            await verify_service.verify_result(session, subject_id=row.result_id, verifier=None, status="passed")

    async def test_failed_does_not_change_result_status(self, session) -> None:
        row = await _seed_result(session)
        outcome = await verify_service.verify_result(
            session, subject_id=row.result_id, verifier=uuid.uuid4(), status="failed", reason="数据不符"
        )
        assert outcome["verification"]["status"] == "failed"
        assert outcome["result"]["status"] == "submitted"
        assert outcome["delivery"] is None and outcome["event"] is None
        assert (await session.execute(select(IntegrationOutbox))).scalars().all() == []

    async def test_passed_transitions_and_emits_result_plus_v2_event(self, session) -> None:
        row = await _seed_result(session)
        verifier = uuid.uuid4()
        outcome = await verify_service.verify_result(
            session, subject_id=row.result_id, verifier=verifier, status="passed", evidence_refs=["E2"]
        )

        assert outcome["duplicate"] is False
        assert outcome["verification"]["subject_revision"] == 1
        assert outcome["result"]["status"] == "verified"
        assert outcome["result"]["verifier"] == str(verifier)
        # state transition is not a business-content change → revision unchanged
        assert outcome["result"]["revision"] == 1
        assert outcome["delivery"]["created"] is True
        assert outcome["event"]["contract_version"] == "AEOS.Event.V2"
        assert outcome["event"]["event_type"] == "SalesResultVerified"

        outbox = (await session.execute(select(IntegrationOutbox))).scalars().all()
        assert {r.event_type for r in outbox} == {ebms.EVENT_RESULT, ebms.EVENT_ENTITY_V2}
        result_payload = next(r.payload for r in outbox if r.event_type == ebms.EVENT_RESULT)
        assert result_payload["status"] == "VERIFIED"
        assert result_payload["evidence_ids"] == ["E1"]
        v2_payload = next(r.payload for r in outbox if r.event_type == ebms.EVENT_ENTITY_V2)
        assert v2_payload["payload"]["verification_id"] == outcome["verification"]["verification_id"]

    async def test_verify_is_idempotent_per_subject_revision(self, session) -> None:
        row = await _seed_result(session)
        verifier = uuid.uuid4()
        first = await verify_service.verify_result(
            session, subject_id=row.result_id, verifier=verifier, status="passed"
        )
        second = await verify_service.verify_result(
            session, subject_id=row.result_id, verifier=verifier, status="passed"
        )

        assert second["duplicate"] is True
        assert second["verification"]["verification_id"] == first["verification"]["verification_id"]
        assert len((await session.execute(select(Verification))).scalars().all()) == 1
        result_outbox = (
            await session.execute(select(IntegrationOutbox).where(IntegrationOutbox.event_type == ebms.EVENT_RESULT))
        ).scalars().all()
        assert len(result_outbox) == 1

    async def test_new_revision_allows_reverification(self, session) -> None:
        row = await _seed_result(session)
        verifier = uuid.uuid4()
        await verify_service.verify_result(session, subject_id=row.result_id, verifier=verifier, status="passed")

        # 指标重算：业务字段变化 → revision +1 并回到 submitted
        row.metric_value = 200.0
        row.status = "submitted"
        await session.flush()
        assert row.revision == 2

        outcome = await verify_service.verify_result(
            session, subject_id=row.result_id, verifier=verifier, status="passed"
        )
        assert outcome["duplicate"] is False
        assert outcome["verification"]["subject_revision"] == 2
        assert outcome["result"]["status"] == "verified"

    async def test_unknown_result_raises_not_found(self, session) -> None:
        from app.core.exceptions import NotFoundError

        with pytest.raises(NotFoundError):
            await verify_service.verify_result(
                session, subject_id="PAND330-NO-SUCH", verifier=uuid.uuid4(), status="passed"
            )
