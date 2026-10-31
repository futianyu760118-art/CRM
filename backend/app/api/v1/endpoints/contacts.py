"""M2 联系人接口：CRUD + 一人多客户关联 + 主要联系人（PAND-315 / CONT-04）。"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select

from app.core import response as resp
from app.core.deps import DbSession, require_permission
from app.core.error_codes import ErrCode
from app.core.exceptions import ApiError, ForbiddenError
from app.db.base import utcnow
from app.domain import dictionaries as dic
from app.models.business import Company, Contact, ContactCompanyLink
from app.models.user import User
from app.schemas.business import (
    ContactCreate,
    ContactLinkIn,
    ContactOut,
    ContactPrimaryIn,
    ContactUpdate,
)
from app.services import contact_link, dedup
from app.services.data_scope import can_access_owner, get_user_scope
from app.services.query import get_or_404, paginate, soft_delete

router = APIRouter(prefix="/contacts", tags=["M2-联系人"])


async def _enrich(db: DbSession, rows: list[Contact]) -> list[dict[str, Any]]:
    companies_map = await contact_link.contact_companies_map(db, rows)
    result: list[dict[str, Any]] = []
    for row in rows:
        data = ContactOut.model_validate(row).model_dump(mode="json")
        relations = companies_map.get(row.id, [])
        data["companies"] = relations
        primary = next((r for r in relations if r["is_primary"]), relations[0] if relations else None)
        data["company_name"] = primary["company_name"] if primary else None
        data["relation_type"] = primary["relation_type"] if primary else dic.CONTACT_RELATION_DEFAULT
        data["relation_label"] = primary["relation_label"] if primary else dic.CONTACT_RELATION_TYPES[
            dic.CONTACT_RELATION_DEFAULT
        ]
        data["is_primary"] = bool(primary and primary["is_primary"])
        result.append(data)
    return result


async def _one(db: DbSession, row: Contact) -> dict[str, Any]:
    return (await _enrich(db, [row]))[0]


async def _check_scope(db: DbSession, current: User, row: Contact) -> None:
    scope_type, dept_ids = await get_user_scope(current, db)
    if not can_access_owner(current, scope_type, dept_ids, row.owner_id, row.department_id):
        raise ForbiddenError("无权访问该联系人")


async def _same_person(db: DbSession, payload: ContactCreate) -> Contact | None:
    """同人判定：手机归一 / 邮箱小写 / 微信 任一相同。"""
    conds = []
    email = dedup.normalize_email(payload.email)
    if email:
        conds.append(func.lower(Contact.email) == email)
    for value in (payload.phone, payload.mobile):
        digits = dedup.normalize_phone(value)
        if digits:
            conds.append(func.regexp_replace(func.coalesce(Contact.phone, ""), "[^0-9]", "", "g") == digits)
            conds.append(func.regexp_replace(func.coalesce(Contact.mobile, ""), "[^0-9]", "", "g") == digits)
    wechat = (payload.wechat or "").strip().lower()
    if wechat:
        conds.append(func.lower(Contact.wechat) == wechat)
    if not conds:
        return None
    return (
        await db.execute(select(Contact).where(Contact.deleted_at.is_(None), or_(*conds)))
    ).scalars().first()


@router.get("", summary="联系人列表（支持按客户过滤）")
async def list_contacts(
    db: DbSession,
    current: User = Depends(require_permission("contact:view")),
    keyword: str | None = Query(None, description="姓名/邮箱/电话/手机"),
    company_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    sort: str = "created_at",
    order: str = Query("desc", pattern="^(asc|desc)$"),
) -> dict[str, Any]:
    stmt = select(Contact).where(Contact.deleted_at.is_(None))
    if company_id:
        linked = select(ContactCompanyLink.contact_id).where(
            ContactCompanyLink.company_id == company_id,
            ContactCompanyLink.deleted_at.is_(None),
        )
        stmt = stmt.where(or_(Contact.id.in_(linked), Contact.company_id == company_id))
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(
            or_(
                Contact.name.ilike(like),
                Contact.email.ilike(like),
                Contact.phone.ilike(like),
                Contact.mobile.ilike(like),
            )
        )
    scope_type, dept_ids = await get_user_scope(current, db)
    if scope_type == "SELF":
        stmt = stmt.where(Contact.owner_id == current.id)
    elif scope_type != "ALL":
        stmt = stmt.where(
            or_(Contact.owner_id == current.id, Contact.department_id.in_(dept_ids))
        )

    column = getattr(Contact, sort, Contact.created_at)
    stmt = stmt.order_by(column.asc() if order == "asc" else column.desc())
    rows, total = await paginate(db, stmt, page, page_size)
    items = await _enrich(db, list(rows))
    return resp.page(items, total, page, page_size)


@router.post("", summary="新建联系人（同人检测，可新增关联或强制独立）", status_code=201)
async def create_contact(
    payload: ContactCreate,
    db: DbSession,
    current: User = Depends(require_permission("contact:create")),
) -> dict[str, Any]:
    company = None
    if payload.company_id:
        company = await get_or_404(db, Company, payload.company_id, "客户")

    existing = await _same_person(db, payload) if company else None
    if payload.link_to_existing_id:
        existing = await get_or_404(db, Contact, payload.link_to_existing_id, "联系人")
    if existing is not None and not payload.force_independent:
        if payload.link_to_existing_id:
            await contact_link.attach_company(
                db,
                existing,
                company.id,
                relation_type=payload.relation_type or dic.CONTACT_RELATION_DEFAULT,
                is_primary=payload.is_primary,
            )
            await db.commit()
            await db.refresh(existing)
            return resp.ok(await _one(db, existing))
        raise ApiError(
            ErrCode.CONFLICT,
            "该联系人在客户下已存在，可新增关联或继续新建独立联系人",
            http_status=409,
            data={"existing": await _one(db, existing)},
        )

    data = payload.model_dump(
        exclude={"link_to_existing_id", "force_independent", "relation_type"}
    )
    contact = Contact(**data)
    if contact.owner_id is None:
        contact.owner_id = current.id
    if contact.department_id is None:
        contact.department_id = current.department_id
    db.add(contact)
    await db.flush()
    if company is not None:
        await contact_link.attach_company(
            db,
            contact,
            company.id,
            relation_type=payload.relation_type or dic.CONTACT_RELATION_DEFAULT,
            is_primary=payload.is_primary,
        )
    await db.commit()
    await db.refresh(contact)
    return resp.ok(await _one(db, contact))


@router.get("/{contact_id}", summary="联系人详情（含关联客户）")
async def get_contact(
    contact_id: uuid.UUID,
    db: DbSession,
    current: User = Depends(require_permission("contact:view")),
) -> dict[str, Any]:
    row = await get_or_404(db, Contact, contact_id, "联系人")
    await _check_scope(db, current, row)
    return resp.ok(await _one(db, row))


@router.put("/{contact_id}", summary="更新联系人主档（所有关联客户同步展示）")
async def update_contact(
    contact_id: uuid.UUID,
    payload: ContactUpdate,
    db: DbSession,
    current: User = Depends(require_permission("contact:update")),
) -> dict[str, Any]:
    row = await get_or_404(db, Contact, contact_id, "联系人")
    await _check_scope(db, current, row)
    data = payload.model_dump(exclude_unset=True, exclude={"relation_type"})
    for key, value in data.items():
        setattr(row, key, value)

    if payload.company_id is not None:
        await contact_link.attach_company(
            db,
            row,
            payload.company_id,
            relation_type=payload.relation_type or dic.CONTACT_RELATION_DEFAULT,
            is_primary=bool(payload.is_primary),
        )
    elif payload.relation_type and row.company_id:
        await contact_link.attach_company(
            db, row, row.company_id, relation_type=payload.relation_type, is_primary=False
        )
    if payload.is_primary and row.company_id:
        await contact_link.set_primary(db, row, row.company_id)
    await db.commit()
    await db.refresh(row)
    return resp.ok(await _one(db, row))


@router.delete("/{contact_id}", summary="删除联系人主档（级联删除关联）")
async def delete_contact(
    contact_id: uuid.UUID,
    db: DbSession,
    current: User = Depends(require_permission("contact:delete")),
) -> dict[str, Any]:
    row = await get_or_404(db, Contact, contact_id, "联系人")
    await _check_scope(db, current, row)
    links = (
        await db.execute(
            select(ContactCompanyLink).where(
                ContactCompanyLink.contact_id == contact_id,
                ContactCompanyLink.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    for link in links:
        link.deleted_at = utcnow()
        link.is_primary = False
    soft_delete(row)
    await db.commit()
    return resp.ok({"deleted": True, "unlinked": len(links)})


@router.post("/{contact_id}/links", summary="为既有联系人新增客户关联")
async def add_link(
    contact_id: uuid.UUID,
    payload: ContactLinkIn,
    db: DbSession,
    current: User = Depends(require_permission("contact:update")),
) -> dict[str, Any]:
    row = await get_or_404(db, Contact, contact_id, "联系人")
    await _check_scope(db, current, row)
    await get_or_404(db, Company, payload.company_id, "客户")
    await contact_link.attach_company(
        db,
        row,
        payload.company_id,
        relation_type=payload.relation_type,
        is_primary=payload.is_primary,
    )
    await db.commit()
    await db.refresh(row)
    return resp.ok(await _one(db, row))


@router.delete("/{contact_id}/links/{company_id}", summary="解除联系人某客户关联")
async def remove_link(
    contact_id: uuid.UUID,
    company_id: uuid.UUID,
    db: DbSession,
    current: User = Depends(require_permission("contact:update")),
) -> dict[str, Any]:
    row = await get_or_404(db, Contact, contact_id, "联系人")
    await _check_scope(db, current, row)
    await contact_link.detach_company(db, row, company_id)
    await db.commit()
    await db.refresh(row)
    return resp.ok(await _one(db, row))


@router.put("/{contact_id}/primary", summary="设为主要联系人（旧主自动取消）")
async def set_primary(
    contact_id: uuid.UUID,
    payload: ContactPrimaryIn,
    db: DbSession,
    current: User = Depends(require_permission("contact:update")),
) -> dict[str, Any]:
    row = await get_or_404(db, Contact, contact_id, "联系人")
    await _check_scope(db, current, row)
    company_id = payload.company_id or row.company_id
    if company_id is None:
        raise ApiError(ErrCode.VALIDATION_ERROR, "请指定客户", http_status=400)
    await get_or_404(db, Company, company_id, "客户")
    await contact_link.set_primary(db, row, company_id)
    await db.commit()
    await db.refresh(row)
    return resp.ok(await _one(db, row))


__all__ = ["router"]
