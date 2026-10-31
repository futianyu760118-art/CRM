"""PAND-298 自检断言：3 项业务观察项落地。

1. 欧洲市场系数规则：``price_multiplier=1.05`` → ``margin_delta=+0.05``，M2.5-D2 后生效。
2. 折扣金额门槛：可配置附加条件，默认关闭时三档判定不变；开启后超门槛升一级。
3. 可维护汇率：``system_config.pricing.exchange_rate`` 取值，缺省 7.25。

运行（纯逻辑，无需数据库）：
    python -m pytest tests/test_pand298_selfcheck.py -v
"""

from __future__ import annotations

from typing import Any

from app.db.seed import DEFAULT_CONFIGS, DEFAULT_PRICING_RULES
from app.services import approval as approval_service
from app.services import pricing as pricing_service
from app.services import system_config


class _FakeResult:
    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value


class _FakeDb:
    def __init__(self, *values: Any) -> None:
        self._values = iter(values)

    async def execute(self, _stmt: Any) -> _FakeResult:
        return _FakeResult(next(self._values))


def _eu_rule() -> dict[str, Any]:
    return next(r for r in DEFAULT_PRICING_RULES if r["code"] == "RULE-EU")


class _Rule:
    enabled = True
    priority = 80
    code = "RULE-EU"
    conditions = {"country": {"in": ["Germany", "France", "Italy", "Spain", "Netherlands"]}}
    actions = {"margin_delta": 0.05}


# ---------------------------------------------------------------- 1. 欧洲系数规则
class TestEuRule:
    def test_seed_rule_uses_margin_delta(self) -> None:
        actions = _eu_rule()["actions"]
        assert actions == {"margin_delta": 0.05}, "欧洲规则应转换为 margin_delta=+0.05"
        assert "price_multiplier" not in actions

    def test_eu_rule_raises_profit_rate(self) -> None:
        result = pricing_service.calculate(
            costs={"material_cost": 100},
            profit_rate=0.2,
            rules=[_Rule()],
            context={"country": "Germany"},
            discount_rate=1,
        )
        assert result["profit_rate"] == 0.25, "欧洲规则应在默认 0.2 上 +0.05"
        assert result["final_price"] == 125.0, f"final_price 实际={result['final_price']} 期望=125.00"

    def test_non_eu_unaffected(self) -> None:
        result = pricing_service.calculate(
            costs={"material_cost": 100},
            profit_rate=0.2,
            rules=[_Rule()],
            context={"country": "USA"},
            discount_rate=1,
        )
        assert result["applied_rules"] == []
        assert result["final_price"] == 120.0


# ---------------------------------------------------------------- 2. 折扣金额门槛
class TestDiscountAmountThreshold:
    def test_default_off_keeps_three_tiers(self) -> None:
        assert approval_service.steps_for("QUOTATION", 1.0, 1_000_000) == [], "默认关闭：=1 仍免审"
        assert approval_service.steps_for("QUOTATION", 0.95, 1_000_000) == ["manager"], "默认关闭：0.95 仍经理"
        assert approval_service.steps_for("QUOTATION", 0.94, 1_000_000) == ["boss"], "默认关闭：0.94 仍总监"

    def test_enabled_upgrades_one_level(self) -> None:
        kwargs = {"amount_threshold_enabled": True, "amount_threshold": 50000}
        assert approval_service.steps_for("QUOTATION", 1.0, 60000, **kwargs) == ["manager"]
        assert approval_service.steps_for("QUOTATION", 0.95, 60000, **kwargs) == ["manager", "boss"]
        assert approval_service.steps_for("QUOTATION", 0.94, 60000, **kwargs) == ["boss"]

    def test_enabled_below_threshold_keeps_tier(self) -> None:
        kwargs = {"amount_threshold_enabled": True, "amount_threshold": 50000}
        assert approval_service.steps_for("QUOTATION", 1.0, 50000, **kwargs) == [], "等于门槛不升级"
        assert approval_service.steps_for("QUOTATION", 0.95, 49999, **kwargs) == ["manager"]

    async def test_load_amount_threshold_reads_config(self) -> None:
        enabled, threshold = await approval_service.load_amount_threshold(_FakeDb("true", "60000"))
        assert enabled is True
        assert threshold == 60000.0

    async def test_load_amount_threshold_defaults_off(self) -> None:
        enabled, threshold = await approval_service.load_amount_threshold(_FakeDb(None, None))
        assert enabled is False, "缺少配置项时金额门槛默认关闭"
        assert threshold == approval_service.DEFAULT_AMOUNT_THRESHOLD

    def test_config_keys_seeded(self) -> None:
        keys = {row[0] for row in DEFAULT_CONFIGS}
        assert approval_service.AMOUNT_THRESHOLD_ENABLED_KEY in keys
        assert approval_service.AMOUNT_THRESHOLD_KEY in keys


# ---------------------------------------------------------------- 3. 可维护汇率
class TestExchangeRateConfig:
    def test_default_is_7_25(self) -> None:
        assert system_config.parse_float(None, pricing_service.DEFAULT_EXCHANGE_RATE) == 7.25
        assert pricing_service.DEFAULT_EXCHANGE_RATE == 7.25

    def test_config_value_overrides_default(self) -> None:
        assert system_config.parse_float("7.35", 7.25) == 7.35

    def test_invalid_value_falls_back(self) -> None:
        assert system_config.parse_float("abc", 7.25) == 7.25

    async def test_get_float_reads_system_config(self) -> None:
        value = await system_config.get_float(_FakeDb("7.35"), pricing_service.EXCHANGE_RATE_CONFIG_KEY, 7.25)
        assert value == 7.35

    async def test_missing_config_uses_default(self) -> None:
        value = await system_config.get_float(_FakeDb(None), pricing_service.EXCHANGE_RATE_CONFIG_KEY, 7.25)
        assert value == 7.25

    def test_exchange_rate_key_seeded(self) -> None:
        rows = {row[0]: row[1] for row in DEFAULT_CONFIGS}
        assert rows.get(pricing_service.EXCHANGE_RATE_CONFIG_KEY) == "7.25"
