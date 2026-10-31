"""M4 核价接口：创建（含版本）/ 计算 / 版本列表 / 提交 / 审批 / 规则。"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.api.crud import CrudConfig, build_crud_router
from app.core import response as resp
from app.core.deps import DbSession, require_permission
from app.core.exceptions import ApiError, NotFoundError
from app.db.base import utcnow
from app.models.business import Company, Inquiry, Opportunity
from app.models.pricing import PricingRecord, PricingRule
from app.models.user import User
from app.schemas.pricing import (
    PricingApproveIn,
    PricingCalcIn,
    PricingCalcOut,
    PricingCreate,
    PricingOut,
    PricingRuleCreate,
    PricingRuleOut,
    PricingRuleUpdate,
    PricingUpdate,
)
from app.services import approval as approval_service
from app.services import pricing as pricing_service
from app.services.data_scope import apply_data_scope
from app.services.query import apply_sort, get_or_404, paginate

router = APIRouter(prefix="/pricing", tags=["M4-核价"])

COST_FIELDS = pricing_service.COST_FIELDS


def _mask(user: User, row: PricingRecord) -> dict[str, Any]:
    data = PricingOut.model_validate(row).model_dump(mode="json")
    can_cost = user.is_superuser or "pricing:cost_view" in user.permission_codes
    can_floor = user.is_superuser or "pricing:floor_view" in user.permission_codes
    if not can_cost:
        for field in (*COST_FIELDS, "total_cost", "base_cost"):
            data[field] = None
    if not can_floor:
        data["floor_price"] = None
    data["can_view_cost"] = can_cost
    data["can_view_floor"] = can_floor
    return data


async def _load_rules(db: DbSession) -> list[PricingRule]:
    return list(
        (await db.execute(select(PricingRule).where(PricingRule.deleted_at.is_(None), PricingRule.enabled.is_(True))))
        .scalars()
        .all()
    )


async def _calc_and_store(db: DbSession, record: PricingRecord, inquiry: Inquiry) -> None:
    costs = {f: getattr(record, f) for f in COST_FIELDS}
    qty = 1.0
    if inquiry.items:
        qty = float(sum(float(i.quantity or 0) for i in inquiry.items) or 1)
    rules = await _load_rules(db)
    company = (await db.execute(select(Company).where(Company.id == inquiry.company_id))).scalar_one_or_none()
    context = {
        "quantity": qty,
        "customer_level": company.customer_level if company else None,
        "country": company.country if company else None,
        "currency": record.currency,
    }
    result = pricing_service.calculate(
        costs=costs,
        quantity=qty,
        profit_rate=float(record.target_margin or pricing_service.DEFAULT_PROFIT_RATE),
        rules=rules,
        context=context,
        discount_rate=float(record.discount_rate or 1),
    )
    record.total_cost = result["total_cost"]
    record.base_cost = result["base_cost"]
    record.floor_price = result["floor_price"]
    record.suggested_price = result["suggested_price"]
    record.final_price = result["final_price"]
    record.target_margin = result["target_margin"]
    record.discount_rate = result["discount_rate"]
    record.remark = (
        f"{record.remark or ''}\n命中规则: {', '.join(result['applied_rules'])}".strip()
        if result["applied_rules"]
        else record.remark
    )


@router.get("", summary="核价记录列表")
async def list_pricing(
    db: DbSession,
    current: User = Depends(require_permission("pricing:view")),
    status: str | None = None,
    inquiry_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    sort: str = "created_at",
    order: str = Query("desc", pattern="^(asc|desc)$"),
) -> dict[str, Any]:
    stmt = select(PricingRecord).where(PricingRecord.deleted_at.is_(None))
    if status:
        stmt = stmt.where(PricingRecord.status == status)
    if inquiry_id:
        stmt = stmt.where(PricingRecord.inquiry_id == inquiry_id)
    stmt = await apply_data_scope(stmt, PricingRecord, current, db)

    stmt = apply_sort(stmt, PricingRecord, sort, order)
    rows, total = await paginate(db, stmt, page, page_size)

    inquiry_ids = {r.inquiry_id for r in rows}
    meta: dict[uuid.UUID, tuple[str, str]] = {}
    if inquiry_ids:
        found = (
            await db.execute(
                select(Inquiry.id, Inquiry.inquiry_no, Company.name)
                .join(Company, Company.id == Inquiry.company_id, isouter=True)
                .where(Inquiry.id.in_(inquiry_ids))
            )
        ).all()
        meta = {r[0]: (r[1], r[2]) for r in found}

    items = []
    for row in rows:
        data = _mask(current, row)
        inquiry_no, company_name = meta.get(row.inquiry_id, (None, None))
        data["inquiry_no"] = inquiry_no
        data["company_name"] = company_name
        items.append(data)
    return resp.page(items, total, page, page_size)


@router.post("/calc", summary="核价试算（不落库）")
async def calc(payload: PricingCalcIn, _: User = Depends(require_permission("pricing:view"))) -> dict[str, Any]:
    result = pricing_service.calculate(
        costs=payload.model_dump(),
        quantity=payload.quantity,
        profit_rate=payload.target_margin,
        discount_rate=payload.discount_rate,
        exchange_rate=payload.exchange_rate,
    )
    result.pop("applied_rules", None)
    return resp.ok(PricingCalcOut(**result).model_dump(mode="json"))


@router.post("", summary="创建核价记录（自动版本号）", status_code=201)
async def create_pricing(
    payload: PricingCreate,
    db: DbSession,
    current: User = Depends(require_permission("pricing:create")),
) -> dict[str, Any]:
    inquiry = await get_or_404(db, Inquiry, payload.inquiry_id, "询价单")
    if inquiry.status == "CLOSED":
        raise ApiError(message="已关闭的询价单不可核价", http_status=400)

    max_version = (
        await db.execute(
            select(func.coalesce(func.max(PricingRecord.version), 0)).where(
                PricingRecord.inquiry_id == inquiry.id, PricingRecord.deleted_at.is_(None)
            )
        )
    ).scalar_one()

    record = PricingRecord(
        inquiry_id=inquiry.id,
        version=int(max_version) + 1,
        status="DRAFT",
        currency=payload.currency,
        target_margin=payload.target_margin,
        discount_rate=payload.discount_rate,
        remark=payload.remark,
        created_by=current.id,
        owner_id=current.id,
        department_id=current.department_id,
    )
    for field, value in payload.costs.model_dump().items():
        setattr(record, field, value)
    db.add(record)
    await db.flush()
    await _calc_and_store(db, record, inquiry)

    if inquiry.status == "SUBMITTED":
        inquiry.status = "PRICING"
    await db.commit()
    await db.refresh(record)
    data = _mask(current, record)
    data["inquiry_no"] = inquiry.inquiry_no
    return resp.ok(data)


@router.get("/{pricing_id}", summary="核价详情")
async def get_pricing(
    pricing_id: uuid.UUID,
    db: DbSession,
    current: User = Depends(require_permission("pricing:view")),
) -> dict[str, Any]:
    record = await get_or_404(db, PricingRecord, pricing_id, "核价记录")
    inquiry = (await db.execute(select(Inquiry).where(Inquiry.id == record.inquiry_id))).scalar_one_or_none()
    data = _mask(current, record)
    if inquiry is not None:
        data["inquiry_no"] = inquiry.inquiry_no
        company = (await db.execute(select(Company.name).where(Company.id == inquiry.company_id))).scalar_one_or_none()
        data["company_name"] = company
    return resp.ok(data)


@router.put("/{pricing_id}", summary="更新核价（仅草稿）")
async def update_pricing(
    pricing_id: uuid.UUID,
    payload: PricingUpdate,
    db: DbSession,
    current: User = Depends(require_permission("pricing:create")),
) -> dict[str, Any]:
    record = await get_or_404(db, PricingRecord, pricing_id, "核价记录")
    if record.status != "DRAFT":
        raise ApiError(message="仅草稿状态的核价可修改（版本不覆盖）", http_status=400)
    data = payload.model_dump(exclude_unset=True)
    costs = data.pop("costs", None)
    for key, value in data.items():
        setattr(record, key, value)
    if costs:
        for field, value in costs.items():
            setattr(record, field, value)
    inquiry = (await db.execute(select(Inquiry).where(Inquiry.id == record.inquiry_id))).scalar_one_or_none()
    if inquiry is not None:
        await _calc_and_store(db, record, inquiry)
    await db.commit()
    await db.refresh(record)
    return resp.ok(_mask(current, record))


async def _apply_pricing_approved(db: DbSession, record: PricingRecord, current: User) -> None:
    """核价通过（免审直批或审批通过）后的单据副作用：询价转已核价、商机转核价阶段。"""
    record.status = "APPROVED"
    record.approved_by = current.id
    record.approved_at = utcnow()
    inquiry = (await db.execute(select(Inquiry).where(Inquiry.id == record.inquiry_id))).scalar_one_or_none()
    if inquiry is not None:
        inquiry.status = "PRICED"
        if inquiry.opportunity_id:
            opp = (
                await db.execute(select(Opportunity).where(Opportunity.id == inquiry.opportunity_id))
            ).scalar_one_or_none()
            if opp is not None and opp.stage in {"INQUIRY", "REQUIREMENT"}:
                opp.stage = "PRICING"
                opp.pricing_id = record.id


@router.post("/{pricing_id}/submit", summary="提交核价审批")
async def submit_pricing(
    pricing_id: uuid.UUID,
    db: DbSession,
    current: User = Depends(require_permission("pricing:submit")),
) -> dict[str, Any]:
    record = await get_or_404(db, PricingRecord, pricing_id, "核价记录")
    if record.status != "DRAFT":
        raise ApiError(message=f"当前状态 {record.status} 不可提交", http_status=400)
    inquiry = await get_or_404(db, Inquiry, record.inquiry_id, "询价单")

    amount_threshold_enabled, amount_threshold = await approval_service.load_amount_threshold(db)
    amount = float(record.total_cost or 0)
    steps = approval_service.steps_for(
        "PRICING",
        record.discount_rate,
        amount,
        amount_threshold_enabled=amount_threshold_enabled,
        amount_threshold=amount_threshold,
    )
    if not steps:
        # M2.6-D1：折扣率 =1 免审，直接放行。
        await _apply_pricing_approved(db, record, current)
        await db.commit()
        await db.refresh(record)
        data = _mask(current, record)
        data["approval_status"] = "APPROVED"
        data["approval_step"] = "免审"
        return resp.ok(data)

    instance = await approval_service.start(
        db,
        biz_type="PRICING",
        biz_id=record.id,
        biz_no=f"{inquiry.inquiry_no}-V{record.version}",
        title=f"核价审批 {inquiry.inquiry_no} V{record.version}",
        amount=amount,
        currency=record.currency,
        applicant=current,
        discount_rate=record.discount_rate,
        amount_threshold_enabled=amount_threshold_enabled,
        amount_threshold=amount_threshold,
    )
    record.status = "PENDING_APPROVAL"
    await db.commit()
    await db.refresh(record)
    data = _mask(current, record)
    data["approval_id"] = str(instance.id)
    return resp.ok(data)


@router.post("/{pricing_id}/approve", summary="审批核价")
async def approve_pricing(
    pricing_id: uuid.UUID,
    payload: PricingApproveIn,
    db: DbSession,
    current: User = Depends(require_permission("pricing:approve")),
) -> dict[str, Any]:
    record = await get_or_404(db, PricingRecord, pricing_id, "核价记录")
    if record.status != "PENDING_APPROVAL":
        raise ApiError(message=f"当前状态 {record.status} 不可审批", http_status=400)

    instance = await approval_service.latest_for_biz(db, "PRICING", record.id)
    if instance is None:
        raise NotFoundError("核价审批实例不存在")

    instance = await approval_service.act(
        db, instance_id=instance.id, user=current, approved=payload.approved, comment=payload.comment
    )

    if instance.status == "APPROVED":
        await _apply_pricing_approved(db, record, current)
    elif instance.status == "REJECTED":
        record.status = "DRAFT"

    await db.commit()
    await db.refresh(record)
    data = _mask(current, record)
    data["approval_status"] = instance.status
    return resp.ok(data)


# ------------------------------------------------------------------ 核价规则
rules_router = build_crud_router(
    CrudConfig(
        model=PricingRule,
        prefix="/pricing-rules",
        tag="M4-核价规则",
        name="核价规则",
        create_schema=PricingRuleCreate,
        update_schema=PricingRuleUpdate,
        out_schema=PricingRuleOut,
        view_permission="pricing:view",
        create_permission="pricing:submit",
        update_permission="pricing:submit",
        delete_permission="pricing:submit",
        search_fields=("name", "code"),
        scope=False,
        description="JSON 条件 + 动作的核价规则引擎（P1）",
    )
)
