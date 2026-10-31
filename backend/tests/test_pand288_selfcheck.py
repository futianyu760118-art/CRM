"""PAND-288 自检断言：M2.5 报价成本结构 + M2.6 折扣审批。

取证口径（对齐签批表 PAND-285「默认」=A）：
- M2.5：成本并轨 9 项（含 loss_cost 默认 0），base_cost = 9 项合计；
  报价公式统一 EBMS：final_price = base_cost × (1+利润率) × 折扣率；
  规则引擎只调利润率；floor_price = 单位成本；取整 4/2 位；利润率默认 0.2。
- M2.6：折扣率三档审批 =1 免审、[0.95,1) 经理、<0.95 总监（0.95 归经理）；
  层级 经理→manager、总监→boss；折扣率 ∈(0,1]，相对标准价 = base_cost×(1+利润率)。

运行（纯逻辑，无需数据库）：
    python -m pytest tests/test_pand288_selfcheck.py -v
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.pricing import PricingCreate
from app.services import approval as approval_service
from app.services import pricing as pricing_service


# ---------------------------------------------------------------- AC-M2.5
class TestM25CostStructure:
    def test_base_cost_is_sum_of_9_items_including_loss(self) -> None:
        costs = {
            "material_cost": 60,
            "labor_cost": 20,
            "packaging_cost": 10,
            "freight_cost": 10,
            "tooling_cost": 10,
            "customization_cost": 5,
            "moq_cost": 5,
            "other_cost": 5,
            "loss_cost": 5,
        }
        assert pricing_service.base_cost_of(costs) == 130, "9 项合计应等于 130"

    def test_loss_cost_defaults_to_zero(self) -> None:
        result = pricing_service.calculate(costs={"material_cost": 100}, profit_rate=0.2, discount_rate=1)
        assert result["breakdown"]["loss_cost"] == 0, "未填 loss_cost 应默认 0"
        assert result["base_cost"] == 100

    def test_final_price_formula_at_full_discount(self) -> None:
        # base_cost=130 → final_price = 130 × 1.2 × 1 = 156.00
        result = pricing_service.calculate(costs={"material_cost": 130}, quantity=1, profit_rate=0.2, discount_rate=1)
        assert result["base_cost"] == 130
        assert result["final_price"] == 156.0, f"final_price 实际={result['final_price']} 期望=156.00"

    def test_final_price_formula_at_95pct_discount(self) -> None:
        # base_cost=130 → final_price = 130 × 1.2 × 0.95 = 148.20
        result = pricing_service.calculate(
            costs={"material_cost": 130}, quantity=1, profit_rate=0.2, discount_rate=0.95
        )
        assert result["final_price"] == 148.2, f"final_price 实际={result['final_price']} 期望=148.20"

    def test_floor_price_equals_unit_cost(self) -> None:
        result = pricing_service.calculate(costs={"material_cost": 130}, quantity=2, profit_rate=0.2, discount_rate=1)
        assert result["unit_cost"] == 65.0, "unit_cost = base_cost / 数量"
        assert result["floor_price"] == result["unit_cost"], "floor_price 应等于单位成本（零利润底线）"
        # 最终价是总价，不随数量摊薄
        assert result["final_price"] == 156.0

    def test_rounding_cost_4_and_price_2(self) -> None:
        result = pricing_service.calculate(
            costs={"material_cost": 1.234, "labor_cost": 2.345}, quantity=1, profit_rate=0.2, discount_rate=1
        )
        # 成本/中间值 4 位：1.234 + 2.345 = 3.579
        assert result["base_cost"] == 3.579
        # 对外报价 2 位：3.579 × 1.2 = 4.2948 → 4.29
        assert result["final_price"] == 4.29, f"对外报价应取 2 位，实际={result['final_price']}"

    def test_profit_rate_default_0_2(self) -> None:
        result = pricing_service.calculate(costs={"material_cost": 100}, discount_rate=1)
        assert result["final_price"] == 120.0, f"默认利润率 0.2，final_price 实际={result['final_price']} 期望=120.00"

    def test_rules_adjust_profit_rate_only(self) -> None:
        class _Rule:
            enabled = True
            priority = 1
            code = "R1"
            conditions = {"customer_level": "A级（核心大客户）"}
            # price_multiplier 已废弃：规则只调利润率，不再直接乘最终价
            actions = {"margin": 0.3, "price_multiplier": 0.8}

        result = pricing_service.calculate(
            costs={"material_cost": 100},
            quantity=1,
            profit_rate=0.2,
            rules=[_Rule()],
            context={"customer_level": "A级（核心大客户）"},
            discount_rate=1,
        )
        assert result["profit_rate"] == 0.3, "规则应把利润率从 0.2 覆盖为 0.3"
        # 100 × 1.3 × 1 = 130（价格乘数 0.8 不再生效）
        assert result["final_price"] == 130.0, f"规则只调利润率，final_price 实际={result['final_price']} 期望=130.00"
        assert result["applied_rules"] == ["R1"]


class TestM25EbmsMapping:
    def test_ebms_to_crm_cost_field_mapping(self) -> None:
        mapping = pricing_service.EBMS_TO_CRM_COST_FIELDS
        assert mapping["process_cost"] == "labor_cost"
        assert mapping["accessory_cost"] == "packaging_cost"
        assert mapping["estimated_loss"] == "loss_cost"


# ---------------------------------------------------------------- AC-M2.6
class TestM26DiscountApproval:
    def test_discount_1_is_exempt(self) -> None:
        assert approval_service.steps_for("PRICING", 1.0) == [], "折扣率=1 应免审"

    def test_discount_0_95_goes_to_manager(self) -> None:
        assert approval_service.steps_for("PRICING", 0.95) == ["manager"], "0.95 应归经理档"

    def test_discount_0_94_goes_to_boss(self) -> None:
        assert approval_service.steps_for("PRICING", 0.94) == ["boss"], "0.94 应归总监档"

    def test_discount_within_manager_band(self) -> None:
        assert approval_service.steps_for("QUOTATION", 0.999) == ["manager"], "[0.95,1) 区间应归经理档"

    def test_discount_none_treated_as_exempt(self) -> None:
        assert approval_service.steps_for("QUOTATION", None) == [], "未填折扣率按 1 免审"

    def test_discount_rate_is_relative_to_standard_price(self) -> None:
        # 标准价 = base_cost × (1+利润率)；折扣率相对标准价，而非直接乘最终价
        standard = 130 * (1 + 0.2)
        result = pricing_service.calculate(
            costs={"material_cost": 130}, quantity=1, profit_rate=0.2, discount_rate=0.95
        )
        assert result["final_price"] == round(standard * 0.95, 2), "折扣率应相对标准价生效"


class TestM26DiscountRateValidation:
    def test_discount_rate_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PricingCreate(inquiry_id="00000000-0000-0000-0000-000000000000", discount_rate=0)

    def test_discount_rate_above_one_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PricingCreate(inquiry_id="00000000-0000-0000-0000-000000000000", discount_rate=1.5)

    def test_discount_rate_0_95_accepted(self) -> None:
        p = PricingCreate(inquiry_id="00000000-0000-0000-0000-000000000000", discount_rate=0.95)
        assert p.discount_rate == 0.95
