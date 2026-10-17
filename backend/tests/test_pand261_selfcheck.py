"""PAND-261 返工4 七项自检断言（实际 vs 期望）。

取证口径（对齐 PAND-255 复测报告）：
- F5 指纹：真实 ``event_fingerprint`` + PAND-253 勘误 fixture + 逐字断言。
- M4.4 / M6.6 / M1.5 / M1.6 / M1.7 / M6.5：PostgreSQL 隔离测试库 + 真实
  model / endpoint 函数 + 断言（``CRM_TEST_DATABASE_URL`` 未设置时跳过）。

运行：
    CRM_TEST_DATABASE_URL=postgresql+asyncpg://crm:crm123456@localhost:55433/crm \\
    POSTGRES_PORT=55433 \\
    python -m pytest tests/test_pand261_selfcheck.py -v
"""

from __future__ import annotations

import importlib.util
import io
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# ---- 真实 endpoint 函数（绕过 FastAPI Depends，直接以 db + User 调用）----
from app.api.v1.endpoints import companies as companies_api
from app.api.v1.endpoints import feedback as feedback_api
from app.api.v1.endpoints import orders as orders_api
from app.contracts.aeos import event_fingerprint, event_idempotency_key
from app.core.exceptions import ApiError, ForbiddenError
from app.models.business import BusinessCode, Company
from app.models.integration import IntegrationLog, IntegrationOutbox
from app.models.sales import Feedback, FeedbackFollowup, SalesOrder, SyncConflict
from app.models.user import User
from app.schemas.business import CompanyBatchUpdateIn
from app.schemas.sales import SalesOrderStatusIn, SalesOrderUpdate
from app.services.ebms_ingest import ingest_event

TEST_DB_URL = os.environ.get("CRM_TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not TEST_DB_URL, reason="需设置 CRM_TEST_DATABASE_URL 指向已迁移的测试库")

PREFIX = "PAND261-"


# ---------------------------------------------------------------- F5 fixture 复用
def _load_sales_center_fixtures() -> tuple[dict, dict]:
    """复用 test_sales_center.py 中与 PAND-253 评论 1 逐字一致的勘误 fixture。"""
    spec = importlib.util.spec_from_file_location(
        "tsc_fixtures", Path(__file__).with_name("test_sales_center.py")
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    cls = module.TestFingerprintFixtures
    return cls.ORDER_FIXTURE, cls.INQUIRY_FIXTURE


ORDER_FIXTURE, INQUIRY_FIXTURE = _load_sales_center_fixtures()


# ---------------------------------------------------------------- F5
class TestF5Fingerprint:
    def test_order_fingerprint_matches_errata(self) -> None:
        actual = event_fingerprint(ORDER_FIXTURE)
        expected = "e44519e77910896a"
        assert actual == expected, f"Order 指纹 实际={actual} 期望={expected}"

    def test_inquiry_fingerprint_matches_errata(self) -> None:
        actual = event_fingerprint(INQUIRY_FIXTURE)
        expected = "6cf954c39baab26c"
        assert actual == expected, f"Inquiry 指纹 实际={actual} 期望={expected}"

    def test_fingerprint_excludes_four_envelope_fields(self) -> None:
        variant = {
            **ORDER_FIXTURE,
            "event_id": "EVT-DIFFERENT",
            "trace_id": "TRACE-DIFFERENT",
            "occurred_at": "2099-01-01T00:00:00+08:00",
            "idempotency_key": "M05:order.upserted:SO20261017001#1:e44519e77910896a",
        }
        assert event_fingerprint(variant) == event_fingerprint(ORDER_FIXTURE)

    def test_idempotency_key_two_directions_differ_only_by_target(self) -> None:
        k_m05 = event_idempotency_key("M05", ORDER_FIXTURE)
        k_ebms = event_idempotency_key("EBMS", ORDER_FIXTURE)
        assert k_m05 == "M05:order.upserted:SO20261017001#1:e44519e77910896a"
        assert k_ebms == "EBMS:order.upserted:SO20261017001#1:e44519e77910896a"


# ---------------------------------------------------------------- DB 会话
async def _clean(session) -> None:
    """只清理本测试写入的 PAND261- 前缀数据（含 Outbox/Log，避免污染共享测试库）。"""
    cids = (
        (await session.execute(select(Company.id).where(Company.name.like(f"{PREFIX}%"))))
        .scalars()
        .all()
    )
    oids = (
        (await session.execute(select(SalesOrder.id).where(SalesOrder.order_no.like(f"{PREFIX}%"))))
        .scalars()
        .all()
    )
    fids = (
        (await session.execute(select(Feedback.id).where(Feedback.feedback_no.like(f"{PREFIX}%"))))
        .scalars()
        .all()
    )
    entity_ids = [*cids, *oids, *fids]
    if entity_ids:
        await session.execute(delete(IntegrationOutbox).where(IntegrationOutbox.biz_id.in_(entity_ids)))
    # 入站/出站幂等键均含 PAND261- 自然键段，统一清理残留日志/队列
    await session.execute(delete(IntegrationLog).where(IntegrationLog.idempotency_key.like(f"%{PREFIX}%")))
    await session.execute(delete(IntegrationOutbox).where(IntegrationOutbox.idempotency_key.like(f"%{PREFIX}%")))
    if cids:
        await session.execute(delete(BusinessCode).where(BusinessCode.company_id.in_(cids)))
        await session.execute(delete(Company).where(Company.id.in_(cids)))
    await session.execute(delete(SalesOrder).where(SalesOrder.order_no.like(f"{PREFIX}%")))
    if fids:
        await session.execute(delete(FeedbackFollowup).where(FeedbackFollowup.feedback_id.in_(fids)))
        await session.execute(delete(Feedback).where(Feedback.id.in_(fids)))
    await session.execute(delete(SyncConflict).where(SyncConflict.object_id.like(f"{PREFIX}%")))
    await session.execute(delete(User).where(User.username.like(f"{PREFIX}%")))
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


def _make_user(session, tag: str) -> User:
    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=f"{PREFIX}{tag}-{suffix}",
        password_hash="x",
        name=f"{tag}-{suffix}",
        code=f"U{suffix[:6].upper()}",
        is_superuser=False,
    )
    # 预置空角色集合，避免 get_user_scope 对 selectin 关系触发异步惰性加载
    user.roles = []
    session.add(user)
    return user


async def _mk_company(session, *, name: str, owner: User, **kw) -> Company:
    c = Company(
        code=f"{PREFIX}{uuid.uuid4().hex[:8]}",
        name=name,
        owner_id=owner.id,
        department_id=None,
        **kw,
    )
    session.add(c)
    await session.flush()
    return c


# ---------------------------------------------------------------- AC-M4.4
@needs_db
class TestM44OrderLock:
    def test_update_schema_exposes_user_status_locked(self) -> None:
        assert "user_status_locked" in SalesOrderUpdate.model_fields

    async def test_transition_order_sets_lock(self, session) -> None:
        user = _make_user(session, "order-user")
        await session.flush()
        order = SalesOrder(
            order_no=f"{PREFIX}{uuid.uuid4().hex[:8]}",
            line_no="1",
            customer_name="自检订单",
            status="open",
            owner_id=user.id,
        )
        session.add(order)
        await session.flush()

        await orders_api.transition_order(
            order_id=order.id,
            payload=SalesOrderStatusIn(status="confirmed"),
            db=session,
            current=user,
        )
        await session.commit()

        row = (
            await session.execute(select(SalesOrder).where(SalesOrder.id == order.id))
        ).scalar_one()
        assert row.status == "confirmed"
        assert row.user_status_locked is True, f"流转后 user_status_locked 实际={row.user_status_locked} 期望=True"

    async def test_inbound_skip_status_when_locked(self, session) -> None:
        user = _make_user(session, "lock-ingest")
        await session.flush()
        order_no = f"{PREFIX}{uuid.uuid4().hex[:8]}"
        order = SalesOrder(
            order_no=order_no,
            line_no="1",
            customer_name="锁定订单",
            status="open",
            user_status_locked=True,
            owner_id=user.id,
        )
        session.add(order)
        await session.flush()

        event = {
            "contract_version": "AEOS.Event.V1",
            "event_id": f"EVT-{order_no}",
            "event_type": "order.upserted",
            "source_system": "M05",
            "object_type": "order",
            "object_id": f"{order_no}#1",
            "occurred_at": "2026-10-17T10:00:00+08:00",
            "trace_id": f"TRACE-{order_no}",
            "payload": {
                "order_no": order_no,
                "line_no": "1",
                "status": "completed",
                "external_id": "EBMS-EXT-LOCKED",
                "customer_name": "入站改名",
            },
        }
        await ingest_event(session, event)
        await session.flush()

        row = (
            await session.execute(select(SalesOrder).where(SalesOrder.order_no == order_no))
        ).scalar_one()
        assert row.status == "open", f"LOCKED 应跳过 status，实际={row.status} 期望=open"
        assert row.external_id == "EBMS-EXT-LOCKED", "EBMS 拥有字段 external_id 应照常应用"
        assert row.customer_name == "锁定订单", "CRM 拥有字段 customer_name 不应被入站改写"

        conflict = (
            await session.execute(
                select(SyncConflict).where(
                    SyncConflict.object_id == f"{order_no}#1",
                    SyncConflict.field == "status",
                    SyncConflict.resolution == "LOCKED",
                )
            )
        ).scalar_one_or_none()
        assert conflict is not None, "应留痕 resolution=LOCKED 的 status 冲突记录"


# ---------------------------------------------------------------- AC-M6.6
@needs_db
class TestM66FeedbackCascade:
    async def test_delete_feedback_soft_deletes_followups(self, session) -> None:
        user = _make_user(session, "fb-user")
        await session.flush()
        fb = Feedback(feedback_no=f"{PREFIX}{uuid.uuid4().hex[:8]}", title="自检反馈", submitter_id=user.id)
        session.add(fb)
        await session.flush()
        for action in ("submit", "comment", "status"):
            session.add(FeedbackFollowup(feedback_id=fb.id, action=action, content=action))
        await session.flush()

        await feedback_api.delete_feedback(feedback_id=fb.id, db=session, _=user)
        await session.commit()

        orphan = (
            await session.execute(
                select(func.count())
                .select_from(FeedbackFollowup)
                .where(
                    FeedbackFollowup.feedback_id == fb.id,
                    FeedbackFollowup.deleted_at.is_(None),
                )
            )
        ).scalar_one()
        assert orphan == 0, f"删除后不得残留 deleted_at=NULL 的孤儿跟进，实际={orphan} 期望=0"
        followups = (
            await session.execute(select(FeedbackFollowup).where(FeedbackFollowup.feedback_id == fb.id))
        ).scalars().all()
        assert len(followups) == 3
        assert all(f.deleted_at is not None for f in followups), "全部跟进应被软删（deleted_at 非空）"


# ---------------------------------------------------------------- AC-M1.5
@needs_db
class TestM15DetailScope:
    async def test_get_company_forbidden_for_other_owner(self, session) -> None:
        owner = _make_user(session, "owner")
        viewer = _make_user(session, "viewer")
        await session.flush()
        company = await _mk_company(session, name=f"{PREFIX}越权客户", owner=owner)

        with pytest.raises(ForbiddenError) as exc:
            await companies_api.get_company(company_id=company.id, db=session, current=viewer)
        assert exc.value.http_status == 403, f"越权详情 实际=http_status={exc.value.http_status} 期望=403"

    async def test_get_company_allows_owner(self, session) -> None:
        owner = _make_user(session, "owner-ok")
        await session.flush()
        company = await _mk_company(session, name=f"{PREFIX}本人客户", owner=owner)

        result = await companies_api.get_company(company_id=company.id, db=session, current=owner)
        assert result["data"]["id"] == str(company.id)


# ---------------------------------------------------------------- AC-M1.6
@needs_db
class TestM16Batch:
    def test_schema_requires_at_least_one_field(self) -> None:
        with pytest.raises(ValidationError):
            CompanyBatchUpdateIn(ids=[uuid.uuid4()], fields={})  # 至少选一字段

    def test_schema_requires_at_least_one_id(self) -> None:
        with pytest.raises(ValidationError):
            CompanyBatchUpdateIn(ids=[], fields={"customer_level": "B级（普通大客户）"})

    async def test_batch_update_only_level_changes(self, session) -> None:
        user = _make_user(session, "batch-user")
        await session.flush()
        company = await _mk_company(
            session,
            name=f"{PREFIX}批量客户",
            owner=user,
            country="美国",
            sales_mode="外销",
            customer_level="A级（核心大客户）",
        )

        await companies_api.batch_update_companies(
            payload=CompanyBatchUpdateIn(ids=[company.id], fields={"customer_level": "B级（普通大客户）"}),
            db=session,
            current=user,
        )
        await session.commit()

        row = (
            await session.execute(select(Company).where(Company.id == company.id))
        ).scalar_one()
        assert row.customer_level == "B级（普通大客户）", "仅改等级：customer_level 应更新"
        assert row.country == "美国", "其余字段不变：country 不应变化"
        assert row.sales_mode == "外销", "其余字段不变：sales_mode 不应变化"
        assert row.name == f"{PREFIX}批量客户", "其余字段不变：name 不应变化"

    async def test_batch_update_rejects_non_whitelist_field(self, session) -> None:
        user = _make_user(session, "batch-bad")
        await session.flush()
        company = await _mk_company(session, name=f"{PREFIX}白名单客户", owner=user)

        with pytest.raises(ApiError) as exc:
            await companies_api.batch_update_companies(
                payload=CompanyBatchUpdateIn(ids=[company.id], fields={"name": "改名"}),
                db=session,
                current=user,
            )
        assert exc.value.http_status == 400, "name 不在白名单，应 400 拒绝"


# ---------------------------------------------------------------- AC-M1.7
@needs_db
class TestM17ImportDedup:
    def _xlsx_bytes(self) -> bytes:
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = "客户"
        ws.append(["客户全称", "客户等级", "国家/地区", "备注说明"])
        ws.append([f"{PREFIX}导入客户A", "A级（核心大客户）", "中国", "第一次"])
        ws.append([f"{PREFIX}导入客户B", "B级（普通大客户）", "美国", ""])
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    def _upload(self, content: bytes):
        from fastapi import UploadFile

        return UploadFile(filename="customers.xlsx", file=io.BytesIO(content))

    async def test_reimport_same_file_no_duplicates(self, session) -> None:
        user = _make_user(session, "import-user")
        await session.flush()
        content = self._xlsx_bytes()

        first = await companies_api.import_companies_xlsx(db=session, file=self._upload(content), current=user)
        await session.commit()
        second = await companies_api.import_companies_xlsx(db=session, file=self._upload(content), current=user)
        await session.commit()

        assert first["data"]["imported"] == 2, f"首次导入 imported 实际={first['data']['imported']} 期望=2"
        assert second["data"]["imported"] == 0, f"二次导入 imported 实际={second['data']['imported']} 期望=0"
        assert second["data"]["skipped"] == 2, f"二次导入 skipped 实际={second['data']['skipped']} 期望=2"

        count = (
            await session.execute(
                select(func.count()).select_from(Company).where(Company.name.like(f"{PREFIX}导入客户%"))
            )
        ).scalar_one()
        assert count == 2, f"同名客户应仅 2 条，实际={count} 期望=2"


# ---------------------------------------------------------------- AC-M6.5
@needs_db
class TestM65AvgHandleHours:
    async def test_avg_handle_hours_and_zero_division(self, session) -> None:
        user = _make_user(session, "stats-user")
        await session.flush()
        created_a = datetime(2026, 10, 1, 0, 0, tzinfo=UTC)
        resolved_a = created_a + timedelta(hours=10)
        created_b = datetime(2026, 10, 2, 0, 0, tzinfo=UTC)
        resolved_b = created_b + timedelta(hours=14)

        fb_a = Feedback(feedback_no=f"{PREFIX}{uuid.uuid4().hex[:8]}", title="A", status="resolved")
        fb_a.created_at = created_a
        fb_a.resolved_at = resolved_a
        fb_b = Feedback(feedback_no=f"{PREFIX}{uuid.uuid4().hex[:8]}", title="B", status="closed")
        fb_b.created_at = created_b
        fb_b.resolved_at = resolved_b
        session.add_all([fb_a, fb_b])
        await session.flush()

        result = await feedback_api.feedback_stats(db=session, _=user)
        data = result["data"]
        assert "avg_handle_hours" in data, "feedback_stats 应包含 avg_handle_hours 字段"
        # (10 + 14) / 2 = 12.0 小时
        assert data["avg_handle_hours"] == 12.0, (
            f"avg_handle_hours 实际={data['avg_handle_hours']} 期望=12.0"
        )

    async def test_avg_handle_hours_zero_when_no_resolved(self, session) -> None:
        user = _make_user(session, "stats-zero")
        await session.flush()
        fb = Feedback(feedback_no=f"{PREFIX}{uuid.uuid4().hex[:8]}", title="未处理", status="open")
        session.add(fb)
        await session.flush()

        result = await feedback_api.feedback_stats(db=session, _=user)
        assert result["data"]["avg_handle_hours"] == 0.0, "无已处理样本时 avg_handle_hours 应为 0（除零保护）"
