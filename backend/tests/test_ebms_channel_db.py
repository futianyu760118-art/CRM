"""EBMS 集成通道 DB 集成测试（幂等 / 投递 / 重试 / 对账 / 试点 A、B）。

需指向一个**已执行 alembic upgrade head 的**测试库：

    CRM_TEST_DATABASE_URL=postgresql+asyncpg://crm:crm123456@localhost:55433/crm \\
    python -m pytest tests/test_ebms_channel_db.py

未设置该环境变量时整文件跳过（不依赖外部 DB 的用例见 test_aeos_contracts.py /
test_ebms_transport.py）。测试只清理自身写入的 PAND163-* 前缀数据与 EBMS 日志。
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.business import Company, Inquiry, InquiryItem
from app.models.integration import IntegrationLog, IntegrationOutbox
from app.models.pricing import Quotation
from app.models.sales import SalesOrder
from app.services import ebms, ebms_sync
from app.services.ebms_transport import DeliveryResult, EbmsTransport

TEST_DB_URL = os.environ.get("CRM_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(not TEST_DB_URL, reason="需设置 CRM_TEST_DATABASE_URL 指向已迁移的测试库")

CN_TZ = timezone(timedelta(hours=8))
CODE_PREFIX = "PAND163-"
#: 判定时点：2026-10-07 12:00 +08
AS_OF = datetime(2026, 10, 7, 12, 0, tzinfo=CN_TZ)
#: 逾期订单业务时间：与 AS_OF 恰好相差 60 天（2026-08-08 12:00 +08）
OVERDUE_AT = datetime(2026, 8, 8, 4, 0, tzinfo=UTC)


async def _clean(session) -> None:
    """只清理本测试写入的数据。"""
    await session.execute(delete(IntegrationLog).where(IntegrationLog.system == "EBMS"))
    await session.execute(
        delete(IntegrationOutbox).where(
            IntegrationOutbox.event_type.in_((ebms.EVENT_RESULT, ebms.EVENT_EXCEPTION, ebms.EVENT_ENTITY))
        )
    )
    await session.execute(delete(Quotation).where(Quotation.quotation_no.like(f"{CODE_PREFIX}%")))
    await session.execute(delete(SalesOrder).where(SalesOrder.order_no.like(f"{CODE_PREFIX}%")))
    inquiry_ids = select(Inquiry.id).where(Inquiry.inquiry_no.like(f"{CODE_PREFIX}%"))
    await session.execute(delete(InquiryItem).where(InquiryItem.inquiry_id.in_(inquiry_ids)))
    await session.execute(delete(Inquiry).where(Inquiry.inquiry_no.like(f"{CODE_PREFIX}%")))
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


async def _seed_company(session) -> Company:
    company = Company(code=f"{CODE_PREFIX}{uuid.uuid4().hex[:8]}", name="PAND163 联调客户", currency="RMB")
    session.add(company)
    await session.flush()
    return company


async def _seed_quotation(
    session,
    company: Company,
    *,
    status: str = "ACCEPTED",
    amount: float | None = 100.0,
    approved_at: datetime | None = None,
    currency: str = "RMB",
) -> Quotation:
    quotation = Quotation(
        quotation_no=f"{CODE_PREFIX}{uuid.uuid4().hex[:8]}",
        company_id=company.id,
        currency=currency,
        total_amount=amount,
        status=status,
        approved_at=approved_at or datetime.now(UTC),
    )
    session.add(quotation)
    await session.flush()
    return quotation


async def _seed_sales_order(
    session,
    *,
    status: str = "open",
    promised_date: date | None = None,
    created_at: datetime | None = None,
) -> SalesOrder:
    """16-06=B：交付逾期取 SalesOrder。有 promised_date 走交期口径，无则回退 created_at + sla。"""
    order = SalesOrder(
        order_no=f"{CODE_PREFIX}{uuid.uuid4().hex[:8]}",
        line_no="1",
        customer_name="PAND163 联调订单",
        status=status,
        promised_date=promised_date,
    )
    if created_at is not None:
        order.created_at = created_at
    session.add(order)
    await session.flush()
    return order


async def _ebms_logs(session) -> list[IntegrationLog]:
    return list(
        (
            await session.execute(
                select(IntegrationLog).where(IntegrationLog.system == "EBMS").order_by(IntegrationLog.created_at)
            )
        )
        .scalars()
        .all()
    )


async def _outbox_count(session, event_type: str) -> int:
    return int(
        (
            await session.execute(
                select(func.count()).select_from(IntegrationOutbox).where(IntegrationOutbox.event_type == event_type)
            )
        ).scalar_one()
    )


# ---------------------------------------------------------------- 试点 A


class TestPilotASalesResult:
    async def test_aggregates_only_accepted_orders_in_period(self, session) -> None:
        company = await _seed_company(session)
        today = date(2026, 10, 7)
        in_period = datetime(2026, 10, 7, 10, 0, tzinfo=UTC)
        await _seed_quotation(session, company, amount=100.5, approved_at=in_period)
        await _seed_quotation(session, company, amount=200.25, approved_at=in_period)
        # 干扰项：区间外
        await _seed_quotation(session, company, amount=999.0, approved_at=datetime(2026, 7, 1, 10, 0, tzinfo=UTC))
        # 干扰项：状态不符
        await _seed_quotation(session, company, status="SENT", amount=888.0, approved_at=in_period)
        # 干扰项：币种不符
        await _seed_quotation(session, company, amount=777.0, approved_at=in_period, currency="USD")

        out = await ebms.emit_sales_result(
            session, period_start=today, period_end=today, metric_code="order_amount", currency="RMB"
        )

        assert out["created"] is True
        assert out["metric_value"] == 300.75
        assert out["order_count"] == 2
        assert out["evidence_count"] == 2
        assert out["contract_id"].startswith("RES-M05-ORDER_AMOUNT-20261007-20261007-RMB")

        logs = await _ebms_logs(session)
        assert len(logs) == 1
        contract = logs[0].request_payload
        assert contract["contract_version"] == "AEOS.Result.V1"
        assert contract["source_system"] == "M05"
        assert contract["object_type"] == "BusinessMetric"
        assert contract["object_id"] == "order_amount"
        assert contract["status"] == "VERIFIED"
        assert contract["metric"]["calculation_version"] == "M05-ORDER-AMOUNT-V1"
        assert contract["metric"]["unit"] == "currency"
        assert contract["period"] == {"start": "2026-10-07", "end": "2026-10-07"}
        assert contract["occurred_at"] == "2026-10-07T23:59:59+08:00"

        outbox = (
            await session.execute(select(IntegrationOutbox).where(IntegrationOutbox.event_type == ebms.EVENT_RESULT))
        ).scalar_one()
        assert outbox.status == "PENDING"
        assert outbox.payload["result_id"] == contract["result_id"]

    async def test_order_count_and_avg_metrics(self, session) -> None:
        company = await _seed_company(session)
        today = date(2026, 10, 7)
        at = datetime(2026, 10, 7, 10, 0, tzinfo=UTC)
        await _seed_quotation(session, company, amount=100.0, approved_at=at)
        await _seed_quotation(session, company, amount=200.0, approved_at=at)

        count = await ebms.emit_sales_result(session, period_start=today, period_end=today, metric_code="order_count")
        assert count["metric_value"] == 2.0
        assert count["unit"] == "count"

        avg = await ebms.emit_sales_result(
            session, period_start=today, period_end=today, metric_code="avg_order_amount"
        )
        assert avg["metric_value"] == 150.0

        # 两个不同指标 → 两条独立投递
        assert await _outbox_count(session, ebms.EVENT_RESULT) == 2

    async def test_empty_period_produces_zero_result(self, session) -> None:
        await _seed_company(session)
        out = await ebms.emit_sales_result(session, period_start=date(2020, 1, 1), period_end=date(2020, 1, 31))
        assert out["metric_value"] == 0.0
        assert out["order_count"] == 0
        assert out["created"] is True

    async def test_unknown_metric_rejected(self, session) -> None:
        from app.core.exceptions import ApiError

        with pytest.raises(ApiError):
            await ebms.emit_sales_result(
                session, period_start=date(2026, 10, 1), period_end=date(2026, 10, 7), metric_code="gross_margin"
            )


# ---------------------------------------------------------------- 幂等


class TestIdempotency:
    async def test_same_content_is_not_reenqueued(self, session) -> None:
        company = await _seed_company(session)
        today = date(2026, 10, 7)
        await _seed_quotation(session, company, amount=100.0, approved_at=datetime(2026, 10, 7, 10, 0, tzinfo=UTC))

        first = await ebms.emit_sales_result(session, period_start=today, period_end=today)
        second = await ebms.emit_sales_result(session, period_start=today, period_end=today)

        assert first["created"] is True
        assert second["created"] is False and second["skipped"] is True
        assert await _outbox_count(session, ebms.EVENT_RESULT) == 1
        assert len(await _ebms_logs(session)) == 1

    async def test_changed_metric_value_produces_new_delivery(self, session) -> None:
        company = await _seed_company(session)
        today = date(2026, 10, 7)
        await _seed_quotation(session, company, amount=100.0, approved_at=datetime(2026, 10, 7, 10, 0, tzinfo=UTC))
        first = await ebms.emit_sales_result(session, period_start=today, period_end=today)

        # 期内新增一笔成交 → 指标值变化 → 应产生新投递
        await _seed_quotation(session, company, amount=50.0, approved_at=datetime(2026, 10, 7, 11, 0, tzinfo=UTC))
        second = await ebms.emit_sales_result(session, period_start=today, period_end=today)

        assert first["created"] is True
        assert second["created"] is True
        assert await _outbox_count(session, ebms.EVENT_RESULT) == 2
        logs = await _ebms_logs(session)
        assert len(logs) == 2
        assert logs[0].idempotency_key != logs[1].idempotency_key
        assert first["metric_value"] != second["metric_value"]


# ---------------------------------------------------------------- 试点 B


class TestPilotBDeliveryOverdue:
    async def test_overdue_order_emits_exception_with_severity(self, session) -> None:
        # 16-06=B：无 promised_date 时回退 created_at + sla；业务时间 2026-08-08 12:00+08，
        # as_of 2026-10-07 12:00+08 → 相差 60 天，60-45=15 天 → high
        overdue = await _seed_sales_order(session, created_at=OVERDUE_AT)
        fresh = await _seed_sales_order(session, created_at=AS_OF)

        out = await ebms.emit_delivery_overdue(session, sla_days=45, as_of=AS_OF)

        assert out["total"] == 1
        assert out["created"] == 1
        emitted = out["emitted"][0]
        assert emitted["severity"] == "high"  # 逾期 15 天 → 14≤x<30
        assert emitted["days_overdue"] == 15

        log = (await _ebms_logs(session))[0]
        contract = log.request_payload
        assert contract["contract_version"] == "AEOS.Exception.V1"
        assert contract["source_system"] == "M05"
        assert contract["object_type"] == "SalesOrder"
        assert contract["reason_code"] == "DELIVERY_OVERDUE"
        assert contract["status"] == "OPEN"
        # 异常指向逾期订单，而非未到期的 fresh 订单
        assert contract["object_id"] == overdue.order_no
        assert contract["object_id"] != fresh.order_no
        assert contract["exception_id"] == f"EXC-M05-{overdue.order_no}"
        assert contract["evidence_ids"] == [str(overdue.id)]
        assert contract["sla_days"] == 45
        assert contract["days_overdue"] == 15
        assert contract["basis"] == "sla"

    async def test_promised_date_takes_priority_over_sla(self, session) -> None:
        # 16-06=B 主口径：有 promised_date 即按交期判定，即使 created_at 很新（未超 sla）。
        overdue = await _seed_sales_order(
            session, promised_date=AS_OF.date() - timedelta(days=5), created_at=AS_OF
        )
        out = await ebms.emit_delivery_overdue(session, sla_days=45, as_of=AS_OF)
        assert out["total"] == 1
        assert out["emitted"][0]["days_overdue"] == 5
        assert out["emitted"][0]["basis"] == "promised_date"
        assert out["emitted"][0]["severity"] == "low"

        log = (await _ebms_logs(session))[0]
        assert log.request_payload["object_id"] == overdue.order_no

    async def test_promised_date_not_yet_due_is_ignored(self, session) -> None:
        # promised_date 未到 as_of 当日（未来交期）→ 不判定逾期。
        await _seed_sales_order(session, promised_date=AS_OF.date() + timedelta(days=3))
        out = await ebms.emit_delivery_overdue(session, sla_days=7, as_of=AS_OF)
        assert out["total"] == 0

    async def test_severity_escalates_to_critical(self, session) -> None:
        await _seed_sales_order(session, created_at=OVERDUE_AT)
        out = await ebms.emit_delivery_overdue(session, sla_days=30, as_of=AS_OF)
        assert out["emitted"][0]["days_overdue"] == 30
        assert out["emitted"][0]["severity"] == "critical"

    async def test_repeated_emit_same_day_is_idempotent(self, session) -> None:
        await _seed_sales_order(session, created_at=OVERDUE_AT)
        first = await ebms.emit_delivery_overdue(session, sla_days=45, as_of=AS_OF)
        second = await ebms.emit_delivery_overdue(session, sla_days=45, as_of=AS_OF)
        assert first["created"] == 1
        assert second["created"] == 0 and second["skipped"] == 1
        assert await _outbox_count(session, ebms.EVENT_EXCEPTION) == 1

    async def test_no_overdue_when_all_within_sla(self, session) -> None:
        await _seed_sales_order(session, created_at=AS_OF - timedelta(days=3))
        out = await ebms.emit_delivery_overdue(session, sla_days=45, as_of=AS_OF)
        assert out["total"] == 0


# ---------------------------------------------------------------- 投递 / 重试 / 对账


class TestEntityEmission:
    async def test_inquiry_upsert_loads_items_before_serialization(self, session) -> None:
        """明细行独立 add 后序列化，必须显式加载关系（否则异步懒加载 MissingGreenlet）。"""
        inquiry = Inquiry(
            inquiry_no=f"{CODE_PREFIX}INQ-{uuid.uuid4().hex[:6]}",
            status="DRAFT",
            customer_name="PAND163 询价客户",
        )
        session.add(inquiry)
        await session.flush()
        session.add(InquiryItem(inquiry_id=inquiry.id, product_model="PAND163-M1", quantity=2))
        await session.flush()

        out = await ebms_sync.emit_upsert(session, "Inquiry", inquiry)

        assert out["created"] == 1
        row = (
            await session.execute(
                select(IntegrationOutbox).where(IntegrationOutbox.event_type == ebms.EVENT_ENTITY)
            )
        ).scalars().first()
        assert row.payload["event_type"] == "inquiry.upserted"
        assert row.payload["payload"]["items"][0]["external_model"] == "PAND163-M1"


class TestDelivery:
    async def test_entity_event_delivers_inner_event_type(self, session) -> None:
        """X-Event-Type 必须是契约体内事件类型（customer.upserted），而非 Outbox 包类型。"""
        company = await _seed_company(session)
        await ebms_sync.emit_upsert(session, "Customer", company)

        class _Recorder:
            mode = "http"

            def __init__(self) -> None:
                self.calls: list[dict] = []

            async def deliver(self, contract, *, event_type, contract_id, idempotency_key):
                self.calls.append({"contract": contract, "event_type": event_type})
                return DeliveryResult(
                    ok=True, mode="http", target="(fake)", status_code=200, response={"result": "ok"}
                )

        recorder = _Recorder()
        result = await ebms.deliver_pending(session, transport=recorder)

        assert result["delivered"] == 1
        assert recorder.calls[0]["event_type"] == "customer.upserted"
        assert recorder.calls[0]["contract"]["event_type"] == "customer.upserted"

    async def test_retry_entity_event_uses_inner_event_type(self, session) -> None:
        company = await _seed_company(session)
        await ebms_sync.emit_upsert(session, "Customer", company)
        await ebms.deliver_pending(session, transport=EbmsTransport(mode="http", ingest_url=""))
        log = (await _ebms_logs(session))[0]

        class _Recorder:
            mode = "http"

            def __init__(self) -> None:
                self.calls: list[str] = []

            async def deliver(self, contract, *, event_type, contract_id, idempotency_key):
                self.calls.append(event_type)
                return DeliveryResult(
                    ok=True, mode="http", target="(fake)", status_code=200, response={"result": "ok"}
                )

        recorder = _Recorder()
        out = await ebms.retry(session, log.id, transport=recorder)

        assert out["status"] == "SUCCESS"
        assert recorder.calls == ["customer.upserted"]

    async def test_deliver_to_spool_marks_log_and_outbox(self, session, tmp_path: Path) -> None:
        company = await _seed_company(session)
        today = date(2026, 10, 7)
        await _seed_quotation(session, company, amount=100.0, approved_at=datetime(2026, 10, 7, 10, 0, tzinfo=UTC))
        await ebms.emit_sales_result(session, period_start=today, period_end=today)

        result = await ebms.deliver_pending(session, transport=EbmsTransport(mode="spool", spool_dir=str(tmp_path)))

        assert result["picked"] == 1 and result["delivered"] == 1
        log = (await _ebms_logs(session))[0]
        assert log.status == "SUCCESS"
        assert log.response_payload["ok"] is True
        assert log.finished_at is not None
        spool_files = list((tmp_path / ebms.EVENT_RESULT).glob("*.json"))
        assert len(spool_files) == 1

        outbox = (
            await session.execute(select(IntegrationOutbox).where(IntegrationOutbox.event_type == ebms.EVENT_RESULT))
        ).scalar_one()
        assert outbox.status == "DONE" and outbox.processed_at is not None

    async def test_second_deliver_picks_nothing(self, session, tmp_path: Path) -> None:
        company = await _seed_company(session)
        today = date(2026, 10, 7)
        await _seed_quotation(session, company, approved_at=datetime(2026, 10, 7, 10, 0, tzinfo=UTC))
        await ebms.emit_sales_result(session, period_start=today, period_end=today)
        transport = EbmsTransport(mode="spool", spool_dir=str(tmp_path))

        await ebms.deliver_pending(session, transport=transport)
        second = await ebms.deliver_pending(session, transport=transport)

        assert second["picked"] == 0
        assert (await _ebms_logs(session))[0].status == "SUCCESS"
        assert len(list((tmp_path / ebms.EVENT_RESULT).glob("*.json"))) == 1
        assert len(await _ebms_logs(session)) == 1

    async def test_failure_is_logged_with_backoff(self, session) -> None:
        company = await _seed_company(session)
        today = date(2026, 10, 7)
        await _seed_quotation(session, company, approved_at=datetime(2026, 10, 7, 10, 0, tzinfo=UTC))
        await ebms.emit_sales_result(session, period_start=today, period_end=today)

        result = await ebms.deliver_pending(session, transport=EbmsTransport(mode="http", ingest_url=""))

        assert result["failed"] == 1
        log = (await _ebms_logs(session))[0]
        assert log.status == "FAILED"
        assert log.retry_count == 1
        assert log.next_retry_at is not None
        assert "EBMS_INGEST_URL 未配置" in (log.error_message or "")

        outbox = (
            await session.execute(select(IntegrationOutbox).where(IntegrationOutbox.event_type == ebms.EVENT_RESULT))
        ).scalar_one()
        assert outbox.status == "PENDING" and outbox.retry_count == 1

    async def test_retry_redelivers_for_real(self, session, tmp_path: Path) -> None:
        company = await _seed_company(session)
        today = date(2026, 10, 7)
        await _seed_quotation(session, company, approved_at=datetime(2026, 10, 7, 10, 0, tzinfo=UTC))
        await ebms.emit_sales_result(session, period_start=today, period_end=today)
        await ebms.deliver_pending(session, transport=EbmsTransport(mode="http", ingest_url=""))
        log = (await _ebms_logs(session))[0]
        assert log.status == "FAILED"

        out = await ebms.retry(session, log.id, transport=EbmsTransport(mode="spool", spool_dir=str(tmp_path)))

        assert out["status"] == "SUCCESS"
        assert log.retry_count == 2
        assert log.error_message is None
        assert len(list((tmp_path / ebms.EVENT_RESULT).glob("*.json"))) == 1
        outbox = (
            await session.execute(select(IntegrationOutbox).where(IntegrationOutbox.event_type == ebms.EVENT_RESULT))
        ).scalar_one()
        assert outbox.status == "DONE"

    async def test_retry_successful_log_is_noop(self, session, tmp_path: Path) -> None:
        company = await _seed_company(session)
        today = date(2026, 10, 7)
        await _seed_quotation(session, company, approved_at=datetime(2026, 10, 7, 10, 0, tzinfo=UTC))
        await ebms.emit_sales_result(session, period_start=today, period_end=today)
        await ebms.deliver_pending(session, transport=EbmsTransport(mode="spool", spool_dir=str(tmp_path)))
        log = (await _ebms_logs(session))[0]

        out = await ebms.retry(session, log.id, transport=EbmsTransport(mode="spool", spool_dir=str(tmp_path)))
        assert "无需重试" in out["message"]

    async def test_exceeding_max_retry_goes_dead_letter(self, session) -> None:
        company = await _seed_company(session)
        today = date(2026, 10, 7)
        await _seed_quotation(session, company, approved_at=datetime(2026, 10, 7, 10, 0, tzinfo=UTC))
        await ebms.emit_sales_result(session, period_start=today, period_end=today)
        log = (await _ebms_logs(session))[0]
        log.max_retry = 1
        await session.flush()

        result = await ebms.deliver_pending(session, transport=EbmsTransport(mode="http", ingest_url=""))

        assert result["dead_letter"] == 1
        assert log.status == "DEAD_LETTER"
        assert log.next_retry_at is None

    async def test_retry_on_dead_letter_log_reports_dead_letter(self, session) -> None:
        company = await _seed_company(session)
        today = date(2026, 10, 7)
        await _seed_quotation(session, company, approved_at=datetime(2026, 10, 7, 10, 0, tzinfo=UTC))
        await ebms.emit_sales_result(session, period_start=today, period_end=today)
        log = (await _ebms_logs(session))[0]
        log.max_retry = 1
        await session.flush()
        await ebms.deliver_pending(session, transport=EbmsTransport(mode="http", ingest_url=""))

        out = await ebms.retry(session, log.id, transport=EbmsTransport(mode="dry_run"))
        assert out["status"] == "DEAD_LETTER"


class TestReconcile:
    async def test_consistent_after_delivery(self, session, tmp_path: Path) -> None:
        company = await _seed_company(session)
        today = date(2026, 10, 7)
        await _seed_quotation(session, company, amount=100.0, approved_at=datetime(2026, 10, 7, 10, 0, tzinfo=UTC))
        await _seed_sales_order(session, created_at=OVERDUE_AT)
        await ebms.emit_sales_result(session, period_start=today, period_end=today)
        await ebms.emit_delivery_overdue(session, sla_days=45, as_of=AS_OF)
        await ebms.deliver_pending(session, transport=EbmsTransport(mode="spool", spool_dir=str(tmp_path)))

        report = await ebms.reconcile(session)

        assert report["result"] == {"produced": 1, "delivered": 1, "pending": 0, "failed": 0}
        assert report["exception"] == {"produced": 1, "delivered": 1, "pending": 0, "failed": 0}
        assert report["consistent"] is True

    async def test_inconsistent_when_delivery_failed(self, session) -> None:
        company = await _seed_company(session)
        today = date(2026, 10, 7)
        await _seed_quotation(session, company, approved_at=datetime(2026, 10, 7, 10, 0, tzinfo=UTC))
        await ebms.emit_sales_result(session, period_start=today, period_end=today)
        await ebms.deliver_pending(session, transport=EbmsTransport(mode="http", ingest_url=""))

        report = await ebms.reconcile(session)

        assert report["result"]["delivered"] == 0
        assert report["result"]["pending"] == 1
        assert report["consistent"] is False
