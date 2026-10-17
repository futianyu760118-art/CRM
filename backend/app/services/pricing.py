"""核价计算与核价规则引擎（M4）。

M2.5 口径（签批 D1~D5=A）：
- 成本并轨 9 项：以 CRM 8 项为录入口径，新增 ``loss_cost``（默认 0）；
  ``base_cost`` = 9 项合计。EBMS 侧 ``process_cost→labor_cost``、
  ``accessory_cost→packaging_cost``、``estimated_loss→loss_cost``。
- 报价公式统一 EBMS：``final_price = base_cost × (1 + profit_rate) × discount_rate``；
  规则引擎只调利润率，不再直接乘最终价。
- ``floor_price`` = 单位成本（零利润底线）。
- 取整：成本/中间值 4 位、对外报价 2 位；汇率在报价创建时快照（默认 7.25）。
- 利润率全局默认 0.2，支持规则覆盖。
"""

from __future__ import annotations

from typing import Any

COST_FIELDS = (
    "material_cost",
    "labor_cost",
    "packaging_cost",
    "freight_cost",
    "tooling_cost",
    "customization_cost",
    "moq_cost",
    "other_cost",
    "loss_cost",
)

#: EBMS 成本项 → CRM 录入口径（成本并轨映射，用于跨系统口径对齐）。
EBMS_TO_CRM_COST_FIELDS = {
    "material_cost": "material_cost",
    "process_cost": "labor_cost",
    "accessory_cost": "packaging_cost",
    "estimated_loss": "loss_cost",
}

COST_LABELS = {
    "material_cost": "材料成本",
    "labor_cost": "人工成本",
    "packaging_cost": "包装成本",
    "freight_cost": "运费",
    "tooling_cost": "模具费",
    "customization_cost": "定制费",
    "moq_cost": "起订量成本",
    "other_cost": "其他成本",
    "loss_cost": "损耗成本",
}

DEFAULT_PROFIT_RATE = 0.2
DEFAULT_DISCOUNT_RATE = 1.0
DEFAULT_EXCHANGE_RATE = 7.25
#: 历史别名，保持向后兼容。
DEFAULT_MARGIN = DEFAULT_PROFIT_RATE


def base_cost_of(costs: dict[str, Any]) -> float:
    """9 项成本合计（保留 4 位）。"""
    return round(sum(float(costs.get(f) or 0) for f in COST_FIELDS), 4)


#: 历史别名，保持向后兼容。
def total_of(costs: dict[str, Any]) -> float:
    return base_cost_of(costs)


def _match(conditions: dict[str, Any] | None, context: dict[str, Any]) -> bool:
    if not conditions:
        return False
    for key, expected in conditions.items():
        actual = context.get(key)
        if isinstance(expected, dict):
            # 支持 {"gte": x} / {"lte": x} / {"eq": x} / {"in": [...]}
            if "gte" in expected and (actual is None or float(actual) < float(expected["gte"])):
                return False
            if "lte" in expected and (actual is None or float(actual) > float(expected["lte"])):
                return False
            if "gt" in expected and (actual is None or float(actual) <= float(expected["gt"])):
                return False
            if "lt" in expected and (actual is None or float(actual) >= float(expected["lt"])):
                return False
            if "eq" in expected and actual != expected["eq"]:
                return False
            if "in" in expected and actual not in expected["in"]:
                return False
            if "contains" in expected and expected["contains"] not in (actual or ""):
                return False
        elif actual != expected:
            return False
    return True


def apply_rules(rules: list[Any], context: dict[str, Any], profit_rate: float) -> tuple[float, list[str]]:
    """按优先级应用规则，只调整利润率，返回 (profit_rate, 命中的规则编码)。

    M2.5-D2：规则引擎不再直接乘最终价（不保留 price_multiplier）。
    """
    hits: list[str] = []
    for rule in sorted(rules, key=lambda r: r.priority, reverse=True):
        if not rule.enabled:
            continue
        if not _match(rule.conditions, context):
            continue
        actions = rule.actions or {}
        if "margin" in actions:
            profit_rate = float(actions["margin"])
        if "margin_delta" in actions:
            profit_rate = profit_rate + float(actions["margin_delta"])
        hits.append(rule.code)
    return round(profit_rate, 4), hits


def calculate(
    *,
    costs: dict[str, Any],
    quantity: float = 1,
    profit_rate: float = DEFAULT_PROFIT_RATE,
    rules: list[Any] | None = None,
    context: dict[str, Any] | None = None,
    discount_rate: float = DEFAULT_DISCOUNT_RATE,
    exchange_rate: float | None = None,
) -> dict[str, Any]:
    """成本归集 + 底价 + 最终报价（EBMS 公式）。

    - ``base_cost``：9 项成本合计（4 位）
    - ``unit_cost`` / ``floor_price``：单位成本，即可接受的最低价（零利润底线）
    - ``final_price``：``base_cost × (1 + profit_rate) × discount_rate``（对外 2 位）

    ``exchange_rate`` 已不参与核价（历史参数保留兼容）：汇率在报价创建时快照。
    """
    qty = float(quantity) or 1
    base_cost = base_cost_of(costs)
    unit_cost = round(base_cost / qty, 4)

    pr = float(profit_rate if profit_rate is not None else DEFAULT_PROFIT_RATE)
    hits: list[str] = []
    if rules:
        pr, hits = apply_rules(rules, context or {}, pr)

    pr = max(min(pr, 10.0), -0.99)
    dr = max(min(float(discount_rate if discount_rate is not None else DEFAULT_DISCOUNT_RATE), 1.0), 1e-9)

    floor_price = unit_cost
    final_price = round(base_cost * (1 + pr) * dr, 2)

    return {
        "base_cost": base_cost,
        "total_cost": base_cost,
        "unit_cost": unit_cost,
        "floor_price": floor_price,
        "final_price": final_price,
        "suggested_price": final_price,
        "profit_rate": pr,
        "target_margin": pr,
        "discount_rate": dr,
        "breakdown": {f: float(costs.get(f) or 0) for f in COST_FIELDS},
        "applied_rules": hits,
    }
