"""M2 线索接口：CRUD + 分配 + 转客户。"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select

from app.core import response as resp
from app.core.deps import DbSession, require_permission
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.db.base import utcnow
from app.models.business import Company, Contact, Lead
from app.models.user import User
from app.schemas.business import (
    LeadAssignIn,
    LeadConvertIn,
    LeadConvertOut,
    LeadCreate,
    LeadOut,
    LeadUpdate,
)
from app.services import company_code
from app.services.data_scope import apply_data_scope, get_user_scope
from app.services.number_sequence import next_number
from app.services.query import apply_sort, get_or_404, paginate, soft_delete

router = APIRouter(prefix="/leads", tags=["M2-线索"])


@router.get("", summary="线索列表")
async def list_leads(
    db: DbSession,
    current: User = Depends(require_permission("lead:view")),
    keyword: str | None = Query(None, description="公司名/联系人/邮箱"),
    status: str | None = None,
    source: str | None = None,
    owner_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    sort: str = "created_at",
    order: str = Query("desc", pattern="^(asc|desc)$"),
) -> dict[str, Any]:
    stmt = select(Lead).where(Lead.deleted_at.is_(None))
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(or_(Lead.name.ilike(like), Lead.contact_name.ilike(like), Lead.email.ilike(like)))
    if status:
        stmt = stmt.where(Lead.status == status)
    if source:
        stmt = stmt.where(Lead.source == source)
    if owner_id:
        stmt = stmt.where(Lead.owner_id == owner_id)
    stmt = await apply_data_scope(stmt, Lead, current, db)

    stmt = apply_sort(stmt, Lead, sort, order)
    rows, total = await paginate(db, stmt, page, page_size)
    items = [LeadOut.model_validate(r).model_dump(mode="json") for r in rows]
    return resp.page(items, total, page, page_size)


@router.post("", summary="新建线索", status_code=201)
async def create_lead(
    payload: LeadCreate,
    db: DbSession,
    current: User = Depends(require_permission("lead:create")),
) -> dict[str, Any]:
    lead = Lead(
        **payload.model_dump(exclude_unset=True),
        lead_no=await next_number("lead"),
        owner_id=payload.owner_id or current.id,
        department_id=current.department_id,
    )
    db.add(lead)
    await db.commit()
    await db.refresh(lead)
    return resp.ok(LeadOut.model_validate(lead).model_dump(mode="json"))


@router.get("/{lead_id}", summary="线索详情")
async def get_lead(
    lead_id: uuid.UUID,
    db: DbSession,
    current: User = Depends(require_permission("lead:view")),
) -> dict[str, Any]:
    lead = await get_or_404(db, Lead, lead_id, "线索")
    scope_type, dept_ids = await get_user_scope(current, db)
    if scope_type != "ALL" and lead.owner_id != current.id and lead.department_id not in dept_ids:
        raise ForbiddenError("无权访问该线索")
    return resp.ok(LeadOut.model_validate(lead).model_dump(mode="json"))


@router.put("/{lead_id}", summary="更新线索")
async def update_lead(
    lead_id: uuid.UUID,
    payload: LeadUpdate,
    db: DbSession,
    _: User = Depends(require_permission("lead:update")),
) -> dict[str, Any]:
    lead = await get_or_404(db, Lead, lead_id, "线索")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(lead, key, value)
    await db.commit()
    await db.refresh(lead)
    return resp.ok(LeadOut.model_validate(lead).model_dump(mode="json"))


@router.delete("/{lead_id}", summary="删除线索（软删除）")
async def delete_lead(
    lead_id: uuid.UUID,
    db: DbSession,
    _: User = Depends(require_permission("lead:delete")),
) -> dict[str, Any]:
    lead = await get_or_404(db, Lead, lead_id, "线索")
    soft_delete(lead)
    await db.commit()
    return resp.ok({"deleted": True})


@router.post("/{lead_id}/assign", summary="分配线索")
async def assign_lead(
    lead_id: uuid.UUID,
    payload: LeadAssignIn,
    db: DbSession,
    _: User = Depends(require_permission("lead:assign")),
) -> dict[str, Any]:
    lead = await get_or_404(db, Lead, lead_id, "线索")
    owner = (await db.execute(select(User).where(User.id == payload.owner_id))).scalar_one_or_none()
    if owner is None:
        raise NotFoundError("指定的负责人不存在")
    lead.owner_id = owner.id
    lead.department_id = owner.department_id
    lead.status = "ASSIGNED"
    lead.assigned_at = utcnow()
    await db.commit()
    await db.refresh(lead)
    return resp.ok(LeadOut.model_validate(lead).model_dump(mode="json"))


@router.post("/{lead_id}/convert", summary="线索转客户")
async def convert_lead(
    lead_id: uuid.UUID,
    payload: LeadConvertIn,
    db: DbSession,
    current: User = Depends(require_permission("lead:convert")),
) -> dict[str, Any]:
    lead = await get_or_404(db, Lead, lead_id, "线索")
    if lead.status == "CONVERTED":
        raise ConflictError("该线索已转化，请勿重复操作")
    if lead.status == "INVALID":
        raise ConflictError("无效线索不可转化")

    domain = (lead.email or "").split("@")[-1].lower() if lead.email and "@" in lead.email else None

    company = None
    if lead.email:
        company = (
            (await db.execute(select(Company).where(Company.deleted_at.is_(None), Company.name == lead.name)))
            .scalars()
            .first()
        )
    if company is None and domain:
        company = (
            (
                await db.execute(
                    select(Company).where(Company.deleted_at.is_(None), Company.name_en.ilike(f"%{domain}%"))
                )
            )
            .scalars()
            .first()
        )

    created_company = False
    if company is None:
        owner = (
            await db.execute(select(User).where(User.id == (lead.owner_id or current.id)))
        ).scalar_one_or_none() or current
        code, owner_seq, global_seq = await company_code.next_company_code(owner)
        company = Company(
            code=code,
            owner_seq=owner_seq,
            global_seq=global_seq,
            name=lead.name,
            country=lead.country,
            industry=lead.industry,
            customer_level=payload.customer_level,
            source=lead.source,
            owner_id=owner.id,
            department_id=lead.department_id or current.department_id,
            remark=f"由线索 {lead.lead_no} 转化",
        )
        db.add(company)
        await db.flush()
        await company_code.ensure_primary_code(db, company)
        created_company = True

    contact_id: uuid.UUID | None = None
    if payload.create_contact and (lead.contact_name or lead.email):
        existing = None
        if lead.email:
            existing = (
                (
                    await db.execute(
                        select(Contact).where(
                            Contact.company_id == company.id,
                            Contact.email == lead.email,
                            Contact.deleted_at.is_(None),
                        )
                    )
                )
                .scalars()
                .first()
            )
        if existing is None:
            contact = Contact(
                company_id=company.id,
                name=lead.contact_name or lead.name,
                email=lead.email,
                phone=lead.phone,
                is_primary=created_company,
                owner_id=lead.owner_id or current.id,
                department_id=lead.department_id or current.department_id,
            )
            db.add(contact)
            await db.flush()
            contact_id = contact.id
        else:
            contact_id = existing.id

    lead.status = "CONVERTED"
    lead.converted_company_id = company.id
    lead.converted_contact_id = contact_id
    lead.converted_at = utcnow()
    await db.commit()

    return resp.ok(
        LeadConvertOut(
            lead_id=lead.id,
            company_id=company.id,
            company_code=company.code,
            contact_id=contact_id,
        ).model_dump(mode="json")
    )
