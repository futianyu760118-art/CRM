"""销售中心 6 模块与 EBMS 双向同步——纯逻辑单测（PAND-249）。

覆盖：AEOS.Event.V1 契约校验/构造/指纹/幂等键、订单/样品/反馈状态机、
编号规则、出站序列化与字段 Owner 边界、入站幂等键与字段规整。
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.contracts.aeos import (
    EVENT_CONTRACT_VERSION,
    EVENT_TYPES,
    AeosEventContract,
    ContractValidationError,
    build_event_contract,
    canonical_json,
    delete_event_for,
    event_fingerprint,
    event_idempotency_key,
    to_wire,
    upsert_event_for,
    validate_contract,
)
from app.domain.state_machine import (
    FEEDBACK_STATUSES,
    SAMPLE_STATUSES,
    allowed_order_transitions,
)
from app.models.business import Company
from app.models.integration import IntegrationLog
from app.services.ebms_ingest import (
    _coerce,
    _differs,
    _external_id,
    _resolve_key,
    ingest_event,
)
from app.services.ebms_sync import SERIALIZERS, _ser, natural_id
from app.services.number_sequence import format_number

# ------------------------------------------------------------------ AEOS.Event.V1


def _event(**overrides: object) -> dict:
    base: dict = {
        "contract_version": EVENT_CONTRACT_VERSION,
        "event_id": "EVT-TEST-001",
        "event_type": "customer.upserted",
        "source_system": "M05",
        "object_type": "Customer",
        "object_id": "HJ003-176-576",
        "operation": "UPSERT",
        "occurred_at": datetime(2026, 10, 16, 8, 0, 0, tzinfo=UTC),
        "trace_id": "TRACE-TEST",
        "payload": {"name": "测试客户", "customer_code": "HJ003-176-576"},
    }
    base.update(overrides)
    return base


class TestEventContract:
    def test_13_event_types_exist(self) -> None:
        # 6 实体 × {upserted, deleted} + dictionary.upserted = 13
        assert len(EVENT_TYPES) == 13
        assert "customer.upserted" in EVENT_TYPES
        assert "customer.deleted" in EVENT_TYPES
        assert "dictionary.upserted" in EVENT_TYPES
        assert "dictionary.deleted" not in EVENT_TYPES

    def test_upsert_and_delete_event_for(self) -> None:
        assert upsert_event_for("Order") == "order.upserted"
        assert delete_event_for("Order") == "order.deleted"
        with pytest.raises(ValueError):
            delete_event_for("Dictionary")

    def test_event_contract_validates_and_roundtrips(self) -> None:
        contract = validate_contract(_event())
        assert isinstance(contract, AeosEventContract)
        assert contract.contract_id == "EVT-TEST-001"
        assert contract.payload["name"] == "测试客户"

    def test_build_event_contract_emits_valid_contract(self) -> None:
        contract = build_event_contract(
            event_id="EVT-2",
            event_type="sample.upserted",
            source_system="M05",
            object_type="Sample",
            object_id="SMP-0001",
            operation="UPSERT",
            payload={"sample_no": "SMP-0001"},
            trace_id="T2",
            occurred_at=datetime(2026, 10, 16, 8, 0, 0, tzinfo=UTC),
        )
        assert contract.contract_version == EVENT_CONTRACT_VERSION
        assert contract.event_type == "sample.upserted"
        assert contract.operation == "UPSERT"

    def test_unknown_event_type_rejected(self) -> None:
        with pytest.raises(ContractValidationError):
            validate_contract(_event(event_type="customer.renamed"))

    def test_unknown_object_type_rejected(self) -> None:
        with pytest.raises(ContractValidationError):
            validate_contract(_event(object_type="invoice"))


class TestFingerprintAndIdempotency:
    def test_fingerprint_ignores_occurred_at(self) -> None:
        a = _event(occurred_at=datetime(2026, 10, 16, 8, 0, 0, tzinfo=UTC))
        b = _event(occurred_at=datetime(2026, 10, 16, 9, 30, 0, tzinfo=UTC))
        assert event_fingerprint(a) == event_fingerprint(b)

    def test_fingerprint_stable_under_key_reorder(self) -> None:
        a = _event(payload={"code": "X", "name": "Y"})
        b = _event(payload={"name": "Y", "code": "X"})
        assert event_fingerprint(a) == event_fingerprint(b)

    def test_fingerprint_changes_when_payload_changes(self) -> None:
        assert event_fingerprint(_event(payload={"code": "A"})) != event_fingerprint(
            _event(payload={"code": "B"})
        )

    def test_canonical_json_sorted_and_no_spaces(self) -> None:
        # 标量以 JSON 原生字面量参与（int → 1、bool → true、None → null），键排序、无空格
        wire = canonical_json({"b": 1, "a": {"z": 1, "y": 2}})
        assert wire == '{"a":{"y":2,"z":1},"b":1}'
        assert " " not in wire

    def test_idempotency_key_format(self) -> None:
        key = event_idempotency_key("M05", _event())
        prefix, event_type, object_id, fp = key.split(":")
        assert prefix == "M05"
        assert event_type == "customer.upserted"
        assert object_id == "HJ003-176-576"
        assert len(fp) == 16


class TestFingerprintFixtures:
    """PAND-253 评论 1 勘误值（整包口径）：CRM 与 EBMS 逐字一致，仅 target 段不同。"""

    ORDER_FIXTURE: dict = {
        "contract_version": "AEOS.Event.V1",
        "event_id": "EVT-M05-order-SO20261017001#1-a1b2c3d4",
        "event_type": "order.upserted",
        "source_system": "M05",
        "object_type": "Order",
        "object_id": "SO20261017001#1",
        "operation": "UPSERT",
        "occurred_at": "2026-10-17T09:30:00+08:00",
        "trace_id": "TRACE-EVT-M05-order-SO20261017001#1-a1b2c3d4",
        "payload": {
            "order_no": "SO20261017001",
            "line_no": "1",
            "customer_name": "宁波恒见光电",
            "customer_code": "KH0001",
            "product_code": "P-100",
            "product_name": "LED 投光灯",
            "project_no": "PRJ-2026-008",
            "quantity": "100.00",
            "completed_qty": "0.00",
            "order_amount": "15600.00",
            "status": "confirmed",
            "risk_level": "blue",
            "promised_date": "2026-11-01",
            "plan_date": "2026-10-25",
            "online_date": "2026-10-28",
            "user_status_locked": False,
            "user_status_modified_at": None,
            "user_status_modified_by": None,
            "sales_id": 7,
            "department_id": 2,
            "create_by": 7,
            "created_at": "2026-10-17T09:00:00+08:00",
            "updated_at": "2026-10-17T09:30:00+08:00",
        },
    }

    INQUIRY_FIXTURE: dict = {
        "contract_version": "AEOS.Event.V1",
        "event_id": "EVT-M05-inquiry-JFX20261017001-9f3e2d1c",
        "event_type": "inquiry.upserted",
        "source_system": "M05",
        "object_type": "Inquiry",
        "object_id": "JFX20261017001",
        "operation": "UPSERT",
        "occurred_at": "2026-10-17T08:15:00+08:00",
        "trace_id": "TRACE-EVT-M05-inquiry-JFX20261017001-9f3e2d1c",
        "payload": {
            "serial_number": "JFX20261017001",
            "customer_name": "宁波恒见光电",
            "customer_code": "KH0001",
            "country_region": "中国",
            "sales_person": "张三",
            "contact_person": "李四",
            "contact_phone": "13800000000",
            "contact_email": "li@example.com",
            "inquiry_time": "2026-10-17T08:00:00+08:00",
            "delivery_date": "2026-11-30",
            "customer_source": "展会",
            "quote_validity": "30 天",
            "status": "pending_quote",
            "lost_reason": None,
            "items": [
                {
                    "external_model": "AC-100W",
                    "internal_model": "内部型号A",
                    "product_name": "LED 投光灯",
                    "product_category": "投光灯",
                    "power": "100W",
                    "configuration": "标配",
                    "quantity": "500.00",
                    "target_price": "85.50",
                    "certificate_compliant": "是",
                    "certificate_level": "国标",
                    "input_voltage": "AC220V",
                    "battery": None,
                    "color_temp": "6000K",
                    "luminous_flux": "12000",
                    "light_source": "LED",
                    "main_body": "压铸铝",
                    "lampshade": "钢化玻璃",
                    "reflector": None,
                    "cable": "1m",
                    "switch_type": None,
                    "usb": None,
                    "waterproof": "IP65",
                    "sensor": None,
                    "quote_time_needed": "15 天",
                    "custom_requirements": "客户要求防水",
                    "image": None,
                },
                {
                    "external_model": "AC-200W",
                    "internal_model": "内部型号B",
                    "product_name": "LED 投光灯",
                    "product_category": "投光灯",
                    "power": "200W",
                    "configuration": "高配",
                    "quantity": "200.00",
                    "target_price": "150.00",
                    "certificate_compliant": "否",
                    "certificate_level": "无证书",
                    "input_voltage": "AC220V",
                    "battery": None,
                    "color_temp": "6500K",
                    "luminous_flux": "24000",
                    "light_source": "LED",
                    "main_body": "压铸铝",
                    "lampshade": "钢化玻璃",
                    "reflector": None,
                    "cable": "1m",
                    "switch_type": None,
                    "usb": None,
                    "waterproof": "IP66",
                    "sensor": None,
                    "quote_time_needed": "20 天",
                    "custom_requirements": None,
                    "image": None,
                },
            ],
            "created_at": "2026-10-17T08:00:00+08:00",
            "updated_at": "2026-10-17T08:15:00+08:00",
        },
    }

    def test_order_fingerprint_matches_errata(self) -> None:
        assert event_fingerprint(self.ORDER_FIXTURE) == "e44519e77910896a"
        assert (
            event_idempotency_key("M05", self.ORDER_FIXTURE)
            == "M05:order.upserted:SO20261017001#1:e44519e77910896a"
        )
        assert (
            event_idempotency_key("EBMS", self.ORDER_FIXTURE)
            == "EBMS:order.upserted:SO20261017001#1:e44519e77910896a"
        )

    def test_inquiry_fingerprint_matches_errata(self) -> None:
        assert event_fingerprint(self.INQUIRY_FIXTURE) == "6cf954c39baab26c"
        assert (
            event_idempotency_key("M05", self.INQUIRY_FIXTURE)
            == "M05:inquiry.upserted:JFX20261017001:6cf954c39baab26c"
        )
        assert (
            event_idempotency_key("EBMS", self.INQUIRY_FIXTURE)
            == "EBMS:inquiry.upserted:JFX20261017001:6cf954c39baab26c"
        )

    def test_fingerprint_ignores_envelope_derived_fields(self) -> None:
        # 仅改动 occurred_at / event_id / trace_id / idempotency_key 不影响指纹
        base = self.ORDER_FIXTURE
        variant = {
            **base,
            "event_id": "EVT-DIFFERENT",
            "trace_id": "TRACE-DIFFERENT",
            "occurred_at": "2099-01-01T00:00:00+08:00",
            "idempotency_key": "M05:order.upserted:SO20261017001#1:e44519e77910896a",
        }
        assert event_fingerprint(variant) == event_fingerprint(base)


# ------------------------------------------------------------------ 状态机


class TestOrderStateMachine:
    def test_order_forward_progression(self) -> None:
        assert allowed_order_transitions("open") == ["confirmed", "closed", "cancelled"]
        assert allowed_order_transitions("shipped") == ["completed", "closed", "cancelled"]

    def test_terminal_states_have_no_transition(self) -> None:
        assert allowed_order_transitions("completed") == []
        assert allowed_order_transitions("cancelled") == []
        assert allowed_order_transitions("closed") == []

    def test_linear_sample_and_feedback_statuses(self) -> None:
        assert SAMPLE_STATUSES == ["pending", "confirmed", "producing", "sent", "customer_confirmed", "completed"]
        assert FEEDBACK_STATUSES == ["open", "processing", "resolved", "closed"]


# ------------------------------------------------------------------ 编号规则


class TestNumberFormats:
    def test_inquiry_format_matches_ac_m2_2(self) -> None:
        no = format_number("inquiry", datetime(2026, 9, 16, tzinfo=UTC), 1)
        assert re.fullmatch(r"JFX\d{8}\d{3}", no), no
        assert no == "JFX20260916001"

    def test_sample_format_global_seq(self) -> None:
        assert format_number("sample", datetime(2026, 10, 16, tzinfo=UTC), 7) == "SMP-0007"

    def test_feedback_format_daily_seq(self) -> None:
        no = format_number("feedback", datetime(2026, 10, 16, tzinfo=UTC), 12)
        assert no == "FB20261016012"


# ------------------------------------------------------------------ 同步纯逻辑


class TestSyncPrimitives:
    def test_ser_normalizes_decimal_datetime_uuid(self) -> None:
        assert _ser(Decimal("12.3400")) == 12.34
        assert _ser(datetime(2026, 10, 16, 8, 0, 0, tzinfo=UTC)) == "2026-10-16T08:00:00+00:00"
        assert _ser(date(2026, 10, 16)) == "2026-10-16"
        uid = uuid.uuid4()
        assert _ser(uid) == str(uid)
        assert _ser(None) is None

    def test_coerce_uuid_columns(self) -> None:
        uid = uuid.uuid4()
        assert _coerce("company_id", str(uid)) == uid
        assert _coerce("company_id", uid) == uid
        assert _coerce("company_id", "not-a-uuid") is None
        assert _coerce("screenshots", ["a", "b"]) == ["a", "b"]

    def test_differs_uses_ser_semantics(self) -> None:
        assert _differs(Decimal("1.5"), 1.5) is False
        assert _differs(Decimal("1.5"), 1.6) is True
        assert _differs(None, None) is False

    def test_natural_id_per_object_type(self) -> None:
        customer = SimpleNamespace(name="宁波恒见光电")
        inquiry = SimpleNamespace(inquiry_no="JFX20261016001")
        quote = SimpleNamespace(external_model="M-1", certificate_level="CE")
        order = SimpleNamespace(order_no="SO-1", line_no="")
        sample = SimpleNamespace(sample_no="SMP-0001")
        feedback = SimpleNamespace(feedback_no="FB20261016001")

        assert natural_id("Customer", customer) == "宁波恒见光电"
        assert natural_id("Inquiry", inquiry) == "JFX20261016001"
        assert natural_id("QuoteLibrary", quote) == "M-1#CE"
        assert natural_id("Order", order) == "SO-1#"
        assert natural_id("Sample", sample) == "SMP-0001"
        assert natural_id("Feedback", feedback) == "FB20261016001"

    def test_natural_id_sanitizes_sep(self) -> None:
        # `#` 为 object_id 保留字符，业务键分量含 `#` 时转义为 `~`
        quote = SimpleNamespace(external_model="M#1", certificate_level="CE")
        order = SimpleNamespace(order_no="SO#1", line_no="L#2")
        assert natural_id("QuoteLibrary", quote) == "M~1#CE"
        assert natural_id("Order", order) == "SO~1#L~2"


# ------------------------------------------------------------------ 出站真实路径（PAND-263 回归保护）


#: 冻结契约 §4.3 的代表性记录（真实序列化 + 真实 natural_id 走完整出站构造路径）
_OUTBOUND_RECORDS: dict[str, SimpleNamespace] = {
    "Customer": SimpleNamespace(
        name="宁波恒见光电",
        code="KH0001",
        former_name=None,
        parent_code=None,
        customer_level="A级（核心大客户）",
        sales_mode="外销",
        customer_status="大货合作客户",
        decision_maker=None,
        decision_maker_position=None,
        decision_core_need=None,
        last_trade_year=None,
        invoice_title=None,
        tax_id=None,
        bank_name=None,
        bank_account=None,
        address=None,
        country_region="中国",
        source="展会",
        remark=None,
        website=None,
    ),
    "Inquiry": SimpleNamespace(
        inquiry_no="JFX20261017001",
        customer_name="宁波恒见光电",
        customer_code="KH0001",
        market="中国",
        source="展会",
        quote_validity="30 天",
        status="pending_quote",
        delivery_date=date(2026, 11, 30),
        start_date=datetime(2026, 10, 17, 8, 0, tzinfo=UTC),
        items=[],
    ),
    "QuoteLibrary": SimpleNamespace(
        external_model="AC-100W",
        certificate_level="国标",
        internal_model=None,
        product_name="LED 投光灯",
        category=None,
        power="100W",
        configuration=None,
        specs=None,
        price_rmb=Decimal("85.50"),
        price_usd=None,
        unit_price=None,
        min_price=None,
        validity_days=30,
        usage_count=0,
        source_inquiry_no=None,
        source_pricing_id=None,
        creator=None,
    ),
    "Order": SimpleNamespace(
        order_no="SO20261017001",
        line_no="1",
        customer_name="宁波恒见光电",
        customer_code="KH0001",
        product_code="P-100",
        product_name="LED 投光灯",
        project_no="PRJ-2026-008",
        quantity=Decimal("100.00"),
        completed_qty=Decimal("0.00"),
        order_amount=Decimal("15600.00"),
        status="confirmed",
        risk_level="blue",
        promised_date=date(2026, 11, 1),
        plan_date=date(2026, 10, 25),
        online_date=date(2026, 10, 28),
        user_status_locked=False,
        user_status_modified_at=None,
        user_status_modified_by=None,
    ),
}


def _outbound_wire(object_type: str) -> dict:
    """按真实出站路径构造 event：serializer → natural_id → build_event_contract → to_wire。"""
    record = _OUTBOUND_RECORDS[object_type]
    contract = build_event_contract(
        event_id=f"EVT-M05-{object_type}-001",
        event_type=upsert_event_for(object_type),
        source_system="M05",
        object_type=object_type,
        object_id=natural_id(object_type, record),
        operation="UPSERT",
        payload=SERIALIZERS[object_type](record),
        trace_id=f"TRACE-M05-{object_type}",
        occurred_at=datetime(2026, 10, 17, 9, 30, tzinfo=UTC),
    )
    return to_wire(contract)


class TestOutboundRealPath:
    """PAND-263：真实出站路径（非硬编码 fixture）必须满足 R5 门禁与 §2 object_id 编码。"""

    @pytest.mark.parametrize("object_type", ["Customer", "Inquiry", "QuoteLibrary", "Order"])
    def test_outbound_event_passes_contract_gate(self, object_type: str) -> None:
        wire = _outbound_wire(object_type)
        assert wire["object_type"] == object_type, "object_type 必须为 PascalCase"
        assert wire["operation"] == "UPSERT", "operation 为契约必填字段"
        assert wire["event_type"] == upsert_event_for(object_type)
        # 再入券校验：真实出站报文必须可被契约反解（等价 EBMS validateAny 的字段级门禁）
        again = validate_contract(wire)
        assert isinstance(again, AeosEventContract)
        assert again.object_type == object_type
        assert again.operation == "UPSERT"

    def test_order_object_id_encodes_line_no(self) -> None:
        wire = _outbound_wire("Order")
        assert wire["object_id"] == "SO20261017001#1"
        assert event_idempotency_key("EBMS", wire) == (
            f"EBMS:order.upserted:SO20261017001#1:{event_fingerprint(wire)}"
        )

    def test_quote_library_object_id_encodes_certificate_level(self) -> None:
        wire = _outbound_wire("QuoteLibrary")
        assert wire["object_id"] == "AC-100W#国标"
        assert event_idempotency_key("EBMS", wire) == (
            f"EBMS:quote_library.upserted:AC-100W#国标:{event_fingerprint(wire)}"
        )


# ------------------------------------------------------------------ 入站契约层（PAND-254）


class _ScalarResult:
    def __init__(self, value: object) -> None:
        self._value = value

    def scalar_one_or_none(self) -> object:
        return self._value


class _FakeIngestSession:
    """极简内存会话：只为验证 ``ingest_event`` 的幂等/去重路径，不落真库。"""

    def __init__(self) -> None:
        self.objects: list[object] = []
        self.logs: list[object] = []

    async def execute(self, stmt: object) -> _ScalarResult:
        params: dict[str, object] = {}
        try:
            params = stmt.compile().params  # type: ignore[attr-defined]
        except Exception:
            params = {}
        entity: object | None = None
        try:
            entity = stmt.column_descriptions[0]["type"]  # type: ignore[index]
        except Exception:
            entity = None
        if entity is IntegrationLog:
            key = params.get("idempotency_key") or params.get("idempotency_key_1")
            for log in self.logs:
                if getattr(log, "idempotency_key", None) == key:
                    return _ScalarResult(log)
            return _ScalarResult(None)
        if entity is Company:
            eid = params.get("external_id") or params.get("external_id_1")
            for obj in self.objects:
                if isinstance(obj, Company) and obj.external_id == eid:
                    return _ScalarResult(obj)
            code = params.get("code") or params.get("code_1")
            for obj in self.objects:
                if isinstance(obj, Company) and code and obj.code == code:
                    return _ScalarResult(obj)
            name = params.get("name") or params.get("name_1")
            for obj in self.objects:
                if isinstance(obj, Company) and name and obj.name == name:
                    return _ScalarResult(obj)
            return _ScalarResult(None)
        return _ScalarResult(None)

    def add(self, obj: object) -> None:
        if isinstance(obj, IntegrationLog):
            self.logs.append(obj)
        else:
            self.objects.append(obj)

    async def flush(self) -> None:
        return None


class TestInboundContractLayer:
    """PAND-254 入站契约层：自然键→external_id 映射、头/体幂等键一致性、
    字典优雅降级，以及「同一对象重复投递不新增记录」（一物一 ID）。"""

    def test_external_id_encodes_natural_key(self) -> None:
        assert _external_id("Customer", {"name": "宁波恒见光电"}) == "宁波恒见光电"
        assert _external_id("Inquiry", {"serial_number": "JFX20261016001"}) == "JFX20261016001"
        assert (
            _external_id("QuoteLibrary", {"external_model": "AC-100W", "certificate_level": "CE"})
            == "AC-100W#CE"
        )
        assert _external_id("QuoteLibrary", {"external_model": "AC-100W"}) == "AC-100W#"
        assert _external_id("Order", {"order_no": "SO-1", "line_no": "1"}) == "SO-1#1"
        assert _external_id("Order", {"order_no": "SO#1", "line_no": "L#2"}) == "SO~1#L~2"

    def test_resolve_key_header_body_consistency(self) -> None:
        contract = validate_contract(_event())
        wire = _event()
        # 头/体一致 → 用头（= 体）
        assert _resolve_key(contract, wire, "K:BODY", "K:BODY") == "K:BODY"
        # 仅体 → 用体（EBMS 出站把 idempotency_key 写进 body）
        assert _resolve_key(contract, wire, "K:BODY", None) == "K:BODY"
        # 仅头 → 用头
        assert _resolve_key(contract, wire, None, "K:HDR") == "K:HDR"
        # 头/体不一致 → 422（对齐 EBMS aeos-http.js 头/体一致）
        with pytest.raises(ContractValidationError):
            _resolve_key(contract, wire, "K:BODY", "K:OTHER")
        # 都没有 → 按 target=M05 重算
        key = _resolve_key(contract, wire, None, None)
        assert key.startswith("M05:customer.upserted:")

    async def test_dictionary_ingest_graceful(self) -> None:
        ev = _event(
            event_type="dictionary.upserted",
            source_system="EBMS",
            object_type="Dictionary",
            object_id="cert_levels",
            payload={"dict_type": "cert_levels"},
        )
        result = await ingest_event(None, ev)  # Dictionary 早返回，不触库
        assert result["status"] == "not_implemented"
        assert result["object_type"] == "Dictionary"

    async def test_repeat_delivery_does_not_create_duplicate(self) -> None:
        db = _FakeIngestSession()
        ev = _event(
            event_type="customer.upserted",
            source_system="EBMS",
            object_type="Customer",
            object_id="宁波恒见光电",
            payload={"name": "宁波恒见光电", "customer_code": "KH0001", "remarks": "重点客户"},
            idempotency_key="M05:customer.upserted:宁波恒见光电:fp0001",
        )
        first = await ingest_event(db, ev)
        second = await ingest_event(db, ev)
        assert first["status"] == "created"
        assert second["status"] == "duplicate"
        assert len(db.objects) == 1
        assert len(db.logs) == 1
