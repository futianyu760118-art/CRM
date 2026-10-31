"""PAND-316 自检：产品资料 / 标准报价 / 商机流转 / 样品管理纯逻辑。"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.domain.state_machine import (
    SAMPLE_STATUS_FROM_WIRE,
    SAMPLE_STATUS_LABELS,
    SAMPLE_STATUS_MIGRATION,
    SAMPLE_STATUS_WIRE_MAP,
    SAMPLE_STATUSES,
    SAMPLE_TERMINAL_STATUS,
    STAGE_RULES,
)
from app.models.sales import Sample
from app.models.user import Role, User
from app.schemas.business import OpportunityStageIn, StandardQuoteCreate
from app.schemas.sales import SampleCreate, SampleStatusIn, SampleUpdate
from app.services import opportunity_stage, product_assets
from app.services.ebms_ingest import _map_payload
from app.services.ebms_sync import sample_payload


# ------------------------------------------------------------------ 产品资料版本号
class TestDocumentVersion:
    @pytest.mark.parametrize("value", ["v1", "v1.0", "v1.2.3", "v12.34.56"])
    def test_accepts_documented_formats(self, value: str) -> None:
        assert product_assets.validate_version(value) == value

    @pytest.mark.parametrize("value", ["", "1", "V1", "v1.", "v1.2.3.4", "v1a"])
    def test_rejects_invalid_formats(self, value: str) -> None:
        with pytest.raises(ValueError):
            product_assets.validate_version(value)

    def test_numeric_ordering_not_lexicographic(self) -> None:
        assert product_assets.version_key("v1.10") > product_assets.version_key("v1.9")

    def test_next_version_increments_major(self) -> None:
        assert product_assets.next_version_no([]) == "v1"
        assert product_assets.next_version_no(["v1", "v2.3"]) == "v3"

    def test_upload_allows_whitelist_and_50mb(self) -> None:
        assert product_assets.file_extension("方案.PDF") == "pdf"
        assert product_assets.validate_upload("方案.pdf", 1024) == "pdf"
        with pytest.raises(ValueError, match="不支持的格式"):
            product_assets.validate_upload("方案.exe", 1024)
        with pytest.raises(ValueError, match="50MB"):
            product_assets.validate_upload("方案.pdf", product_assets.DOC_MAX_BYTES + 1)
        with pytest.raises(ValueError, match="内容为空"):
            product_assets.validate_upload("方案.pdf", 0)


# ------------------------------------------------------------------ 标准报价
class TestStandardQuoteRules:
    def test_interval_is_half_open(self) -> None:
        assert product_assets.interval_overlaps(1, 100, 100, 200) is False
        assert product_assets.interval_overlaps(100, None, 1, 200) is True
        assert product_assets.interval_overlaps(1, None, 1, None) is True

    def test_price_requires_four_decimals_max(self) -> None:
        assert product_assets.normalize_price("12.3456") == Decimal("12.3456")
        with pytest.raises(ValueError, match="4 位小数"):
            product_assets.normalize_price("12.34567")
        with pytest.raises(ValueError, match="大于 0"):
            product_assets.normalize_price(0)

    def test_status_derivation(self) -> None:
        today = date(2026, 10, 31)
        assert product_assets.quote_status("ACTIVE", today, today + timedelta(days=1), today) == "ACTIVE"
        expired = (today - timedelta(days=5), today - timedelta(days=1))
        assert product_assets.quote_status("ACTIVE", *expired, today) == "EXPIRED"
        pending = (today + timedelta(days=1), today + timedelta(days=5))
        assert product_assets.quote_status("ACTIVE", *pending, today) == "PENDING"
        assert product_assets.quote_status("DISABLED", today, today + timedelta(days=5), today) == "DISABLED"
        assert product_assets.quote_status_label("ACTIVE", today, today, today) == "生效中"

    def test_disabled_quote_is_not_overlap_blocker(self) -> None:
        disabled = product_assets.StandardQuote(
            qty_from=1, qty_to=None, status=product_assets.QUOTE_DISABLED
        )
        assert product_assets.find_overlap([disabled], 1, None) is None

    def test_schema_rejects_bad_currency_and_dates(self) -> None:
        with pytest.raises(ValidationError):
            StandardQuoteCreate(
                currency="XXX",
                qty_from=1,
                unit_price=1,
                valid_from=date(2026, 1, 1),
                valid_to=date(2026, 2, 1),
                version_no="v1",
            )


# ------------------------------------------------------------------ 商机阶段
class TestOpportunityStage:
    def test_required_fields_match_stage_rules(self) -> None:
        assert opportunity_stage.required_fields("REQUIREMENT") == ["product_category", "quantity"]
        assert opportunity_stage.required_fields("PRICING") == ["pricing_id"]
        assert opportunity_stage.required_fields("SAMPLE") == ["sample_record"]
        assert opportunity_stage.required_field_label("SAMPLE", "sample_record") == "样品记录或关联样品单"
        assert opportunity_stage.required_field_label("PRICING", "pricing_id") == "关联核价记录"

    def test_missing_error_is_chinese_and_actionable(self) -> None:
        err = opportunity_stage.missing_error("REQUIREMENT", "QUALIFIED", ["产品类别", "数量"])
        assert "流转至【需求明确】失败" in err.message
        assert "缺少必填项——产品类别、数量" in err.message
        assert "可流转至：需求明确、流失" in err.message
        assert err.data is not None
        assert err.data["allowed_targets"] == ["REQUIREMENT", "LOST"]

    def test_invalid_transition_error_lists_targets(self) -> None:
        err = opportunity_stage.invalid_transition_error("QUOTATION", "INQUIRY")
        assert "不能从【询价中】流转到【已报价】" in err.message
        assert "可流转至：核价中、流失" in err.message

    def test_role_error_mentions_current_role_and_proxy(self) -> None:
        user = User(username="u1", name="张三", status="ACTIVE", is_superuser=False)
        user.roles = [Role(code="sales", name="销售")]
        err = opportunity_stage.role_error("PRICING", "INQUIRY", user)
        assert "仅限【核价员】操作" in err.message
        assert "当前角色【销售】" in err.message
        assert "可请主管代办" in err.message
        assert err.http_status == 403

    def test_role_allowed(self) -> None:
        sales = User(username="s", name="销售", status="ACTIVE", is_superuser=False)
        sales.roles = [Role(code="sales", name="销售")]
        pricing = User(username="p", name="核价", status="ACTIVE", is_superuser=False)
        pricing.roles = [Role(code="pricing", name="核价员")]
        assert opportunity_stage.role_allowed(sales, "PRICING") is False
        assert opportunity_stage.role_allowed(pricing, "PRICING") is True
        assert opportunity_stage.role_allowed(sales, "QUOTATION") is True

    def test_auto_advance_forward_only(self) -> None:
        opp = opportunity_stage.Opportunity(opportunity_no="OPP1", name="A", stage="INQUIRY", status="OPEN")
        assert opportunity_stage.auto_advance(
            opp, "PRICING", from_stages={"INQUIRY"}, values={"pricing_id": None}
        )
        assert opp.stage == "PRICING"
        # 不回退、不重复
        assert opportunity_stage.auto_advance(
            opp, "INQUIRY", from_stages={"NEW"}, values={}
        ) is False
        assert opp.stage == "PRICING"

    def test_apply_transition_closes_terminal_stage(self) -> None:
        opp = opportunity_stage.Opportunity(
            opportunity_no="OPP2", name="B", stage="NEGOTIATION", status="OPEN"
        )
        opportunity_stage.apply_transition(opp, "WON", {"won_amount": 100.0})
        assert opp.stage == "WON"
        assert opp.status == "CLOSED"
        assert opp.probability == 100
        assert opp.won_amount == 100.0

    def test_stage_payload_blank_strings_become_missing(self) -> None:
        payload = OpportunityStageIn(
            stage="REQUIREMENT", product_category="   ", quantity=10, requirement="  "
        )
        assert payload.product_category is None
        assert payload.requirement is None
        assert payload.quantity == 10


# ------------------------------------------------------------------ 样品
class TestSampleRules:
    def test_five_status_chain_and_labels(self) -> None:
        assert SAMPLE_STATUSES == ["pending", "producing", "testing", "sent", "feedback"]
        assert [SAMPLE_STATUS_LABELS[s] for s in SAMPLE_STATUSES] == [
            "待确认",
            "制作中",
            "测试中",
            "已寄出",
            "客户反馈",
        ]
        assert SAMPLE_TERMINAL_STATUS == "feedback"

    def test_migration_and_wire_maps(self) -> None:
        assert SAMPLE_STATUS_MIGRATION["confirmed"] == "producing"
        assert SAMPLE_STATUS_MIGRATION["customer_confirmed"] == "feedback"
        assert SAMPLE_STATUS_MIGRATION["completed"] == "feedback"
        assert SAMPLE_STATUS_WIRE_MAP["testing"] == "producing"
        assert SAMPLE_STATUS_WIRE_MAP["feedback"] == "customer_confirmed"
        assert SAMPLE_STATUS_FROM_WIRE["customer_confirmed"] == "feedback"
        assert SAMPLE_STATUS_FROM_WIRE["confirmed"] == "producing"

    def test_create_requires_product_model_and_defaults_quantity(self) -> None:
        with pytest.raises(ValidationError):
            SampleCreate(customer_name="A 公司", product_model="")
        row = SampleCreate(customer_name="A 公司", product_model="X-100")
        assert row.quantity == 1
        assert row.sample_type == "常规"

    def test_quantity_two_decimals_only(self) -> None:
        with pytest.raises(ValidationError):
            SampleCreate(customer_name="A", product_model="X", quantity=1.234)

    def test_tracking_pattern_and_courier_enum(self) -> None:
        SampleStatusIn(status="sent", courier="SF", tracking_no="SF123456")
        with pytest.raises(ValidationError):
            SampleStatusIn(status="sent", tracking_no="123")
        with pytest.raises(ValidationError):
            SampleStatusIn(status="sent", courier="UNKNOWN", tracking_no="SF123456")
        assert SampleStatusIn(status="sent", tracking_no="SF-123456").tracking_no == "SF-123456"

    def test_plan_date_floor(self) -> None:
        today = date(2026, 10, 31)
        assert product_assets.default_plan_date(today) == today + timedelta(days=7)
        assert SampleUpdate(plan_date=today - timedelta(days=1)).plan_date == today - timedelta(days=1)

    def test_outbound_payload_keeps_old_wire_status_and_field_list(self) -> None:
        sample = Sample(
            sample_no="SMP-0001",
            customer_name="A 公司",
            product_model="X-100",
            quantity=1,
            sample_type="常规",
            status="testing",
            sample_requirement="防水",
        )
        payload = sample_payload(sample)
        # PAND-314 D4：线字段清单与状态值域不变，5 态映射回旧值
        assert payload["status"] == "producing"
        assert "product_model" not in payload
        assert "sample_requirement" not in payload
        assert set(payload) == {
            "sample_no",
            "customer_name",
            "quantity",
            "sample_type",
            "status",
        }

    def test_inbound_wire_status_maps_back(self) -> None:
        assert _map_payload("Sample", {"status": "customer_confirmed"}) == {"status": "feedback"}
        assert _map_payload("Sample", {"status": "confirmed"}) == {"status": "producing"}
        assert _map_payload("Sample", {"status": "pending"}) == {"status": "pending"}

    def test_stage_rules_cover_all_stages(self) -> None:
        for stage, rule in STAGE_RULES.items():
            for field in rule.required_fields:
                assert opportunity_stage.required_field_label(stage, field)
