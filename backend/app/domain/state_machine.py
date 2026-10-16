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


# ---------------------------------------------------------------- 销售中心 6 模块（PAND-249，契约冻结取值域）

# 客户三分类字典（AC-M1.2）
CUSTOMER_LEVELS: list[str] = ["A级（核心大客户）", "B级（普通大客户）", "C级（中小客户）", "D级（新客/休眠客）"]
SALES_MODES: list[str] = ["外销", "内销", "外贸公司"]
CUSTOMER_STATUSES: list[str] = ["大货合作客户", "样品单客户", "潜在客户", "未合作休眠客户"]

# 询价证书（AC-M2.3，与报价库证书字典独立）
CERTIFICATE_COMPLIANT: list[str] = ["是", "否"]
INQUIRY_CERTIFICATE_LEVELS: list[str] = ["国标", "行标", "企标", "无证书"]

# 报价库证书等级（AC-M3.3）
QUOTE_LIBRARY_CERTIFICATE_LEVELS: list[str] = ["CE", "ROHS", "CCC", "UL", "ETL"]

# 询价 11 态（AC-M2.7，对齐 EBMS）
INQUIRY_STATUSES_V2: list[str] = [
    "new",
    "cert_configured",
    "config_generated",
    "pending_pricing",
    "pending_quote",
    "quoted",
    "negotiating",
    "sample",
    "project",
    "lost",
    "closed",
]

# 旧 6 态 -> 11 态迁移映射（PAND-247 5.5 / 契约 §6）
INQUIRY_STATUS_MIGRATION: dict[str, str] = {
    "DRAFT": "new",
    "SUBMITTED": "config_generated",
    "PRICING": "pending_pricing",
    "PRICED": "pending_quote",
    "QUOTED": "quoted",
    "CLOSED": "closed",
}

INQUIRY_TRANSITIONS_V2: dict[str, list[str]] = {
    "new": ["cert_configured"],
    "cert_configured": ["config_generated"],
    "config_generated": ["pending_pricing"],
    "pending_pricing": ["pending_quote"],
    "pending_quote": ["quoted"],
    "quoted": ["negotiating", "sample", "lost", "closed"],
    "negotiating": ["sample", "project", "lost", "closed"],
    "sample": ["project", "lost", "closed"],
    "project": ["lost", "closed"],
    "lost": [],
    "closed": [],
}

# 订单（AC-M4.3）
ORDER_STATUSES: list[str] = [
    "open",
    "confirmed",
    "procurement_ready",
    "material_ready",
    "packaging_done",
    "shipped",
    "completed",
    "closed",
    "cancelled",
]
ORDER_PROGRESSION: list[str] = [
    "open",
    "confirmed",
    "procurement_ready",
    "material_ready",
    "packaging_done",
    "shipped",
    "completed",
]
ORDER_TERMINAL: set[str] = {"completed", "closed", "cancelled"}
# 风险等级：默认 blue；表单 low/medium/high，过滤 blue/yellow/red（契约 §4.2 双轨）
ORDER_RISK_FORM: list[str] = ["low", "medium", "high"]
ORDER_RISK_FILTER: list[str] = ["blue", "yellow", "red"]
# 外部状态 -> 本地状态映射（AC-M4.4）
EXTERNAL_ORDER_STATUS_MAP: dict[str, str] = {"completed": "shipped", "closed": "completed"}

# 样品（AC-M5.3）
SAMPLE_STATUSES: list[str] = ["pending", "confirmed", "producing", "sent", "customer_confirmed", "completed"]

# 问题反馈（AC-M6.1 / AC-M6.3）
FEEDBACK_TYPES: list[str] = ["bug", "feature", "improvement", "question"]
FEEDBACK_PRIORITIES: list[str] = ["low", "medium", "high", "urgent"]
FEEDBACK_STATUSES: list[str] = ["open", "processing", "resolved", "closed"]
FEEDBACK_FOLLOWUP_ACTIONS: list[str] = ["submit", "comment", "status", "assign", "resolve", "close"]

# 同步状态（契约 §4.2）
SYNC_STATUSES: list[str] = ["PENDING", "SYNCING", "SYNCED", "CONFLICT"]


def allowed_order_transitions(current: str) -> list[str]:
    """订单正向推进链（closed/cancelled 需显式选择，终态无后续）。"""
    if current in ORDER_TERMINAL or current not in ORDER_PROGRESSION:
        return []
    idx = ORDER_PROGRESSION.index(current)
    nxt = [ORDER_PROGRESSION[idx + 1]] if idx + 1 < len(ORDER_PROGRESSION) else []
    return nxt + ["closed", "cancelled"]
