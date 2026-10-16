"""M3 询价接口：CRUD + 明细 + 提交 + 核价版本。"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm.attributes import set_committed_value

from app.core import response as resp
from app.core.deps import DbSession, require_permission
from app.core.exceptions import ApiError, ForbiddenError, NotFoundError
from app.domain.state_machine import INQUIRY_TRANSITIONS
from app.models.business import Company, Contact, Inquiry, InquiryItem, Opportunity
from app.models.pricing import PricingRecord
from app.models.support import SystemConfig
from app.models.user import Department, User
from app.schemas.business import (
    InquiryCreate,
    InquiryOut,
    InquiryUpdate,
)
from app.schemas.pricing import PricingOut
from app.services import ebms_sync, export_excel
from app.services.data_scope import apply_data_scope, get_user_scope
from app.services.number_sequence import next_number
from app.services.query import apply_sort, get_or_404, paginate, soft_delete

router = APIRouter(prefix="/inquiries", tags=["M3-询价"])


async def _load_items(db: DbSession, inquiry: Inquiry) -> list[InquiryItem]:
    """显式加载明细并写回关系属性，避免异步上下文隐式懒加载。"""
    rows = list(
        (
            await db.execute(
                select(InquiryItem)
                .where(InquiryItem.inquiry_id == inquiry.id, InquiryItem.deleted_at.is_(None))
                .order_by(InquiryItem.sort, InquiryItem.created_at)
            )
        )
        .scalars()
        .all()
    )
    set_committed_value(inquiry, "items", rows)
    return rows


async def _serialize(db: DbSession, inquiry: Inquiry, *, with_items: bool = True) -> dict[str, Any]:
    if with_items:
        await _load_items(db, inquiry)
    else:
        set_committed_value(inquiry, "items", [])
    data = InquiryOut.model_validate(inquiry).model_dump(mode="json")
    if not with_items:
        data.pop("items", None)
    company = (await db.execute(select(Company.name).where(Company.id == inquiry.company_id))).scalar_one_or_none()
    data["company_name"] = company
    if not data.get("customer_name"):
        data["customer_name"] = company
    if inquiry.contact_id:
        contact = (await db.execute(select(Contact.name).where(Contact.id == inquiry.contact_id))).scalar_one_or_none()
        data["contact_name"] = contact
    if inquiry.owner_id:
        owner = (await db.execute(select(User.name).where(User.id == inquiry.owner_id))).scalar_one_or_none()
        data["owner_name"] = owner
    if inquiry.department_id:
        dept = (
            await db.execute(select(Department.name).where(Department.id == inquiry.department_id))
        ).scalar_one_or_none()
        data["department_name"] = dept
    versions = (
        await db.execute(
            select(func.count())
            .select_from(PricingRecord)
            .where(PricingRecord.inquiry_id == inquiry.id, PricingRecord.deleted_at.is_(None))
        )
    ).scalar_one()
    data["pricing_versions"] = int(versions)
    return data


async def _replace_items(db: DbSession, inquiry_id: uuid.UUID, items: list[Any]) -> None:
    await db.execute(delete(InquiryItem).where(InquiryItem.inquiry_id == inquiry_id))
    for item in items:
        db.add(InquiryItem(inquiry_id=inquiry_id, **item.model_dump(exclude_unset=True)))
    await db.flush()


@router.get("", summary="询价列表")
async def list_inquiries(
    db: DbSession,
    current: User = Depends(require_permission("inquiry:view")),
    keyword: str | None = None,
    status: str | None = None,
    company_id: uuid.UUID | None = None,
    opportunity_id: uuid.UUID | None = None,
    owner_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    sort: str = "created_at",
    order: str = Query("desc", pattern="^(asc|desc)$"),
) -> dict[str, Any]:
    stmt = select(Inquiry).where(Inquiry.deleted_at.is_(None))
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(or_(Inquiry.inquiry_no.ilike(like), Inquiry.requirement_text.ilike(like)))
    if status:
        stmt = stmt.where(Inquiry.status == status)
    if company_id:
        stmt = stmt.where(Inquiry.company_id == company_id)
    if opportunity_id:
        stmt = stmt.where(Inquiry.opportunity_id == opportunity_id)
    if owner_id:
        stmt = stmt.where(Inquiry.owner_id == owner_id)
    stmt = await apply_data_scope(stmt, Inquiry, current, db)

    stmt = apply_sort(stmt, Inquiry, sort, order)
    rows, total = await paginate(db, stmt, page, page_size)

    company_ids = {r.company_id for r in rows}
    names: dict[uuid.UUID, str] = {}
    if company_ids:
        found = (await db.execute(select(Company.id, Company.name).where(Company.id.in_(company_ids)))).all()
        names = {c[0]: c[1] for c in found}

    items = []
    for row in rows:
        data = InquiryOut.model_validate(row).model_dump(mode="json")
        data["company_name"] = names.get(row.company_id)
        data.pop("items", None)
        items.append(data)
    return resp.page(items, total, page, page_size)


@router.post("", summary="创建询价单", status_code=201)
async def create_inquiry(
    payload: InquiryCreate,
    db: DbSession,
    current: User = Depends(require_permission("inquiry:create")),
) -> dict[str, Any]:
    company = None
    if payload.company_id is not None:
        company = (
            await db.execute(select(Company).where(Company.id == payload.company_id, Company.deleted_at.is_(None)))
        ).scalar_one_or_none()
        if company is None:
            raise NotFoundError("客户不存在")

    data = payload.model_dump(exclude_unset=True)
    items = data.pop("items", [])
    if company is not None:
        data.setdefault("customer_code", company.code)
        data.setdefault("customer_name", company.name)
    inquiry = Inquiry(
        **data,
        inquiry_no=await next_number("inquiry"),
        status="DRAFT",
        owner_id=payload.owner_id or current.id,
        department_id=current.department_id,
    )
    db.add(inquiry)
    await db.flush()
    for item in items:
        db.add(InquiryItem(inquiry_id=inquiry.id, **item))
    await db.flush()
    await _trim_items_total(db, inquiry)
    await ebms_sync.emit_upsert(db, "inquiry", inquiry)
    await db.commit()
    await db.refresh(inquiry)
    return resp.ok(await _serialize(db, inquiry))


async def _trim_items_total(db: DbSession, inquiry: Inquiry) -> None:
    """若未填单据头数量，则用明细数量合计回填。"""
    if inquiry.quantity_total:
        return
    total = (
        await db.execute(
            select(func.coalesce(func.sum(InquiryItem.quantity), 0)).where(
                InquiryItem.inquiry_id == inquiry.id, InquiryItem.deleted_at.is_(None)
            )
        )
    ).scalar_one()
    if total:
        inquiry.quantity_total = total


@router.get("/{inquiry_id}", summary="询价详情")
async def get_inquiry(
    inquiry_id: uuid.UUID,
    db: DbSession,
    current: User = Depends(require_permission("inquiry:view")),
) -> dict[str, Any]:
    inquiry = await get_or_404(db, Inquiry, inquiry_id, "询价单")
    scope_type, dept_ids = await get_user_scope(current, db)
    if scope_type != "ALL" and inquiry.owner_id != current.id and inquiry.department_id not in dept_ids:
        raise ForbiddenError("无权访问该询价单")
    return resp.ok(await _serialize(db, inquiry))


@router.put("/{inquiry_id}", summary="更新询价单")
async def update_inquiry(
    inquiry_id: uuid.UUID,
    payload: InquiryUpdate,
    db: DbSession,
    _: User = Depends(require_permission("inquiry:update")),
) -> dict[str, Any]:
    inquiry = await get_or_404(db, Inquiry, inquiry_id, "询价单")
    if inquiry.status not in {"DRAFT", "SUBMITTED"}:
        raise ApiError(message=f"当前状态 {inquiry.status} 不允许修改", http_status=400)
    data = payload.model_dump(exclude_unset=True)
    items = data.pop("items", None)
    for key, value in data.items():
        setattr(inquiry, key, value)
    if items is not None:
        from app.schemas.business import InquiryItemIn

        await _replace_items(db, inquiry.id, [InquiryItemIn(**i) for i in items])
    await ebms_sync.emit_upsert(db, "inquiry", inquiry)
    await db.commit()
    await db.refresh(inquiry)
    return resp.ok(await _serialize(db, inquiry))


@router.post("/{inquiry_id}/submit", summary="提交询价")
async def submit_inquiry(
    inquiry_id: uuid.UUID,
    db: DbSession,
    _: User = Depends(require_permission("inquiry:submit")),
) -> dict[str, Any]:
    inquiry = await get_or_404(db, Inquiry, inquiry_id, "询价单")
    if "SUBMITTED" not in INQUIRY_TRANSITIONS.get(inquiry.status, []):
        raise ApiError(message=f"当前状态 {inquiry.status} 不可提交", http_status=400)
    if not inquiry.items:
        raise ApiError(message="询价单至少需要一条明细", http_status=400)

    inquiry.status = "SUBMITTED"
    if inquiry.opportunity_id:
        opp = (
            await db.execute(select(Opportunity).where(Opportunity.id == inquiry.opportunity_id))
        ).scalar_one_or_none()
        if opp is not None and opp.stage in {"REQUIREMENT", "NEW", "QUALIFIED"}:
            opp.stage = "INQUIRY"
            opp.inquiry_id = inquiry.id
    await ebms_sync.emit_upsert(db, "inquiry", inquiry)
    await db.commit()
    await db.refresh(inquiry)
    return resp.ok(await _serialize(db, inquiry))


@router.delete("/{inquiry_id}", summary="删除询价单（软删除）")
async def delete_inquiry(
    inquiry_id: uuid.UUID,
    db: DbSession,
    _: User = Depends(require_permission("inquiry:delete")),
) -> dict[str, Any]:
    inquiry = await get_or_404(db, Inquiry, inquiry_id, "询价单")
    soft_delete(inquiry)
    await db.flush()
    await ebms_sync.emit_delete(db, "inquiry", inquiry)
    await db.commit()
    return resp.ok({"deleted": True})


@router.get("/{inquiry_id}/export-excel", summary="导出询价单 Excel")
async def export_inquiry_excel(
    inquiry_id: uuid.UUID,
    db: DbSession,
    _: User = Depends(require_permission("inquiry:view")),
) -> Response:
    inquiry = await get_or_404(db, Inquiry, inquiry_id, "询价单")
    config = (await db.execute(select(SystemConfig).where(SystemConfig.key == "company.name"))).scalars().first()
    data = await export_excel.build_inquiry_workbook(
        db, inquiry, company_title=config.value if config and config.value else "客户询价单"
    )
    filename = f"{inquiry.inquiry_no}.xlsx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{inquiry_id}/pricing-versions", summary="核价版本列表")
async def pricing_versions(
    inquiry_id: uuid.UUID,
    db: DbSession,
    current: User = Depends(require_permission("pricing:view")),
) -> dict[str, Any]:
    await get_or_404(db, Inquiry, inquiry_id, "询价单")
    rows = (
        (
            await db.execute(
                select(PricingRecord)
                .where(PricingRecord.inquiry_id == inquiry_id, PricingRecord.deleted_at.is_(None))
                .order_by(PricingRecord.version.desc())
            )
        )
        .scalars()
        .all()
    )
    can_cost = current.is_superuser or "pricing:cost_view" in current.permission_codes
    can_floor = current.is_superuser or "pricing:floor_view" in current.permission_codes
    out = []
    for row in rows:
        data = PricingOut.model_validate(row).model_dump(mode="json")
        if not can_cost:
            for field in (
                "material_cost",
                "labor_cost",
                "packaging_cost",
                "freight_cost",
                "tooling_cost",
                "customization_cost",
                "moq_cost",
                "other_cost",
                "total_cost",
            ):
                data[field] = None
        if not can_floor:
            data["floor_price"] = None
        data["can_view_cost"] = can_cost
        data["can_view_floor"] = can_floor
        out.append(data)
    return resp.ok(out)
