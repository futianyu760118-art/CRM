"""状态机定义（DOC-PRD-001 § 5），第1周冻结。

- 商机阶段：NEW → QUALIFIED → REQUIREMENT → INQUIRY → PRICING → QUOTATION
            → SAMPLE → NEGOTIATION → WON（任意阶段可转 LOST，须填流失原因）
- 询价状态：DRAFT → SUBMITTED → PRICING → PRICED → QUOTED → CLOSED
- 报价状态：DRAFT → PENDING_APPROVAL → APPROVED → SENT → ACCEPTED / REJECTED → EXPIRED
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------- 商机阶段

OPPORTUNITY_STAGES: list[str] = [
    "NEW",
    "QUALIFIED",
    "REQUIREMENT",
    "INQUIRY",
    "PRICING",
    "QUOTATION",
    "SAMPLE",
    "NEGOTIATION",
    "WON",
    "LOST",
]

STAGE_LABELS: dict[str, str] = {
    "NEW": "新建",
    "QUALIFIED": "已确认",
    "REQUIREMENT": "需求明确",
    "INQUIRY": "询价中",
    "PRICING": "核价中",
    "QUOTATION": "已报价",
    "SAMPLE": "样品阶段",
    "NEGOTIATION": "谈判中",
    "WON": "赢单",
    "LOST": "流失",
}


@dataclass(frozen=True)
class StageRule:
    label: str
    required_fields: list[str] = field(default_factory=list)
    roles: list[str] = field(default_factory=list)
    description: str = ""


# 阶段进入条件与必填字段
STAGE_RULES: dict[str, StageRule] = {
    "NEW": StageRule("新建", ["name", "company_id"], ["sales"]),
    "QUALIFIED": StageRule("已确认", ["requirement", "estimated_amount"], ["sales"], "确认有需求"),
    "REQUIREMENT": StageRule("需求明确", ["product_category", "quantity"], ["sales"], "需求明确"),
    "INQUIRY": StageRule("询价中", ["inquiry_id"], ["sales"], "创建询价单"),
    "PRICING": StageRule("核价中", ["pricing_id"], ["pricing"], "核价完成"),
    "QUOTATION": StageRule("已报价", ["quotation_amount"], ["sales"], "报价单创建"),
    "SAMPLE": StageRule("样品阶段", ["sample_record"], ["sales"], "客户要求样品"),
    "NEGOTIATION": StageRule("谈判中", ["negotiation_record"], ["sales", "manager"], "进入谈判"),
    "WON": StageRule("赢单", ["won_amount"], ["sales", "manager"], "客户确认成交"),
    "LOST": StageRule("流失", ["lost_reason"], ["sales", "manager"], "客户流失"),
}

# 正向流转链（不允许跳级，LOST 除外）
_STAGE_ORDER = OPPORTUNITY_STAGES[:-1]  # 去掉 LOST


def allowed_opportunity_transitions(current: str) -> list[str]:
    # WON / LOST 为终态，不允许再流转
    if current in {"WON", "LOST"} or current not in _STAGE_ORDER:
        return []
    idx = _STAGE_ORDER.index(current)
    nxt: list[str] = []
    if idx + 1 < len(_STAGE_ORDER):
        nxt.append(_STAGE_ORDER[idx + 1])
    nxt.append("LOST")
    return nxt


def validate_opportunity_transition(current: str, target: str, payload: dict[str, Any]) -> list[str]:
    """返回缺失的必填字段；为空表示校验通过。"""
    if target not in OPPORTUNITY_STAGES:
        return ["__invalid_target__"]
    if target != current and target not in allowed_opportunity_transitions(current):
        return ["__invalid_transition__"]
    rule = STAGE_RULES.get(target)
    if not rule:
        return []
    return [f for f in rule.required_fields if not payload.get(f)]


# ---------------------------------------------------------------- 询价状态

INQUIRY_STATUSES: list[str] = [
    "DRAFT",
    "SUBMITTED",
    "PRICING",
    "PRICED",
    "QUOTED",
    "CLOSED",
]

INQUIRY_TRANSITIONS: dict[str, list[str]] = {
    "DRAFT": ["SUBMITTED", "CLOSED"],
    "SUBMITTED": ["PRICING", "CLOSED"],
    "PRICING": ["PRICED", "CLOSED"],
    "PRICED": ["QUOTED", "CLOSED"],
    "QUOTED": ["CLOSED"],
    "CLOSED": [],
}


# ---------------------------------------------------------------- 报价状态

QUOTATION_STATUSES: list[str] = [
    "DRAFT",
    "PENDING_APPROVAL",
    "APPROVED",
    "SENT",
    "ACCEPTED",
    "REJECTED",
    "EXPIRED",
]

QUOTATION_TRANSITIONS: dict[str, list[str]] = {
    "DRAFT": ["PENDING_APPROVAL"],
    "PENDING_APPROVAL": ["APPROVED", "REJECTED", "DRAFT"],
    "APPROVED": ["SENT", "EXPIRED"],
    "SENT": ["ACCEPTED", "REJECTED", "EXPIRED"],
    "ACCEPTED": ["EXPIRED"],
    "REJECTED": ["DRAFT"],
    "EXPIRED": [],
}


def can_transition(machine: dict[str, list[str]], current: str, target: str) -> bool:
    return target in machine.get(current, [])
