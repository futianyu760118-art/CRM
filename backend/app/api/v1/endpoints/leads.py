"""M2 线索接口：CRUD + 分配 + 查重 + 转客户（PAND-315）。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Select, exists, func, or_, select

from app.core import response as resp
from app.core.deps import DbSession, require_permission
from app.core.error_codes import ErrCode
from app.core.exceptions import ApiError, ConflictError, ForbiddenError, NotFoundError
from app.db.base import utcnow
from app.domain import dictionaries as dic
from app.models.business import Activity, Company, Contact, ContactCompanyLink, Lead, Task
from app.models.user import User
from app.schemas.business import (
    LeadAssignIn,
    LeadConvertIn,
    LeadConvertOut,
    LeadCreate,
    LeadDuplicateCheckIn,
    LeadOut,
    LeadUpdate,
)
from app.services import company_code, contact_link, dedup
from app.services.data_scope import apply_data_scope, get_user_scope
from app.services.number_sequence import next_number
from app.services.query import apply_sort, get_or_404, paginate, soft_delete

router = APIRouter(prefix="/leads", tags=["M2-线索"])

#: 派生列排序：负责人 / 最近跟进 / 下次跟进（PAND-314 §3.2）
_DERIVED_SORTS = {"owner_name", "last_followup_at", "next_due_date"}


def _last_followup_expr() -> Any:
    return (
        select(func.max(Activity.happened_at))
        .where(
            Activity.biz_type == "LEAD",
            Activity.biz_id == Lead.id,
            Activity.deleted_at.is_(None),
        )
        .correlate_except(Activity)
        .scalar_subquery()
    )


def _next_due_expr() -> Any:
    return (
        select(func.min(Task.due_date))
        .where(
            Task.biz_type == "LEAD",
            Task.biz_id == Lead.id,
            Task.status == "PENDING",
            Task.deleted_at.is_(None),
        )
        .correlate_except(Task)
        .scalar_subquery()
    )


def _owner_name_expr() -> Any:
    return select(User.name).where(User.id == Lead.owner_id).correlate_except(User).scalar_subquery()


def _overdue_expr(now: datetime) -> Any:
    return exists(
        select(Task.id).where(
            Task.biz_type == "LEAD",
            Task.biz_id == Lead.id,
            Task.status == "PENDING",
            Task.deleted_at.is_(None),
            Task.due_date.is_not(None),
            Task.due_date < now,
        )
    )


def _apply_derived_sort(stmt: Select, sort: str, order: str) -> Select:
    if sort not in _DERIVED_SORTS:
        return apply_sort(stmt, Lead, sort, order)
    expr = {
        "owner_name": _owner_name_expr(),
        "last_followup_at": _last_followup_expr(),
        "next_due_date": _next_due_expr(),
    }[sort]
    ordering = expr.asc() if order == "asc" else expr.desc()
    return stmt.order_by(ordering.nullslast())


async def _enrich(db: DbSession, rows: list[Lead]) -> list[dict[str, Any]]:
    """补全派生三列与转化客户展示字段。"""
    ids = [r.id for r in rows]
    owner_ids = {r.owner_id for r in rows if r.owner_id}
    owners: dict[uuid.UUID, str] = {}
    if owner_ids:
        owner_rows = (await db.execute(select(User.id, User.name).where(User.id.in_(owner_ids)))).all()
        owners = {r[0]: r[1] for r in owner_rows}

    last_followups: dict[uuid.UUID, datetime] = {}
    next_dues: dict[uuid.UUID, datetime] = {}
    if ids:
        last_followups = {
            r[0]: r[1]
            for r in (
                await db.execute(
                    select(Activity.biz_id, func.max(Activity.happened_at))
                    .where(
                        Activity.biz_type == "LEAD",
                        Activity.biz_id.in_(ids),
                        Activity.deleted_at.is_(None),
                    )
                    .group_by(Activity.biz_id)
                )
            ).all()
            if r[0] and r[1]
        }
        next_dues = {
            r[0]: r[1]
            for r in (
                await db.execute(
                    select(Task.biz_id, func.min(Task.due_date))
                    .where(
                        Task.biz_type == "LEAD",
                        Task.biz_id.in_(ids),
                        Task.status == "PENDING",
                        Task.deleted_at.is_(None),
                    )
                    .group_by(Task.biz_id)
                )
            ).all()
            if r[0] and r[1]
        }

    company_ids = {r.converted_company_id for r in rows if r.converted_company_id}
    companies: dict[uuid.UUID, Company] = {}
    if company_ids:
        companies = {
            c.id: c
            for c in (await db.execute(select(Company).where(Company.id.in_(company_ids)))).scalars().all()
        }

    result: list[dict[str, Any]] = []
    for row in rows:
        data = LeadOut.model_validate(row).model_dump(mode="json")
        data["owner_name"] = owners.get(row.owner_id) if row.owner_id else None
        data["last_followup_at"] = last_followups.get(row.id).isoformat() if last_followups.get(row.id) else None
        data["next_due_date"] = next_dues.get(row.id).isoformat() if next_dues.get(row.id) else None
        company = companies.get(row.converted_company_id) if row.converted_company_id else None
        data["converted_company_name"] = company.name if company else None
        data["converted_company_code"] = company.code if company else None
        result.append(data)
    return result


def _dedup_conflict(message: str, result: dict[str, Any]) -> ApiError:
    candidates = result["definite"] + result["suspected"]
    return ApiError(
        ErrCode.CONFLICT,
        message,
        http_status=409,
        data={
            "candidates": candidates,
            "definite": result["definite"],
            "suspected": result["suspected"],
            "truncated": result["truncated"],
            "total": result["total"],
        },
    )


@router.get("", summary="线索列表（含负责人/最近跟进/下次跟进 + 逾期筛选）")
async def list_leads(
    db: DbSession,
    current: User = Depends(require_permission("lead:view")),
    keyword: str | None = Query(None, description="公司名/联系人/邮箱"),
    status: str | None = None,
    source: str | None = None,
    lead_level: str | None = None,
    channel: str | None = None,
    owner_id: uuid.UUID | None = None,
    overdue: bool = Query(False, description="仅看下次跟进已逾期"),
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
    if lead_level:
        stmt = stmt.where(Lead.lead_level == lead_level)
    if channel:
        stmt = stmt.where(Lead.channel == channel)
    if owner_id:
        stmt = stmt.where(Lead.owner_id == owner_id)
    if overdue:
        stmt = stmt.where(_overdue_expr(utcnow()))
    stmt = await apply_data_scope(stmt, Lead, current, db)

    stmt = _apply_derived_sort(stmt, sort, order)
    rows, total = await paginate(db, stmt, page, page_size)
    items = await _enrich(db, list(rows))
    return resp.page(items, total, page, page_size)


@router.post("/check-duplicate", summary="线索查重（LEAD-02，创建前预检）")
async def check_duplicate(
    payload: LeadDuplicateCheckIn,
    db: DbSession,
    _: User = Depends(require_permission("lead:view")),
) -> dict[str, Any]:
    result = await dedup.check_lead_duplicates(
        db,
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        exclude_lead_id=payload.exclude_lead_id,
    )
    return resp.ok(result)


@router.post("", summary="新建线索（强制查重）", status_code=201)
async def create_lead(
    payload: LeadCreate,
    db: DbSession,
    current: User = Depends(require_permission("lead:create")),
) -> dict[str, Any]:
    result = await dedup.check_lead_duplicates(db, name=payload.name, email=payload.email, phone=payload.phone)
    if result["definite"] and not payload.force:
        raise _dedup_conflict("存在确定重复线索/客户，请打开已有记录或确认仍然创建", result)
    if payload.force and result["definite"] and not (payload.dedup_note or "").strip():
        raise ApiError(ErrCode.VALIDATION_ERROR, "请填写查重说明后再确认创建", http_status=400)

    data = payload.model_dump(exclude_unset=True, exclude={"force", "dedup_note"})
    data["owner_id"] = payload.owner_id or current.id
    if payload.force:
        data["remark"] = dedup.merge_note(data.get("remark"), payload.dedup_note)
    lead = Lead(
        **data,
        lead_no=await next_number("lead"),
        department_id=current.department_id,
    )
    db.add(lead)
    await db.commit()
    await db.refresh(lead)
    items = await _enrich(db, [lead])
    return resp.ok(items[0])


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
    items = await _enrich(db, [lead])
    return resp.ok(items[0])


@router.put("/{lead_id}", summary="更新线索（改名/邮箱/电话变更触发查重）")
async def update_lead(
    lead_id: uuid.UUID,
    payload: LeadUpdate,
    db: DbSession,
    _: User = Depends(require_permission("lead:update")),
) -> dict[str, Any]:
    lead = await get_or_404(db, Lead, lead_id, "线索")
    data = payload.model_dump(exclude_unset=True, exclude={"force", "dedup_note"})

    check_keys = {"name", "email", "phone"} & set(data)
    if check_keys and not payload.force:
        result = await dedup.check_lead_duplicates(
            db,
            name=data.get("name", lead.name),
            email=data.get("email", lead.email),
            phone=data.get("phone", lead.phone),
            exclude_lead_id=lead.id,
        )
        if result["definite"]:
            raise _dedup_conflict("修改后与已有记录重复，请确认", result)

    for key, value in data.items():
        setattr(lead, key, value)
    if payload.force and payload.dedup_note:
        lead.remark = dedup.merge_note(lead.remark, payload.dedup_note)
    await db.commit()
    await db.refresh(lead)
    items = await _enrich(db, [lead])
    return resp.ok(items[0])


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
    items = await _enrich(db, [lead])
    return resp.ok(items[0])


async def _find_contact_by_email(db: DbSession, company_id: uuid.UUID, email: str | None) -> Contact | None:
    norm = dedup.normalize_email(email)
    if not norm:
        return None
    linked = (
        await db.execute(
            select(Contact)
            .join(ContactCompanyLink, ContactCompanyLink.contact_id == Contact.id)
            .where(
                ContactCompanyLink.company_id == company_id,
                ContactCompanyLink.deleted_at.is_(None),
                Contact.deleted_at.is_(None),
                func.lower(Contact.email) == norm,
            )
        )
    ).scalars().first()
    if linked is not None:
        return linked
    return (
        await db.execute(
            select(Contact).where(
                Contact.company_id == company_id,
                Contact.deleted_at.is_(None),
                func.lower(Contact.email) == norm,
            )
        )
    ).scalars().first()


async def _ensure_contact(
    db: DbSession,
    lead: Lead,
    company: Company,
    payload: LeadConvertIn,
    current: User,
) -> uuid.UUID | None:
    if not payload.create_contact or not (lead.contact_name or lead.email):
        return None
    existing = await _find_contact_by_email(db, company.id, lead.email)
    if existing is not None:
        return existing.id

    primaries = await contact_link.primary_contact_map(db, {company.id})
    contact = Contact(
        company_id=company.id,
        name=lead.contact_name or lead.name,
        email=lead.email,
        phone=lead.phone,
        is_primary=company.id not in primaries,
        owner_id=lead.owner_id or current.id,
        department_id=lead.department_id or current.department_id,
    )
    db.add(contact)
    await db.flush()
    await contact_link.attach_company(
        db,
        contact,
        company.id,
        relation_type=payload.relation_type,
        is_primary=contact.is_primary,
    )
    return contact.id


def _lead_source(lead: Lead) -> str:
    if lead.channel in dic.CUSTOMER_SOURCES:
        return lead.channel
    if lead.source in dic.CUSTOMER_SOURCES:
        return lead.source
    return dic.CUSTOMER_SOURCE_DEFAULT


@router.post("/{lead_id}/convert", summary="线索转客户（16-15 查重 + 关联既有客户）")
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

    if payload.link_company_id is not None:
        company = await get_or_404(db, Company, payload.link_company_id, "客户")
        linked_existing = True
    else:
        result = await dedup.check_company_duplicates(db, name=lead.name, email=lead.email, phone=lead.phone)
        if result["definite"]:
            raise _dedup_conflict("已存在同名客户，请关联既有客户（link_company_id）", result)
        if result["suspected"] and not (payload.non_duplicate_reason or "").strip():
            raise _dedup_conflict("存在疑似重复客户，请关联既有客户、填写非重复说明后新建或放弃", result)
        company = None
        linked_existing = False

    if company is None:
        owner = (
            await db.execute(select(User).where(User.id == (lead.owner_id or current.id)))
        ).scalar_one_or_none() or current
        code, owner_seq, global_seq = await company_code.next_company_code(owner)
        remark = f"由线索 {lead.lead_no} 转化"
        reason = (payload.non_duplicate_reason or "").strip()
        if reason:
            remark = f"{remark}\n非重复说明：{reason}"
        company = Company(
            code=code,
            owner_seq=owner_seq,
            global_seq=global_seq,
            name=lead.name,
            country=lead.country,
            industry=lead.industry,
            customer_level=payload.customer_level,
            source=_lead_source(lead),
            company_background=lead.background,
            owner_id=owner.id,
            department_id=lead.department_id or current.department_id,
            remark=remark,
        )
        db.add(company)
        await db.flush()
        await company_code.ensure_primary_code(db, company)

    contact_id = await _ensure_contact(db, lead, company, payload, current)

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
            linked_existing=linked_existing,
        ).model_dump(mode="json")
    )
