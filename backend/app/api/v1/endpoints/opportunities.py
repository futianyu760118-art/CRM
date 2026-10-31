"""M3 商机接口：CRUD + 阶段流转 + 阶段目录（状态机）。"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select

from app.core import response as resp
from app.core.deps import DbSession, require_permission
from app.core.error_codes import ErrCode
from app.core.exceptions import ApiError, ForbiddenError, NotFoundError
from app.domain.state_machine import (
    OPPORTUNITY_STAGES,
    STAGE_LABELS,
    STAGE_RULES,
    allowed_opportunity_transitions,
)
from app.models.business import Company, Opportunity
from app.models.user import User
from app.schemas.business import (
    OpportunityCreate,
    OpportunityOut,
    OpportunityStageIn,
    OpportunityUpdate,
    StageCatalogOut,
)
from app.services import opportunity_stage
from app.services.data_scope import apply_data_scope, get_user_scope
from app.services.number_sequence import next_number
from app.services.query import apply_sort, get_or_404, paginate, soft_delete

router = APIRouter(prefix="/opportunities", tags=["M3-商机"])


async def _to_out(db: DbSession, opp: Opportunity) -> dict[str, Any]:
    data = OpportunityOut.model_validate(opp).model_dump(mode="json")
    company = (await db.execute(select(Company.name).where(Company.id == opp.company_id))).scalar_one_or_none()
    data["company_name"] = company
    data["stage_label"] = STAGE_LABELS.get(opp.stage, opp.stage)
    return data


@router.get("/stages", summary="商机阶段目录（状态机定义）")
async def stage_catalog(_: User = Depends(require_permission("opportunity:view"))) -> dict[str, Any]:
    catalog = []
    for stage in OPPORTUNITY_STAGES:
        rule = STAGE_RULES.get(stage)
        catalog.append(
            StageCatalogOut(
                value=stage,
                label=STAGE_LABELS.get(stage, stage),
                next_stages=allowed_opportunity_transitions(stage),
                required_fields=rule.required_fields if rule else [],
                required_field_labels=[
                    opportunity_stage.required_field_label(stage, name)
                    for name in (rule.required_fields if rule else [])
                ],
                roles=rule.roles if rule else [],
            ).model_dump(mode="json")
        )
    return resp.ok(catalog)


@router.get("", summary="商机列表")
async def list_opportunities(
    db: DbSession,
    current: User = Depends(require_permission("opportunity:view")),
    keyword: str | None = None,
    stage: str | None = None,
    company_id: uuid.UUID | None = None,
    owner_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    sort: str = "created_at",
    order: str = Query("desc", pattern="^(asc|desc)$"),
) -> dict[str, Any]:
    stmt = select(Opportunity).where(Opportunity.deleted_at.is_(None))
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(or_(Opportunity.name.ilike(like), Opportunity.opportunity_no.ilike(like)))
    if stage:
        stmt = stmt.where(Opportunity.stage == stage)
    if company_id:
        stmt = stmt.where(Opportunity.company_id == company_id)
    if owner_id:
        stmt = stmt.where(Opportunity.owner_id == owner_id)
    stmt = await apply_data_scope(stmt, Opportunity, current, db)

    stmt = apply_sort(stmt, Opportunity, sort, order)
    rows, total = await paginate(db, stmt, page, page_size)

    company_ids = {r.company_id for r in rows}
    names: dict[uuid.UUID, str] = {}
    if company_ids:
        found = (await db.execute(select(Company.id, Company.name).where(Company.id.in_(company_ids)))).all()
        names = {c[0]: c[1] for c in found}

    items = []
    for row in rows:
        data = OpportunityOut.model_validate(row).model_dump(mode="json")
        data["company_name"] = names.get(row.company_id)
        data["stage_label"] = STAGE_LABELS.get(row.stage, row.stage)
        items.append(data)
    return resp.page(items, total, page, page_size)


@router.get("/kanban", summary="商机看板（按阶段分组）")
async def kanban(
    db: DbSession,
    current: User = Depends(require_permission("opportunity:view")),
) -> dict[str, Any]:
    stmt = select(Opportunity).where(Opportunity.deleted_at.is_(None))
    stmt = await apply_data_scope(stmt, Opportunity, current, db)
    rows = (await db.execute(stmt.order_by(Opportunity.created_at.desc()))).scalars().all()

    company_ids = {r.company_id for r in rows}
    names: dict[uuid.UUID, str] = {}
    if company_ids:
        found = (await db.execute(select(Company.id, Company.name).where(Company.id.in_(company_ids)))).all()
        names = {c[0]: c[1] for c in found}

    columns: list[dict[str, Any]] = []
    for stage in OPPORTUNITY_STAGES:
        cards = []
        amount = 0.0
        for row in rows:
            if row.stage != stage:
                continue
            amount += float(row.estimated_amount or 0)
            cards.append(
                {
                    "id": str(row.id),
                    "opportunity_no": row.opportunity_no,
                    "name": row.name,
                    "company_name": names.get(row.company_id),
                    "estimated_amount": float(row.estimated_amount or 0),
                    "currency": row.currency,
                    "owner_id": str(row.owner_id) if row.owner_id else None,
                    "probability": row.probability,
                }
            )
        columns.append(
            {
                "stage": stage,
                "label": STAGE_LABELS.get(stage, stage),
                "count": len(cards),
                "amount": round(amount, 2),
                "cards": cards,
            }
        )
    return resp.ok({"columns": columns})


@router.post("", summary="新建商机", status_code=201)
async def create_opportunity(
    payload: OpportunityCreate,
    db: DbSession,
    current: User = Depends(require_permission("opportunity:create")),
) -> dict[str, Any]:
    company = (
        await db.execute(select(Company).where(Company.id == payload.company_id, Company.deleted_at.is_(None)))
    ).scalar_one_or_none()
    if company is None:
        raise NotFoundError("客户不存在")

    opp = Opportunity(
        **payload.model_dump(exclude_unset=True),
        opportunity_no=await next_number("opportunity"),
        stage="NEW",
        owner_id=payload.owner_id or current.id,
        department_id=current.department_id,
    )
    db.add(opp)
    await db.commit()
    await db.refresh(opp)
    return resp.ok(await _to_out(db, opp))


@router.get("/{opp_id}", summary="商机详情")
async def get_opportunity(
    opp_id: uuid.UUID,
    db: DbSession,
    current: User = Depends(require_permission("opportunity:view")),
) -> dict[str, Any]:
    opp = await get_or_404(db, Opportunity, opp_id, "商机")
    scope_type, dept_ids = await get_user_scope(current, db)
    if scope_type != "ALL" and opp.owner_id != current.id and opp.department_id not in dept_ids:
        raise ForbiddenError("无权访问该商机")
    return resp.ok(await _to_out(db, opp))


@router.put("/{opp_id}", summary="更新商机")
async def update_opportunity(
    opp_id: uuid.UUID,
    payload: OpportunityUpdate,
    db: DbSession,
    _: User = Depends(require_permission("opportunity:update")),
) -> dict[str, Any]:
    opp = await get_or_404(db, Opportunity, opp_id, "商机")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(opp, key, value)
    await db.commit()
    await db.refresh(opp)
    return resp.ok(await _to_out(db, opp))


@router.delete("/{opp_id}", summary="删除商机（软删除）")
async def delete_opportunity(
    opp_id: uuid.UUID,
    db: DbSession,
    _: User = Depends(require_permission("opportunity:delete")),
) -> dict[str, Any]:
    opp = await get_or_404(db, Opportunity, opp_id, "商机")
    soft_delete(opp)
    await db.commit()
    return resp.ok({"deleted": True})


@router.get("/{opp_id}/transitions", summary="可流转目标与必填项预检")
async def list_transitions(
    opp_id: uuid.UUID,
    db: DbSession,
    current: User = Depends(require_permission("opportunity:view")),
) -> dict[str, Any]:
    opp = await get_or_404(db, Opportunity, opp_id, "商机")
    scope_type, dept_ids = await get_user_scope(current, db)
    if scope_type != "ALL" and opp.owner_id != current.id and opp.department_id not in dept_ids:
        raise ForbiddenError("无权访问该商机")

    targets = []
    for stage in allowed_opportunity_transitions(opp.stage):
        state, _ = await opportunity_stage.evaluate_target(db, opp, stage, {})
        targets.append(
            {
                "stage": state.stage,
                "label": state.label,
                "satisfied": state.satisfied,
                "required": [
                    {
                        "field": item.field,
                        "label": item.label,
                        "satisfied": item.satisfied,
                        "source": item.source,
                    }
                    for item in state.fields
                ],
                "missing_labels": state.missing_labels,
                "roles": state.role_labels,
                "role_allowed": opportunity_stage.role_allowed(current, stage),
            }
        )
    return resp.ok(
        {
            "current": opp.stage,
            "current_label": STAGE_LABELS.get(opp.stage, opp.stage),
            "targets": targets,
        }
    )


@router.patch("/{opp_id}/stage", summary="变更商机阶段")
async def change_stage(
    opp_id: uuid.UUID,
    payload: OpportunityStageIn,
    db: DbSession,
    current: User = Depends(require_permission("opportunity:stage")),
) -> dict[str, Any]:
    opp = await get_or_404(db, Opportunity, opp_id, "商机")
    target = payload.stage

    if target not in STAGE_RULES:
        raise ApiError(ErrCode.VALIDATION_ERROR, f"未知阶段：{target}", http_status=400)
    if target not in allowed_opportunity_transitions(opp.stage):
        raise opportunity_stage.invalid_transition_error(target, opp.stage)
    if not opportunity_stage.role_allowed(current, target):
        raise opportunity_stage.role_error(target, opp.stage, current)

    context = payload.model_dump(exclude_unset=True)
    state, values = await opportunity_stage.evaluate_target(db, opp, target, context)
    if not state.satisfied:
        raise opportunity_stage.missing_error(target, opp.stage, state.missing_labels)

    merged = {
        name: value
        for name, value in context.items()
        if name in opportunity_stage.STAGE_FIELDS and value is not None
    }
    merged.update(values)
    opportunity_stage.apply_transition(opp, target, merged)
    await db.commit()
    await db.refresh(opp)
    return resp.ok(await _to_out(db, opp))
