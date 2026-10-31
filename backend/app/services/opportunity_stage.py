"""商机阶段流转领域逻辑（PAND-316 OPP-01~06）。

集中三件事，避免手工流转与自动推进各写一套：

1. **校验上下文** = 商机已存字段 ∪ 本次请求体 ∪ 来源单据自动带出（修 R2）。
2. **中文错误结构** = 目标/当前阶段中文名 + 缺失字段中文名 + 可流转目标（修 R3/R7）。
3. **自动推进** = 询价提交/核价审批/报价创建共用 ``auto_advance``，不回退不重复（修 R6）。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.error_codes import ErrCode
from app.core.exceptions import ApiError
from app.db.base import utcnow
from app.domain.field_labels import field_label
from app.domain.state_machine import (
    STAGE_LABELS,
    STAGE_ROLE_LABELS,
    STAGE_RULES,
    allowed_opportunity_transitions,
    opportunity_stage_index,
)
from app.models.business import Inquiry, Opportunity
from app.models.pricing import PricingRecord, Quotation
from app.models.sales import Sample
from app.models.user import User

TERMINAL_STAGES = {"WON", "LOST"}
SAMPLE_FIELD = "sample_record"
SAMPLE_FIELD_LABEL = "样品记录或关联样品单"

# 允许被写入商机的阶段字段（顺序即展示/提示顺序）
STAGE_FIELDS: tuple[str, ...] = (
    "requirement",
    "estimated_amount",
    "product_category",
    "quantity",
    "inquiry_id",
    "pricing_id",
    "quotation_amount",
    "sample_record",
    "negotiation_record",
    "won_amount",
    "lost_reason",
)


def is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def required_fields(target: str) -> list[str]:
    rule = STAGE_RULES.get(target)
    return list(rule.required_fields) if rule else []


def required_field_label(target: str, name: str) -> str:
    if target == "SAMPLE" and name == SAMPLE_FIELD:
        return SAMPLE_FIELD_LABEL
    return field_label(name)


def allowed_target_labels(current: str) -> list[str]:
    return [STAGE_LABELS.get(s, s) for s in allowed_opportunity_transitions(current)]


def current_role_label(user: User) -> str:
    codes = set(user.role_codes)
    for code in ("pricing", "manager", "admin", "sales"):
        if code in codes:
            return STAGE_ROLE_LABELS[code]
    return STAGE_ROLE_LABELS["sales"]


def role_allowed(user: User, target: str) -> bool:
    if user.is_superuser:
        return True
    codes = set(user.role_codes)
    if codes & {"admin", "manager"}:
        return True
    rule = STAGE_RULES.get(target)
    if rule is None:
        return True
    return not codes.isdisjoint(set(rule.roles))


def transition_error_data(target: str, current: str) -> dict[str, Any]:
    allowed = allowed_opportunity_transitions(current)
    return {
        "target": target,
        "target_label": STAGE_LABELS.get(target, target),
        "current": current,
        "current_label": STAGE_LABELS.get(current, current),
        "allowed_targets": allowed,
        "allowed_labels": [STAGE_LABELS.get(s, s) for s in allowed],
    }


# ------------------------------------------------------------------ 来源单据自动带出
async def _latest_submitted_inquiry(db: AsyncSession, opp_id: uuid.UUID) -> Inquiry | None:
    stmt = (
        select(Inquiry)
        .where(
            Inquiry.opportunity_id == opp_id,
            Inquiry.deleted_at.is_(None),
            Inquiry.status != "DRAFT",
        )
        .order_by(Inquiry.created_at.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _latest_approved_pricing(db: AsyncSession, opp_id: uuid.UUID) -> PricingRecord | None:
    inquiry_ids = select(Inquiry.id).where(Inquiry.opportunity_id == opp_id, Inquiry.deleted_at.is_(None))
    stmt = (
        select(PricingRecord)
        .where(
            PricingRecord.inquiry_id.in_(inquiry_ids),
            PricingRecord.deleted_at.is_(None),
            PricingRecord.status == "APPROVED",
        )
        .order_by(PricingRecord.approved_at.desc().nullslast(), PricingRecord.created_at.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _latest_approved_quotation(db: AsyncSession, opp_id: uuid.UUID) -> Quotation | None:
    stmt = (
        select(Quotation)
        .where(
            Quotation.opportunity_id == opp_id,
            Quotation.deleted_at.is_(None),
            Quotation.status.in_(("APPROVED", "SENT", "ACCEPTED")),
        )
        .order_by(Quotation.created_at.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _linked_sample_count(db: AsyncSession, opp_id: uuid.UUID) -> int:
    stmt = select(func.count()).select_from(
        select(Sample.id)
        .where(Sample.opportunity_id == opp_id, Sample.deleted_at.is_(None))
        .subquery()
    )
    return int((await db.execute(stmt)).scalar_one())


@dataclass
class FieldState:
    field: str
    label: str
    satisfied: bool
    value: Any = None
    source: str | None = None


@dataclass
class TargetState:
    stage: str
    label: str
    satisfied: bool = False
    fields: list[FieldState] = field(default_factory=list)
    missing_labels: list[str] = field(default_factory=list)
    roles: list[str] = field(default_factory=list)
    role_labels: list[str] = field(default_factory=list)
    role_allowed: bool = True


async def evaluate_target(
    db: AsyncSession, opp: Opportunity, target: str, payload: dict[str, Any]
) -> tuple[TargetState, dict[str, Any]]:
    """计算目标阶段必填项满足情况，并返回应回写的字段值。"""
    rule = STAGE_RULES.get(target)
    state = TargetState(
        stage=target,
        label=STAGE_LABELS.get(target, target),
        roles=list(rule.roles) if rule else [],
        role_labels=[STAGE_ROLE_LABELS.get(r, r) for r in (rule.roles if rule else [])],
    )
    values: dict[str, Any] = {}
    for name in required_fields(target):
        item = FieldState(field=name, label=required_field_label(target, name), satisfied=False)

        explicit = payload.get(name)
        stored = getattr(opp, name, None)
        if not is_blank(explicit):
            item.satisfied = True
            item.value = explicit
            values[name] = explicit
        elif not is_blank(stored):
            item.satisfied = True
            item.value = stored
            item.source = "沿用已保存值"
        elif name == "inquiry_id":
            inquiry = await _latest_submitted_inquiry(db, opp.id)
            if inquiry is not None:
                item.satisfied = True
                item.value = inquiry.id
                item.source = f"已自动带出：询价单 {inquiry.inquiry_no}"
                values[name] = inquiry.id
        elif name == "pricing_id":
            pricing = await _latest_approved_pricing(db, opp.id)
            if pricing is not None:
                item.satisfied = True
                item.value = pricing.id
                item.source = f"已自动带出：核价记录 v{pricing.version}"
                values[name] = pricing.id
        elif name == "quotation_amount":
            quotation = await _latest_approved_quotation(db, opp.id)
            if quotation is not None and quotation.total_amount is not None:
                item.satisfied = True
                item.value = quotation.total_amount
                item.source = f"已自动带出：报价单 {quotation.quotation_no}"
                values[name] = quotation.total_amount
        elif target == "SAMPLE" and name == SAMPLE_FIELD:
            count = await _linked_sample_count(db, opp.id)
            if count:
                item.satisfied = True
                item.source = f"已关联样品单 {count} 条"

        state.fields.append(item)
        if not item.satisfied:
            state.missing_labels.append(item.label)

    state.satisfied = not state.missing_labels
    return state, values


# ------------------------------------------------------------------ 错误构造（OPP-03）
def missing_error(target: str, current: str, missing_labels: list[str]) -> ApiError:
    data = transition_error_data(target, current)
    data["missing_fields"] = []
    data["missing_labels"] = missing_labels
    target_label = STAGE_LABELS.get(target, target)
    current_label = STAGE_LABELS.get(current, current)
    allowed = "、".join(data["allowed_labels"]) or "无"
    message = (
        f"流转至【{target_label}】失败：缺少必填项——{'、'.join(missing_labels)}。"
        f"当前阶段【{current_label}】可流转至：{allowed}。"
    )
    return ApiError(ErrCode.VALIDATION_ERROR, message, http_status=400, data=data)


def invalid_transition_error(target: str, current: str) -> ApiError:
    data = transition_error_data(target, current)
    target_label = STAGE_LABELS.get(target, target)
    current_label = STAGE_LABELS.get(current, current)
    allowed = "、".join(data["allowed_labels"]) or "无"
    message = (
        f"流转至【{target_label}】失败：不能从【{current_label}】流转到【{target_label}】。"
        f"可流转至：{allowed}。"
    )
    return ApiError(ErrCode.VALIDATION_ERROR, message, http_status=400, data=data)


def role_error(target: str, current: str, user: User) -> ApiError:
    data = transition_error_data(target, current)
    rule = STAGE_RULES.get(target)
    role_labels = [STAGE_ROLE_LABELS.get(r, r) for r in (rule.roles if rule else [])]
    data["required_roles"] = list(rule.roles) if rule else []
    data["required_role_labels"] = role_labels
    data["current_role_labels"] = [current_role_label(user)]
    target_label = STAGE_LABELS.get(target, target)
    message = (
        f"流转至【{target_label}】失败：该阶段仅限【{'、'.join(role_labels) or '授权角色'}】操作，"
        f"当前角色【{current_role_label(user)}】；可请主管代办。"
    )
    return ApiError(ErrCode.VALIDATION_ERROR, message, http_status=403, data=data)


# ------------------------------------------------------------------ 写入
def apply_transition(opp: Opportunity, target: str, values: dict[str, Any]) -> None:
    for name in STAGE_FIELDS:
        if name in values and values[name] is not None:
            setattr(opp, name, values[name])
    opp.stage = target
    opp.status = "CLOSED" if target in TERMINAL_STAGES else "OPEN"
    if target == "WON":
        opp.probability = 100
    opp.last_followup_at = utcnow()


def auto_advance(
    opp: Opportunity,
    target: str,
    *,
    from_stages: set[str],
    values: dict[str, Any],
) -> bool:
    """来源单据驱动的自动推进：只在指定前序阶段生效，不回退、不重复。"""
    if opp.stage in TERMINAL_STAGES or opp.stage not in from_stages:
        return False
    if opportunity_stage_index(target) <= opportunity_stage_index(opp.stage):
        return False
    for name, value in values.items():
        if value is not None:
            setattr(opp, name, value)
    opp.stage = target
    opp.status = "OPEN"
    opp.last_followup_at = utcnow()
    return True
