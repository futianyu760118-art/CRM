"""M2 客户接口：CRUD + 去重 + 合并 + 编码。"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select, update

from app.core import response as resp
from app.core.deps import DbSession, require_permission
from app.core.exceptions import ConflictError
from app.models.business import (
    Activity,
    BusinessCode,
    Company,
    Contact,
    Inquiry,
    Opportunity,
)
from app.models.email import EmailThread
from app.models.pricing import Quotation
from app.models.user import User
from app.schemas.business import (
    BusinessCodeOut,
    CompanyCreate,
    CompanyMergeIn,
    CompanyMergeOut,
    CompanyOut,
    CompanyUpdate,
    CurrencyCodeIn,
    CurrencyCodeOut,
    CustomerCodePreview,
)
from app.services import company_code, ebms_sync
from app.services.data_scope import apply_data_scope
from app.services.query import apply_sort, get_or_404, paginate, soft_delete

router = APIRouter(prefix="/customers", tags=["M2-客户"])

CODE_RULE = "{业务员编号}-{业务员第N个客户}-{公司第N个客户}，如 HJ003-176-576；同客户多币别追加 -1/-2"


async def _company_or_404(db: DbSession, company_id: uuid.UUID) -> Company:
    return await get_or_404(db, Company, company_id, "客户")


async def _enrich(db: DbSession, rows: list[Company]) -> list[dict[str, Any]]:
    """补全负责人名称、联系人数量、编码规则提示。"""
    ids = [r.id for r in rows]
    counts: dict[uuid.UUID, int] = {}
    if ids:
        found = (
            await db.execute(
                select(Contact.company_id, func.count())
                .where(Contact.company_id.in_(ids), Contact.deleted_at.is_(None))
                .group_by(Contact.company_id)
            )
        ).all()
        counts = {r[0]: int(r[1]) for r in found}

    owner_ids = {r.owner_id for r in rows if r.owner_id}
    owners: dict[uuid.UUID, str] = {}
    if owner_ids:
        found_owners = (await db.execute(select(User.id, User.name).where(User.id.in_(owner_ids)))).all()
        owners = {r[0]: r[1] for r in found_owners}

    result = []
    for row in rows:
        data = CompanyOut.model_validate(row).model_dump(mode="json")
        data["contact_count"] = counts.get(row.id, 0)
        data["owner_name"] = owners.get(row.owner_id) if row.owner_id else None
        data["code_rule"] = CODE_RULE
        result.append(data)
    return result


@router.get("", summary="客户列表")
async def list_companies(
    db: DbSession,
    current: User = Depends(require_permission("customer:view")),
    keyword: str | None = Query(None, description="名称/编码/国家"),
    country: str | None = None,
    customer_level: str | None = None,
    status: str | None = None,
    owner_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    sort: str = "created_at",
    order: str = Query("desc", pattern="^(asc|desc)$"),
) -> dict[str, Any]:
    stmt = select(Company).where(Company.deleted_at.is_(None))
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(
            or_(
                Company.name.ilike(like),
                Company.name_en.ilike(like),
                Company.code.ilike(like),
                Company.country.ilike(like),
            )
        )
    if country:
        stmt = stmt.where(Company.country == country)
    if customer_level:
        stmt = stmt.where(Company.customer_level == customer_level)
    if status:
        stmt = stmt.where(Company.status == status)
    if owner_id:
        stmt = stmt.where(Company.owner_id == owner_id)
    stmt = await apply_data_scope(stmt, Company, current, db)

    stmt = apply_sort(stmt, Company, sort, order)
    rows, total = await paginate(db, stmt, page, page_size)
    items = await _enrich(db, list(rows))
    return resp.page(items, total, page, page_size)


@router.post("", summary="新建客户", status_code=201)
async def create_company(
    payload: CompanyCreate,
    db: DbSession,
    current: User = Depends(require_permission("customer:create")),
) -> dict[str, Any]:
    owner_id = payload.owner_id or current.id
    owner = (await db.execute(select(User).where(User.id == owner_id))).scalar_one_or_none() or current

    code, owner_seq, global_seq = await company_code.next_company_code(owner)
    company = Company(
        **payload.model_dump(exclude_unset=True),
        code=code,
        owner_seq=owner_seq,
        global_seq=global_seq,
        owner_id=owner.id,
        department_id=current.department_id,
    )
    db.add(company)
    await db.flush()
    await company_code.ensure_primary_code(db, company)
    if company.currency:
        await company_code.add_currency_code(db, company, company.currency)
    await ebms_sync.emit_upsert(db, "customer", company)
    await db.commit()
    await db.refresh(company)
    items = await _enrich(db, [company])
    return resp.ok(items[0])


@router.get("/next-code", summary="预览下一个客户编码")
async def next_code_preview(
    current: User = Depends(require_permission("customer:view")),
) -> dict[str, Any]:
    code, owner_seq, global_seq = await company_code.preview_next_code(current)
    return resp.ok(
        CustomerCodePreview(
            code=code,
            owner_code=current.code,
            owner_seq=owner_seq,
            global_seq=global_seq,
            rule=CODE_RULE,
        ).model_dump(mode="json")
    )


@router.get("/duplicates", summary="客户重复检测")
async def duplicates(
    db: DbSession,
    _: User = Depends(require_permission("customer:view")),
) -> dict[str, Any]:
    groups = (
        await db.execute(
            select(Company.name, func.count().label("cnt"))
            .where(Company.deleted_at.is_(None))
            .group_by(Company.name)
            .having(func.count() > 1)
        )
    ).all()
    result = []
    for name, _cnt in groups:
        rows = (
            (await db.execute(select(Company).where(Company.name == name, Company.deleted_at.is_(None))))
            .scalars()
            .all()
        )
        result.append(
            {
                "key": name,
                "companies": [CompanyOut.model_validate(r).model_dump(mode="json") for r in rows],
            }
        )
    return resp.ok(result)


@router.post("/merge", summary="合并客户")
async def merge_companies(
    payload: CompanyMergeIn,
    db: DbSession,
    _: User = Depends(require_permission("customer:merge")),
) -> dict[str, Any]:
    target = await _company_or_404(db, payload.keep_id)
    source_ids = [sid for sid in payload.source_ids if sid != payload.keep_id]
    if not source_ids:
        raise ConflictError("未指定需要合并的客户")

    moved_contacts = moved_opportunities = 0
    for source_id in source_ids:
        await _company_or_404(db, source_id)

    for source_id in source_ids:
        result = await db.execute(update(Contact).where(Contact.company_id == source_id).values(company_id=target.id))
        moved_contacts += int(getattr(result, "rowcount", 0) or 0)
        result = await db.execute(
            update(Opportunity).where(Opportunity.company_id == source_id).values(company_id=target.id)
        )
        moved_opportunities += int(getattr(result, "rowcount", 0) or 0)
        await db.execute(update(Inquiry).where(Inquiry.company_id == source_id).values(company_id=target.id))
        await db.execute(update(Quotation).where(Quotation.company_id == source_id).values(company_id=target.id))
        await db.execute(update(Activity).where(Activity.company_id == source_id).values(company_id=target.id))
        await db.execute(update(EmailThread).where(EmailThread.company_id == source_id).values(company_id=target.id))
        await db.execute(update(BusinessCode).where(BusinessCode.company_id == source_id).values(company_id=target.id))
        source = await _company_or_404(db, source_id)
        source.status = "MERGED"
        source.remark = f"{source.remark or ''}\n已合并至 {target.code}".strip()
        soft_delete(source)
        await ebms_sync.emit_delete(db, "customer", source)

    await ebms_sync.emit_upsert(db, "customer", target)
    await db.commit()
    return resp.ok(
        CompanyMergeOut(
            target_id=target.id,
            merged=len(source_ids),
            moved_contacts=moved_contacts,
            moved_opportunities=moved_opportunities,
        ).model_dump(mode="json")
    )


@router.get("/{company_id}", summary="客户详情")
async def get_company(
    company_id: uuid.UUID,
    db: DbSession,
    _: User = Depends(require_permission("customer:view")),
) -> dict[str, Any]:
    company = await _company_or_404(db, company_id)
    enriched = await _enrich(db, [company])
    data = enriched[0]

    codes = await company_code.codes_of(db, company_id)
    data["business_codes"] = [BusinessCodeOut.model_validate(c).model_dump(mode="json") for c in codes]

    contacts = (
        (
            await db.execute(
                select(Contact)
                .where(Contact.company_id == company_id, Contact.deleted_at.is_(None))
                .order_by(Contact.is_primary.desc(), Contact.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    data["contacts"] = [
        {
            "id": str(c.id),
            "name": c.name,
            "position": c.position,
            "email": c.email,
            "phone": c.phone,
            "mobile": c.mobile,
            "is_primary": c.is_primary,
        }
        for c in contacts
    ]

    opportunities = (
        (
            await db.execute(
                select(Opportunity)
                .where(Opportunity.company_id == company_id, Opportunity.deleted_at.is_(None))
                .order_by(Opportunity.created_at.desc())
                .limit(50)
            )
        )
        .scalars()
        .all()
    )
    data["opportunities"] = [
        {
            "id": str(o.id),
            "opportunity_no": o.opportunity_no,
            "name": o.name,
            "stage": o.stage,
            "estimated_amount": float(o.estimated_amount) if o.estimated_amount else None,
            "currency": o.currency,
        }
        for o in opportunities
    ]

    inquiries = (
        (
            await db.execute(
                select(Inquiry)
                .where(Inquiry.company_id == company_id, Inquiry.deleted_at.is_(None))
                .order_by(Inquiry.created_at.desc())
                .limit(50)
            )
        )
        .scalars()
        .all()
    )
    data["inquiries"] = [
        {
            "id": str(i.id),
            "inquiry_no": i.inquiry_no,
            "status": i.status,
            "currency": i.currency,
            "created_at": i.created_at.isoformat() if i.created_at else None,
        }
        for i in inquiries
    ]

    emails = (
        (
            await db.execute(
                select(EmailThread)
                .where(EmailThread.company_id == company_id, EmailThread.deleted_at.is_(None))
                .order_by(EmailThread.last_message_at.desc().nullslast())
                .limit(20)
            )
        )
        .scalars()
        .all()
    )
    data["email_threads"] = [
        {
            "id": str(t.id),
            "subject": t.subject,
            "message_count": t.message_count,
            "last_message_at": t.last_message_at.isoformat() if t.last_message_at else None,
        }
        for t in emails
    ]
    return resp.ok(data)


@router.put("/{company_id}", summary="更新客户")
async def update_company(
    company_id: uuid.UUID,
    payload: CompanyUpdate,
    db: DbSession,
    _: User = Depends(require_permission("customer:update")),
) -> dict[str, Any]:
    company = await _company_or_404(db, company_id)
    data = payload.model_dump(exclude_unset=True)
    new_currency = data.get("currency")
    for key, value in data.items():
        setattr(company, key, value)
    if new_currency:
        await company_code.add_currency_code(db, company, new_currency)
    await ebms_sync.emit_upsert(db, "customer", company)
    await db.commit()
    await db.refresh(company)
    items = await _enrich(db, [company])
    return resp.ok(items[0])


@router.delete("/{company_id}", summary="删除客户（软删除）")
async def delete_company(
    company_id: uuid.UUID,
    db: DbSession,
    _: User = Depends(require_permission("customer:delete")),
) -> dict[str, Any]:
    company = await _company_or_404(db, company_id)
    soft_delete(company)
    await ebms_sync.emit_delete(db, "customer", company)
    await db.commit()
    return resp.ok({"deleted": True})


@router.get("/{company_id}/business-codes", summary="客户业务编码（含币别码）")
async def list_business_codes(
    company_id: uuid.UUID,
    db: DbSession,
    _: User = Depends(require_permission("customer:view")),
) -> dict[str, Any]:
    await _company_or_404(db, company_id)
    rows = await company_code.codes_of(db, company_id)
    return resp.ok([BusinessCodeOut.model_validate(r).model_dump(mode="json") for r in rows])


@router.post("/{company_id}/currencies", summary="为客户追加币别编码（-1/-2…）", status_code=201)
async def add_currency_code(
    company_id: uuid.UUID,
    payload: CurrencyCodeIn,
    db: DbSession,
    _: User = Depends(require_permission("customer:update")),
) -> dict[str, Any]:
    company = await _company_or_404(db, company_id)
    row, created = await company_code.add_currency_code(db, company, payload.currency)
    await db.commit()
    await db.refresh(row)
    return resp.ok(
        CurrencyCodeOut(id=row.id, code=row.code, currency=row.currency, created=created).model_dump(mode="json")
    )
