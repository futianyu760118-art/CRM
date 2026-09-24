"""核价计算与核价规则引擎（M4）。"""

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
)

COST_LABELS = {
    "material_cost": "材料成本",
    "labor_cost": "人工成本",
    "packaging_cost": "包装成本",
    "freight_cost": "运费",
    "tooling_cost": "模具费",
    "customization_cost": "定制费",
    "moq_cost": "起订量成本",
    "other_cost": "其他成本",
}

DEFAULT_MARGIN = 0.2


def total_of(costs: dict[str, Any]) -> float:
    return round(sum(float(costs.get(f) or 0) for f in COST_FIELDS), 4)


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


def apply_rules(rules: list[Any], context: dict[str, Any], margin: float) -> tuple[float, float, list[str]]:
    """按优先级应用规则，返回 (margin, price_multiplier, 命中的规则编码)。"""
    multiplier = 1.0
    hits: list[str] = []
    for rule in sorted(rules, key=lambda r: r.priority, reverse=True):
        if not rule.enabled:
            continue
        if not _match(rule.conditions, context):
            continue
        actions = rule.actions or {}
        if "margin" in actions:
            margin = float(actions["margin"])
        if "margin_delta" in actions:
            margin = margin + float(actions["margin_delta"])
        if "price_multiplier" in actions:
            multiplier *= float(actions["price_multiplier"])
        hits.append(rule.code)
    return round(margin, 4), round(multiplier, 6), hits


def calculate(
    *,
    costs: dict[str, Any],
    quantity: float = 1,
    target_margin: float = DEFAULT_MARGIN,
    rules: list[Any] | None = None,
    context: dict[str, Any] | None = None,
    exchange_rate: float = 1.0,
) -> dict[str, Any]:
    """成本汇总 + 底价 + 建议售价。

    - total_cost：成本合计
    - unit_cost / floor_price：单位成本，即可接受的最低价（底价）
    - suggested_price：底价 × (1 + 目标利润率) × 规则系数
    """
    qty = float(quantity) or 1
    total_cost = total_of(costs)
    unit_cost = round(total_cost / qty, 4)

    margin = float(target_margin if target_margin is not None else DEFAULT_MARGIN)
    multiplier = 1.0
    hits: list[str] = []
    if rules:
        margin, multiplier, hits = apply_rules(rules, context or {}, margin)

    margin = max(min(margin, 10.0), -0.99)
    floor_price = round(unit_cost * exchange_rate, 4)
    suggested_price = round(floor_price * (1 + margin) * multiplier, 4)

    return {
        "total_cost": total_cost,
        "unit_cost": unit_cost,
        "floor_price": floor_price,
        "suggested_price": suggested_price,
        "target_margin": margin,
        "breakdown": {f: float(costs.get(f) or 0) for f in COST_FIELDS},
        "applied_rules": hits,
    }
