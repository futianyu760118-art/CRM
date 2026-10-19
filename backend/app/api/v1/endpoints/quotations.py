"""M4 报价接口：CRUD + 由核价生成 + 审批 + PDF + 邮件发送。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import delete, or_, select
from sqlalchemy.orm.attributes import set_committed_value

from app.core import response as resp
from app.core.config import settings
from app.core.deps import CurrentUser, DbSession, require_permission
from app.core.exceptions import ApiError, NotFoundError
from app.db.base import utcnow
from app.models.business import Company, Contact, Inquiry, InquiryItem, Opportunity
from app.models.email import File
from app.models.pricing import PricingRecord, Quotation, QuotationItem
from app.models.support import SystemConfig
from app.models.user import User
from app.schemas.pricing import (
    QuotationCreate,
    QuotationFromPricingIn,
    QuotationOut,
    QuotationUpdate,
)
from app.services import approval as approval_service
from app.services import company_code, email_service, export_excel, storage
from app.services import pdf as pdf_service
from app.services import pricing as pricing_service
from app.services.data_scope import apply_data_scope
from app.services.number_sequence import next_number
from app.services.query import apply_sort, get_or_404, paginate

router = APIRouter(prefix="/quotations", tags=["M4-报价"])


# ------------------------------------------------------------------ 内部工具


async def _seller_info(db: DbSession) -> dict[str, Any]:
    rows = (
        (
            await db.execute(
                select(SystemConfig).where(SystemConfig.group == "general", SystemConfig.deleted_at.is_(None))
            )
        )
        .scalars()
        .all()
    )
    config = {r.key: r.value for r in rows}
    return {
        "name": config.get("company.name", settings.APP_NAME),
        "address": config.get("company.address", ""),
        "contact": config.get("company.contact", ""),
    }


async def _load_items(db: DbSession, quotation: Quotation) -> list[QuotationItem]:
    """显式加载明细并写回关系属性，避免异步上下文隐式懒加载。"""
    rows = list(
        (
            await db.execute(
                select(QuotationItem)
                .where(
                    QuotationItem.quotation_id == quotation.id,
                    QuotationItem.deleted_at.is_(None),
                )
                .order_by(QuotationItem.sort, QuotationItem.created_at)
            )
        )
        .scalars()
        .all()
    )
    set_committed_value(quotation, "items", rows)
    return rows


def _recalc(quotation: Quotation) -> None:
    subtotal = 0.0
    for item in quotation.items:
        qty = float(item.quantity or 0)
        price = float(item.unit_price or 0)
        item.amount = round(qty * price, 4)
        subtotal += item.amount
    quotation.subtotal = round(subtotal, 4)
    quotation.total_amount = round(
        subtotal
        + float(quotation.additional_fee or 0)
        - float(quotation.discount or 0)
        + float(quotation.tax_amount or 0),
        4,
    )
    if quotation.valid_days:
        quotation.valid_until = (datetime.now(UTC) + timedelta(days=quotation.valid_days)).date()


async def _serialize(db: DbSession, quotation: Quotation) -> dict[str, Any]:
    await _load_items(db, quotation)
    data = QuotationOut.model_validate(quotation).model_dump(mode="json")
    company = (await db.execute(select(Company.name).where(Company.id == quotation.company_id))).scalar_one_or_none()
    data["company_name"] = company
    if quotation.contact_id:
        contact = (
            await db.execute(select(Contact.name).where(Contact.id == quotation.contact_id))
        ).scalar_one_or_none()
        data["contact_name"] = contact
    instance = await approval_service.latest_for_biz(db, "QUOTATION", quotation.id)
    data["approval_id"] = str(instance.id) if instance else None
    return data


async def _build_pdf_context(db: DbSession, quotation: Quotation) -> dict[str, Any]:
    company = (await db.execute(select(Company).where(Company.id == quotation.company_id))).scalar_one_or_none()
    contact_name = None
    if quotation.contact_id:
        contact_name = (
            await db.execute(select(Contact.name).where(Contact.id == quotation.contact_id))
        ).scalar_one_or_none()
    return pdf_service.build_context(
        seller=await _seller_info(db),
        quotation={
            "quotation_no": quotation.quotation_no,
            "created_at": datetime.now(UTC).strftime("%Y-%m-%d"),
            "valid_until": quotation.valid_until.isoformat() if quotation.valid_until else "",
            "currency": quotation.currency,
            "incoterm": quotation.incoterm,
            "payment_terms": quotation.payment_terms,
            "warranty": quotation.warranty,
            "remark": quotation.remark,
            "subtotal": quotation.subtotal,
            "additional_fee": quotation.additional_fee,
            "discount": quotation.discount,
            "tax_amount": quotation.tax_amount,
            "total_amount": quotation.total_amount,
        },
        customer={
            "name": company.name if company else "",
            "country": company.country if company else "",
            "contact_name": contact_name,
        },
        items=[
            {
                "product_name": i.product_name,
                "spec": i.spec,
                "quantity": i.quantity,
                "unit": i.unit,
                "unit_price": i.unit_price,
                "amount": i.amount,
            }
            for i in quotation.items
        ],
    )


# ------------------------------------------------------------------ 列表 / 新建


@router.get("", summary="报价列表")
async def list_quotations(
    db: DbSession,
    current: User = Depends(require_permission("quotation:view")),
    keyword: str | None = None,
    status: str | None = None,
    company_id: uuid.UUID | None = None,
    opportunity_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    sort: str = "created_at",
    order: str = Query("desc", pattern="^(asc|desc)$"),
) -> dict[str, Any]:
    stmt = select(Quotation).where(Quotation.deleted_at.is_(None))
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(or_(Quotation.quotation_no.ilike(like), Quotation.remark.ilike(like)))
    if status:
        stmt = stmt.where(Quotation.status == status)
    if company_id:
        stmt = stmt.where(Quotation.company_id == company_id)
    if opportunity_id:
        stmt = stmt.where(Quotation.opportunity_id == opportunity_id)
    stmt = await apply_data_scope(stmt, Quotation, current, db)

    stmt = apply_sort(stmt, Quotation, sort, order)
    rows, total = await paginate(db, stmt, page, page_size)

    company_ids = {r.company_id for r in rows}
    names: dict[uuid.UUID, str] = {}
    if company_ids:
        found = (await db.execute(select(Company.id, Company.name).where(Company.id.in_(company_ids)))).all()
        names = {c[0]: c[1] for c in found}

    items = []
    for row in rows:
        data = QuotationOut.model_validate(row).model_dump(mode="json")
        data["company_name"] = names.get(row.company_id)
        data.pop("items", None)
        items.append(data)
    return resp.page(items, total, page, page_size)


@router.post("", summary="创建报价单", status_code=201)
async def create_quotation(
    payload: QuotationCreate,
    db: DbSession,
    current: User = Depends(require_permission("quotation:create")),
) -> dict[str, Any]:
    company = (
        await db.execute(select(Company).where(Company.id == payload.company_id, Company.deleted_at.is_(None)))
    ).scalar_one_or_none()
    if company is None:
        raise NotFoundError("客户不存在")

    data = payload.model_dump(exclude_unset=True)
    items = data.pop("items", [])
    quotation = Quotation(
        **data,
        quotation_no=await next_number("quotation"),
        status="DRAFT",
        created_by=current.id,
        owner_id=current.id,
        department_id=current.department_id,
    )
    db.add(quotation)
    await db.flush()
    for item in items:
        db.add(QuotationItem(quotation_id=quotation.id, **item))
    await db.flush()
    # 币别编码：同客户出现新币别时自动追加 -1/-2…
    await company_code.add_currency_code(db, company, quotation.currency)
    await _load_items(db, quotation)
    _recalc(quotation)
    await db.commit()
    await db.refresh(quotation)
    return resp.ok(await _serialize(db, quotation))


def _allocate_unit_price(final_price: float, total_qty: float, margin_over_floor: float = 0.0) -> float:
    """M2.5-D4：对外单位价按 2 位落库，避免数量不整除时产生 4 位对外价。"""
    return round(float(final_price or 0) / (total_qty or 1) * (1 + margin_over_floor), 2)


@router.post("/from-pricing", summary="由核价记录生成报价单", status_code=201)
async def create_from_pricing(
    payload: QuotationFromPricingIn,
    db: DbSession,
    current: User = Depends(require_permission("quotation:create")),
) -> dict[str, Any]:
    pricing = await get_or_404(db, PricingRecord, payload.pricing_id, "核价记录")
    if pricing.status != "APPROVED":
        raise ApiError(message="核价记录需审批通过后才能生成报价", http_status=400)
    inquiry = await get_or_404(db, Inquiry, pricing.inquiry_id, "询价单")
    inquiry_items = list(
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

    # M2.5-D4：汇率在报价创建时快照（默认 7.25）；M2.5-D2：最终价 = base_cost×(1+利润率)×折扣率，
    # 由核价生成时按最终总价摊到单位价，并沿用核价的折扣率。
    total_qty = float(sum(float(i.quantity or 0) for i in inquiry_items) or 1)
    unit_price = _allocate_unit_price(
        pricing.final_price or pricing.suggested_price or pricing.floor_price or 0,
        total_qty,
        payload.margin_over_floor,
    )
    quotation = Quotation(
        company_id=inquiry.company_id,
        contact_id=inquiry.contact_id,
        opportunity_id=inquiry.opportunity_id,
        inquiry_id=inquiry.id,
        pricing_id=pricing.id,
        quotation_no=await next_number("quotation"),
        currency=pricing.currency,
        exchange_rate=pricing_service.DEFAULT_EXCHANGE_RATE,
        discount_rate=float(pricing.discount_rate or 1),
        incoterm=payload.incoterm,
        payment_terms=payload.payment_terms,
        valid_days=payload.valid_days,
        status="DRAFT",
        created_by=current.id,
        owner_id=current.id,
        department_id=current.department_id,
    )
    db.add(quotation)
    await db.flush()
    for item in inquiry_items:
        db.add(
            QuotationItem(
                quotation_id=quotation.id,
                product_id=item.product_id,
                sku_id=item.sku_id,
                product_name=item.product_name,
                spec=item.spec,
                quantity=item.quantity,
                unit=item.unit,
                unit_price=unit_price,
                remark=item.remark,
                sort=item.sort,
            )
        )
    await db.flush()
    await _load_items(db, quotation)
    _recalc(quotation)
    company = (await db.execute(select(Company).where(Company.id == quotation.company_id))).scalar_one_or_none()
    if company is not None:
        await company_code.add_currency_code(db, company, quotation.currency)
    await db.commit()
    await db.refresh(quotation)
    return resp.ok(await _serialize(db, quotation))


@router.get("/{quotation_id}", summary="报价详情")
async def get_quotation(
    quotation_id: uuid.UUID,
    db: DbSession,
    _: User = Depends(require_permission("quotation:view")),
) -> dict[str, Any]:
    quotation = await get_or_404(db, Quotation, quotation_id, "报价单")
    return resp.ok(await _serialize(db, quotation))


@router.put("/{quotation_id}", summary="更新报价单")
async def update_quotation(
    quotation_id: uuid.UUID,
    payload: QuotationUpdate,
    db: DbSession,
    _: User = Depends(require_permission("quotation:update")),
) -> dict[str, Any]:
    quotation = await get_or_404(db, Quotation, quotation_id, "报价单")
    if quotation.status not in {"DRAFT", "REJECTED"}:
        raise ApiError(message=f"当前状态 {quotation.status} 不可编辑", http_status=400)
    data = payload.model_dump(exclude_unset=True)
    items = data.pop("items", None)
    for key, value in data.items():
        setattr(quotation, key, value)
    if items is not None:
        await db.execute(delete(QuotationItem).where(QuotationItem.quotation_id == quotation.id))
        for item in items:
            db.add(QuotationItem(quotation_id=quotation.id, **item))
    await db.flush()
    await _load_items(db, quotation)
    _recalc(quotation)
    await db.commit()
    await db.refresh(quotation)
    return resp.ok(await _serialize(db, quotation))


@router.delete("/{quotation_id}", summary="删除报价单（软删除）")
async def delete_quotation(
    quotation_id: uuid.UUID,
    db: DbSession,
    _: User = Depends(require_permission("quotation:update")),
) -> dict[str, Any]:
    quotation = await get_or_404(db, Quotation, quotation_id, "报价单")
    quotation.deleted_at = utcnow()
    await db.commit()
    return resp.ok({"deleted": True})


# ------------------------------------------------------------------ 审批


@router.post("/{quotation_id}/submit", summary="提交报价审批")
async def submit_quotation(
    quotation_id: uuid.UUID,
    db: DbSession,
    current: User = Depends(require_permission("quotation:submit")),
) -> dict[str, Any]:
    quotation = await get_or_404(db, Quotation, quotation_id, "报价单")
    if quotation.status not in {"DRAFT", "REJECTED"}:
        raise ApiError(message=f"当前状态 {quotation.status} 不可提交", http_status=400)
    if not quotation.items:
        raise ApiError(message="报价单至少需要一条明细", http_status=400)

    # M2.6-D1：折扣率三档审批，=1 免审直接放行。
    steps = approval_service.steps_for("QUOTATION", quotation.discount_rate)
    if not steps:
        quotation.status = "APPROVED"
        quotation.approved_by = current.id
        quotation.approved_at = utcnow()
        if quotation.opportunity_id:
            opp = (
                await db.execute(select(Opportunity).where(Opportunity.id == quotation.opportunity_id))
            ).scalar_one_or_none()
            if opp is not None and opp.stage in {"PRICING", "INQUIRY", "REQUIREMENT"}:
                opp.stage = "QUOTATION"
                opp.quotation_amount = quotation.total_amount
        await db.commit()
        await db.refresh(quotation)
        data = await _serialize(db, quotation)
        data["approval_status"] = "APPROVED"
        data["approval_step"] = "免审"
        return resp.ok(data)

    instance = await approval_service.start(
        db,
        biz_type="QUOTATION",
        biz_id=quotation.id,
        biz_no=quotation.quotation_no,
        title=f"报价审批 {quotation.quotation_no}",
        amount=float(quotation.total_amount or 0),
        currency=quotation.currency,
        applicant=current,
        discount_rate=quotation.discount_rate,
    )
    quotation.status = "PENDING_APPROVAL"
    if quotation.opportunity_id:
        opp = (
            await db.execute(select(Opportunity).where(Opportunity.id == quotation.opportunity_id))
        ).scalar_one_or_none()
        if opp is not None and opp.stage in {"PRICING", "INQUIRY", "REQUIREMENT"}:
            opp.stage = "QUOTATION"
            opp.quotation_amount = quotation.total_amount
    await db.commit()
    await db.refresh(quotation)
    data = await _serialize(db, quotation)
    data["approval_id"] = str(instance.id)
    return resp.ok(data)


@router.post("/{quotation_id}/approve", summary="审批报价")
async def approve_quotation(
    quotation_id: uuid.UUID,
    db: DbSession,
    current: User = Depends(require_permission("quotation:approve")),
    comment: str | None = Query(None),
    approved: bool = Query(True),
) -> dict[str, Any]:
    quotation = await get_or_404(db, Quotation, quotation_id, "报价单")
    if quotation.status != "PENDING_APPROVAL":
        raise ApiError(message=f"当前状态 {quotation.status} 不可审批", http_status=400)

    instance = await approval_service.latest_for_biz(db, "QUOTATION", quotation.id)
    if instance is None:
        raise NotFoundError("报价审批实例不存在")

    instance = await approval_service.act(db, instance_id=instance.id, user=current, approved=approved, comment=comment)
    if instance.status == "APPROVED":
        quotation.status = "APPROVED"
        quotation.approved_by = current.id
        quotation.approved_at = utcnow()
    elif instance.status == "REJECTED":
        quotation.status = "REJECTED"

    await db.commit()
    await db.refresh(quotation)
    data = await _serialize(db, quotation)
    data["approval_status"] = instance.status
    data["approval_step"] = f"{instance.current_step}/{instance.total_steps}"
    return resp.ok(data)


# ------------------------------------------------------------------ PDF / 邮件


async def _price_list_context(db: DbSession, quotation: Quotation) -> dict[str, Any]:
    """对外价格表上下文（含产品图 base64）。"""
    import base64

    from app.models.email import File as FileModel
    from app.services.export_excel import DEFAULT_NOTES_CN, DEFAULT_NOTES_EN, DEFAULT_TERMS

    items = list(
        (
            await db.execute(
                select(QuotationItem)
                .where(
                    QuotationItem.quotation_id == quotation.id,
                    QuotationItem.deleted_at.is_(None),
                )
                .order_by(QuotationItem.sort, QuotationItem.created_at)
            )
        )
        .scalars()
        .all()
    )
    image_ids = [i.image_file_id for i in items if i.image_file_id]
    files = (
        (await db.execute(select(FileModel).where(FileModel.id.in_(image_ids)))).scalars().all() if image_ids else []
    )
    data_uri: dict[str, str] = {}
    for record in files:
        try:
            raw = storage.read_bytes(record)
            mime = record.mime or "image/png"
            data_uri[str(record.id)] = f"data:{mime};base64,{base64.b64encode(raw).decode()}"
        except Exception:  # noqa: BLE001
            continue

    company = (await db.execute(select(Company).where(Company.id == quotation.company_id))).scalar_one_or_none()
    seller = await _seller_info(db)

    return {
        "seller_name": quotation.seller_name or seller.get("name") or settings.APP_NAME,
        "seller_address": quotation.seller_address or seller.get("address") or "",
        "seller_contact": quotation.seller_contact or seller.get("contact") or "",
        "customer_name": company.name if company else "",
        "buyer_attn": f" (Attn: {quotation.buyer_attn})" if quotation.buyer_attn else "",
        "title": quotation.title or "Offer",
        "currency": quotation.currency,
        "terms": quotation.terms or DEFAULT_TERMS,
        "notes_cn": quotation.notes_cn or DEFAULT_NOTES_CN,
        "notes_en": quotation.notes_en or DEFAULT_NOTES_EN,
        "items": [
            {
                "item_no": i.item_no or i.product_name,
                "description": i.description or "\n".join(x for x in [i.spec, i.remark] if x),
                "unit_price": i.unit_price,
                "moq": i.moq,
                "power": i.power,
                "ip": i.ip,
                "lumen": i.lumen,
                "color_temp": i.color_temp,
                "color_rendering": i.color_rendering,
                "price_valid": i.price_valid or (quotation.valid_until.isoformat() if quotation.valid_until else ""),
                "picture": data_uri.get(str(i.image_file_id)) if i.image_file_id else None,
            }
            for i in items
        ],
    }


@router.post("/{quotation_id}/generate-pdf", summary="生成报价单 PDF（对外价格表）")
async def generate_pdf(
    quotation_id: uuid.UUID,
    db: DbSession,
    current: User = Depends(require_permission("quotation:pdf")),
) -> dict[str, Any]:
    quotation = await get_or_404(db, Quotation, quotation_id, "报价单")
    # M2.6-D4：未批不得生成/导出报价单。
    if quotation.status not in {"APPROVED", "SENT", "ACCEPTED"}:
        raise ApiError(message="报价单需审批通过后方可生成 PDF", http_status=400)
    context = await _price_list_context(db, quotation)
    data, engine = pdf_service.build_price_list_pdf(context)
    filename = f"{quotation.quotation_no}.pdf"
    record = await storage.save_bytes(
        db,
        filename=filename,
        data=data,
        mime="application/pdf",
        module="quotation",
        biz_id=quotation.id,
        uploader_id=current.id,
    )
    quotation.pdf_file_id = record.id
    await db.commit()
    return resp.ok(
        {
            "ok": True,
            "detail": f"PDF 已生成（{engine}）",
            "file_id": str(record.id),
            "filename": filename,
            "size": len(data),
        }
    )


@router.get("/{quotation_id}/export-excel", summary="导出报价单 Excel（价格表）")
async def export_quotation_excel(
    quotation_id: uuid.UUID,
    db: DbSession,
    _: User = Depends(require_permission("quotation:view")),
) -> Response:
    quotation = await get_or_404(db, Quotation, quotation_id, "报价单")
    # M2.6-D4：未批不得生成/导出报价单。
    if quotation.status not in {"APPROVED", "SENT", "ACCEPTED"}:
        raise ApiError(message="报价单需审批通过后方可导出 Excel", http_status=400)
    if not quotation.terms:
        from app.services.export_excel import DEFAULT_NOTES_CN, DEFAULT_NOTES_EN, DEFAULT_TERMS

        quotation.terms = DEFAULT_TERMS
        quotation.notes_cn = quotation.notes_cn or DEFAULT_NOTES_CN
        quotation.notes_en = quotation.notes_en or DEFAULT_NOTES_EN
        await db.commit()
    data = await export_excel.build_quotation_workbook(db, quotation, seller_default=await _seller_info(db))
    filename = f"{quotation.quotation_no}.xlsx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{quotation_id}/pdf", summary="下载报价单 PDF")
async def download_pdf(
    quotation_id: uuid.UUID,
    db: DbSession,
    _: User = Depends(require_permission("quotation:view")),
) -> Response:
    quotation = await get_or_404(db, Quotation, quotation_id, "报价单")
    if not quotation.pdf_file_id:
        raise NotFoundError("PDF 尚未生成")
    record = (await db.execute(select(File).where(File.id == quotation.pdf_file_id))).scalar_one_or_none()
    if record is None:
        raise NotFoundError("PDF 文件不存在")
    return Response(
        content=storage.read_bytes(record),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{quotation.quotation_no}.pdf"'},
    )


@router.post("/{quotation_id}/send-email", summary="发送报价邮件")
async def send_quotation_email(
    quotation_id: uuid.UUID,
    db: DbSession,
    current: User = Depends(require_permission("quotation:send")),
    account_id: uuid.UUID | None = Query(None),
    to_addrs: str | None = Query(None, description="逗号分隔，缺省取联系人邮箱"),
    subject: str | None = Query(None),
    body: str | None = Query(None),
) -> dict[str, Any]:
    quotation = await get_or_404(db, Quotation, quotation_id, "报价单")
    if quotation.status not in {"APPROVED", "SENT", "ACCEPTED"}:
        raise ApiError(message="报价单需审批通过后方可发送", http_status=400)

    company = (await db.execute(select(Company).where(Company.id == quotation.company_id))).scalar_one_or_none()
    contact = None
    if quotation.contact_id:
        contact = (await db.execute(select(Contact).where(Contact.id == quotation.contact_id))).scalar_one_or_none()
    if contact is None and company is not None:
        contact = (
            (
                await db.execute(
                    select(Contact)
                    .where(Contact.company_id == company.id, Contact.deleted_at.is_(None))
                    .order_by(Contact.is_primary.desc())
                )
            )
            .scalars()
            .first()
        )

    recipients = [t.strip() for t in (to_addrs or "").split(",") if t.strip()]
    if not recipients and contact and contact.email:
        recipients = [contact.email]
    if not recipients:
        raise ApiError(message="未找到收件人邮箱，请填写联系人或手动指定", http_status=400)

    account = await email_service.get_account(db, account_id, current.id)

    if quotation.pdf_file_id:
        record = (await db.execute(select(File).where(File.id == quotation.pdf_file_id))).scalar_one_or_none()
        if record is not None:
            attachments = [(f"{quotation.quotation_no}.pdf", storage.read_bytes(record), "application/pdf")]
        else:
            attachments = []
    else:
        context = await _build_pdf_context(db, quotation)
        data, _engine = pdf_service.build_quotation_pdf(context)
        attachments = [(f"{quotation.quotation_no}.pdf", data, "application/pdf")]

    final_subject = subject or f"Quotation {quotation.quotation_no} - {company.name if company else ''}".strip()
    final_body = body or (
        f"Dear {contact.name if contact else 'Sir/Madam'},\n\n"
        f"Please find our quotation {quotation.quotation_no} in attachment.\n"
        f"Total amount: {quotation.currency} {float(quotation.total_amount or 0):,.2f}\n"
        f"Valid until: {quotation.valid_until or ''}\n\n"
        f"Best regards,\n{current.name}"
    )

    message = await email_service.send(
        db,
        account=account,
        to_addrs=recipients,
        cc_addrs=[],
        subject=final_subject,
        body=final_body,
        attachments=attachments,
        company_id=quotation.company_id,
        contact_id=quotation.contact_id,
        opportunity_id=quotation.opportunity_id,
        user_id=current.id,
        sender_name=current.name,
    )
    quotation.status = "SENT"
    quotation.sent_at = utcnow()
    await db.commit()

    return resp.ok(
        {
            "message_id": str(message.id),
            "send_status": message.send_status,
            "to": recipients,
            "simulated": email_service.is_simulated(account),
            "subject": final_subject,
        }
    )


@router.get("/{quotation_id}/price-summary", summary="报价毛利概览")
async def price_summary(
    quotation_id: uuid.UUID,
    db: DbSession,
    current: CurrentUser,
) -> dict[str, Any]:
    quotation = await get_or_404(db, Quotation, quotation_id, "报价单")
    pricing = None
    if quotation.pricing_id:
        pricing = (
            await db.execute(select(PricingRecord).where(PricingRecord.id == quotation.pricing_id))
        ).scalar_one_or_none()

    can_cost = current.is_superuser or "pricing:cost_view" in current.permission_codes
    result: dict[str, Any] = {
        "total_amount": float(quotation.total_amount or 0),
        "currency": quotation.currency,
        "cost": None,
        "gross_margin": None,
    }
    if pricing is not None and can_cost:
        cost = float(pricing.total_cost or 0)
        total = float(quotation.total_amount or 0)
        result["cost"] = cost
        result["gross_margin"] = round((total - cost) / total, 4) if total else None
    return resp.ok(result)
