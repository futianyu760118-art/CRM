"""M3 产品 / SKU / 产品资料 / 标准报价接口（PAND-316 PROD-01~03）。"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy import select

from app.api.crud import CrudConfig, build_crud_router
from app.core import response as resp
from app.core.deps import DbSession, require_permission
from app.core.error_codes import ErrCode
from app.core.exceptions import ApiError, ConflictError, NotFoundError
from app.domain import dictionaries as dic
from app.models.business import Product, ProductDocument, Sku, StandardQuote
from app.models.user import User
from app.schemas.business import (
    ProductCreate,
    ProductDocumentGroupOut,
    ProductDocumentOut,
    ProductDocumentVersionIn,
    ProductOut,
    ProductUpdate,
    SkuCreate,
    SkuOut,
    SkuUpdate,
    StandardQuoteCreate,
    StandardQuoteOut,
    StandardQuoteSelectIn,
)
from app.services import product_assets, storage
from app.services.query import get_or_404, name_map, soft_delete

router = build_crud_router(
    CrudConfig(
        model=Product,
        prefix="/products",
        tag="M3-产品",
        name="产品",
        create_schema=ProductCreate,
        update_schema=ProductUpdate,
        out_schema=ProductOut,
        view_permission="product:view",
        create_permission="product:create",
        update_permission="product:update",
        delete_permission="product:delete",
        search_fields=("name", "name_en", "code", "category"),
        filter_fields={"category": "category", "status": "status"},
        scope=False,
        description="产品 CRUD，响应内联 SKU 列表",
    )
)

quotes_router = APIRouter(prefix="/standard-quotes", tags=["M3-标准报价"])


def _bad(message: str) -> ApiError:
    return ApiError(ErrCode.VALIDATION_ERROR, message, http_status=400)


# ------------------------------------------------------------------ 产品资料
def _doc_out(doc: ProductDocument, uploader_name: str | None = None) -> dict[str, Any]:
    return ProductDocumentOut(
        id=doc.id,
        product_id=doc.product_id,
        doc_type=doc.doc_type,
        doc_type_label=dic.PRODUCT_DOC_TYPES.get(doc.doc_type, doc.doc_type),
        version_no=doc.version_no,
        filename=doc.filename,
        size=doc.size,
        is_current=doc.is_current,
        file_id=doc.file_id,
        uploader_name=uploader_name,
        created_at=doc.created_at,
    ).model_dump(mode="json")


@router.post("/{product_id}/documents", summary="上传产品资料", status_code=201)
async def upload_document(
    product_id: uuid.UUID,
    db: DbSession,
    file: UploadFile = File(...),
    doc_type: str = Form(...),
    version_no: str | None = Form(None),
    current: User = Depends(require_permission("product:update")),
) -> dict[str, Any]:
    product = await get_or_404(db, Product, product_id, "产品")
    if doc_type not in dic.PRODUCT_DOC_TYPES:
        raise _bad(f"资料类型：仅可选 {dic.labels_text(dic.PRODUCT_DOC_TYPES)}")

    filename = file.filename or "资料"
    data = await file.read()
    try:
        product_assets.validate_upload(filename, len(data))
    except ValueError as exc:
        raise _bad(f"文件：{exc}") from exc

    existing = (
        (
            await db.execute(
                select(ProductDocument).where(
                    ProductDocument.product_id == product.id,
                    ProductDocument.doc_type == doc_type,
                )
            )
        )
        .scalars()
        .all()
    )
    used_versions = {d.version_no for d in existing}
    try:
        version = product_assets.validate_version(version_no) if version_no else ""
    except ValueError as exc:
        raise _bad(f"版本号：{exc}") from exc
    if not version:
        version = product_assets.next_version_no(used_versions)
    if version in used_versions:
        raise ConflictError(f"版本号：{version} 已存在，请更换版本号")

    record = await storage.save_bytes(
        db,
        filename=filename,
        data=data,
        mime=file.content_type,
        module="product_doc",
        biz_id=product.id,
        uploader_id=current.id,
    )
    doc = ProductDocument(
        product_id=product.id,
        doc_type=doc_type,
        version_no=version,
        file_id=record.id,
        filename=filename,
        size=len(data),
        owner_id=current.id,
        department_id=current.department_id,
    )
    db.add(doc)
    await db.flush()
    await product_assets.recompute_current(db, product.id, doc_type)
    await db.commit()
    await db.refresh(doc)
    return resp.ok(_doc_out(doc, current.name))


@router.get("/{product_id}/documents", summary="产品资料（按 4 类分组）")
async def list_documents(
    product_id: uuid.UUID,
    db: DbSession,
    _: User = Depends(require_permission("product:view")),
) -> dict[str, Any]:
    product = await get_or_404(db, Product, product_id, "产品")
    docs = (
        (
            await db.execute(
                select(ProductDocument).where(
                    ProductDocument.product_id == product.id,
                    ProductDocument.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    uploaders = await name_map(db, User, {d.owner_id for d in docs})
    groups = []
    for code, label in dic.PRODUCT_DOC_TYPES.items():
        items = sorted(
            (d for d in docs if d.doc_type == code),
            key=lambda d: product_assets.version_key(d.version_no),
            reverse=True,
        )
        groups.append(
            ProductDocumentGroupOut(
                doc_type=code,
                doc_type_label=label,
                count=len(items),
                latest_version=items[0].version_no if items else None,
                documents=[_doc_out(d, uploaders.get(d.owner_id)) for d in items],
            ).model_dump(mode="json")
        )
    return resp.ok(groups)


async def _get_doc(db: DbSession, product_id: uuid.UUID, doc_id: uuid.UUID) -> ProductDocument:
    doc = (
        await db.execute(
            select(ProductDocument).where(
                ProductDocument.id == doc_id,
                ProductDocument.product_id == product_id,
                ProductDocument.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if doc is None:
        raise NotFoundError("资料不存在")
    return doc


@router.put("/{product_id}/documents/{doc_id}", summary="修改资料版本号")
async def update_document(
    product_id: uuid.UUID,
    doc_id: uuid.UUID,
    payload: ProductDocumentVersionIn,
    db: DbSession,
    _: User = Depends(require_permission("product:update")),
) -> dict[str, Any]:
    doc = await _get_doc(db, product_id, doc_id)
    try:
        version = product_assets.validate_version(payload.version_no)
    except ValueError as exc:
        raise _bad(f"版本号：{exc}") from exc
    if version != doc.version_no:
        duplicated = (
            await db.execute(
                select(ProductDocument.id).where(
                    ProductDocument.product_id == doc.product_id,
                    ProductDocument.doc_type == doc.doc_type,
                    ProductDocument.version_no == version,
                    ProductDocument.id != doc.id,
                )
            )
        ).scalar_one_or_none()
        if duplicated:
            raise ConflictError(f"版本号：{version} 已存在，请更换版本号")
        doc.version_no = version
        await db.flush()
        await product_assets.recompute_current(db, doc.product_id, doc.doc_type)
    await db.commit()
    await db.refresh(doc)
    return resp.ok(_doc_out(doc))


@router.delete("/{product_id}/documents/{doc_id}", summary="删除资料（软删除）")
async def delete_document(
    product_id: uuid.UUID,
    doc_id: uuid.UUID,
    db: DbSession,
    _: User = Depends(require_permission("product:update")),
) -> dict[str, Any]:
    doc = await _get_doc(db, product_id, doc_id)
    doc_type = doc.doc_type
    soft_delete(doc)
    await db.flush()
    await product_assets.recompute_current(db, product_id, doc_type)
    await db.commit()
    return resp.ok({"deleted": True})


# ------------------------------------------------------------------ 标准报价
def _quote_out(quote: StandardQuote) -> dict[str, Any]:
    today = date.today()
    status = product_assets.quote_status(quote.status, quote.valid_from, quote.valid_to, today)
    return StandardQuoteOut(
        id=quote.id,
        product_id=quote.product_id,
        currency=quote.currency,
        currency_label=dic.CURRENCIES.get(quote.currency, quote.currency),
        qty_from=quote.qty_from,
        qty_to=quote.qty_to,
        interval_label=product_assets.interval_text(quote.qty_from, quote.qty_to),
        unit_price=float(quote.unit_price),
        valid_from=quote.valid_from,
        valid_to=quote.valid_to,
        version_no=quote.version_no,
        status=status,
        status_label=product_assets.QUOTE_LABELS[status],
        created_at=quote.created_at,
    ).model_dump(mode="json")


async def _product_quotes(db: DbSession, product_id: uuid.UUID) -> list[StandardQuote]:
    return (
        (
            await db.execute(
                select(StandardQuote)
                .where(
                    StandardQuote.product_id == product_id,
                    StandardQuote.deleted_at.is_(None),
                )
                .order_by(StandardQuote.created_at.desc())
            )
        )
        .scalars()
        .all()
    )


@router.post("/{product_id}/standard-quotes", summary="新建标准报价", status_code=201)
async def create_standard_quote(
    product_id: uuid.UUID,
    payload: StandardQuoteCreate,
    db: DbSession,
    current: User = Depends(require_permission("product:update")),
) -> dict[str, Any]:
    product = await get_or_404(db, Product, product_id, "产品")
    try:
        version = product_assets.validate_version(payload.version_no)
    except ValueError as exc:
        raise _bad(f"版本号：{exc}") from exc
    try:
        price = product_assets.normalize_price(payload.unit_price)
    except ValueError as exc:
        raise _bad(f"单价：{exc}") from exc
    if payload.qty_to is not None and payload.qty_to <= payload.qty_from:
        raise _bad("数量区间：止数量应大于起数量")
    if payload.valid_to < payload.valid_from:
        raise _bad("有效期：止日期不得早于起日期")

    duplicated = (
        await db.execute(
            select(StandardQuote.id).where(
                StandardQuote.product_id == product.id,
                StandardQuote.currency == payload.currency,
                StandardQuote.version_no == version,
            )
        )
    ).scalar_one_or_none()
    if duplicated:
        raise ConflictError(f"版本号：{version} 已存在，请更换版本号")

    existing = [q for q in await _product_quotes(db, product.id) if q.currency == payload.currency]
    overlap = product_assets.find_overlap(existing, payload.qty_from, payload.qty_to)
    if overlap is not None:
        raise ConflictError(
            f"数量区间：{product_assets.interval_text(payload.qty_from, payload.qty_to)} 与版本 "
            f"{overlap.version_no} 的 {product_assets.interval_text(overlap.qty_from, overlap.qty_to)} 重叠"
        )

    quote = StandardQuote(
        product_id=product.id,
        currency=payload.currency,
        qty_from=payload.qty_from,
        qty_to=payload.qty_to,
        unit_price=price,
        valid_from=payload.valid_from,
        valid_to=payload.valid_to,
        version_no=version,
        status=product_assets.QUOTE_ACTIVE,
        owner_id=current.id,
        department_id=current.department_id,
    )
    db.add(quote)
    await db.commit()
    await db.refresh(quote)
    return resp.ok(_quote_out(quote))


@router.get("/{product_id}/standard-quotes", summary="标准报价列表")
async def list_standard_quotes(
    product_id: uuid.UUID,
    db: DbSession,
    _: User = Depends(require_permission("product:view")),
    currency: str | None = Query(None),
    status: str | None = Query(None, description="生效中/已过期/未生效/已停用"),
) -> dict[str, Any]:
    await get_or_404(db, Product, product_id, "产品")
    items = [_quote_out(q) for q in await _product_quotes(db, product_id)]
    label_to_status = {label: code for code, label in product_assets.QUOTE_LABELS.items()}
    wanted = label_to_status.get(status, status) if status else None
    if currency:
        items = [x for x in items if x["currency"] == currency]
    if wanted:
        items = [x for x in items if x["status"] == wanted]
    return resp.ok(items)


@router.post("/{product_id}/standard-quotes/select", summary="按币种+数量选择标准报价")
async def select_standard_quote(
    product_id: uuid.UUID,
    payload: StandardQuoteSelectIn,
    db: DbSession,
    _: User = Depends(require_permission("product:view")),
) -> dict[str, Any]:
    await get_or_404(db, Product, product_id, "产品")
    today = date.today()
    matches = [
        q
        for q in await _product_quotes(db, product_id)
        if q.currency == payload.currency
        and product_assets.quote_status(q.status, q.valid_from, q.valid_to, today) == product_assets.QUOTE_ACTIVE
        and q.qty_from <= payload.quantity
        and (q.qty_to is None or payload.quantity < q.qty_to)
    ]
    if not matches:
        raise NotFoundError("无适用的标准报价")
    best = max(matches, key=lambda q: product_assets.version_key(q.version_no))
    return resp.ok(_quote_out(best))


@quotes_router.post("/{quote_id}/disable", summary="停用标准报价（不改价）")
async def disable_standard_quote(
    quote_id: uuid.UUID,
    db: DbSession,
    _: User = Depends(require_permission("product:update")),
) -> dict[str, Any]:
    quote = (
        await db.execute(
            select(StandardQuote).where(
                StandardQuote.id == quote_id,
                StandardQuote.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if quote is None:
        raise NotFoundError("标准报价不存在")
    quote.status = product_assets.QUOTE_DISABLED
    await db.commit()
    await db.refresh(quote)
    return resp.ok(_quote_out(quote))


# ------------------------------------------------------------------ SKU
@router.post("/{product_id}/skus", summary="新增 SKU", status_code=201)
async def create_sku(
    product_id: uuid.UUID,
    payload: SkuCreate,
    db: DbSession,
    _: User = Depends(require_permission("product:update")),
) -> dict[str, Any]:
    product = await get_or_404(db, Product, product_id, "产品")
    exists = (await db.execute(select(Sku.id).where(Sku.code == payload.code))).scalar_one_or_none()
    if exists:
        raise ConflictError("SKU 编码已存在")
    sku = Sku(**payload.model_dump(exclude_unset=True), product_id=product.id)
    db.add(sku)
    await db.commit()
    await db.refresh(sku)
    return resp.ok(SkuOut.model_validate(sku).model_dump(mode="json"))


@router.put("/skus/{sku_id}", summary="更新 SKU")
async def update_sku(
    sku_id: uuid.UUID,
    payload: SkuUpdate,
    db: DbSession,
    _: User = Depends(require_permission("product:update")),
) -> dict[str, Any]:
    sku = (await db.execute(select(Sku).where(Sku.id == sku_id, Sku.deleted_at.is_(None)))).scalar_one_or_none()
    if sku is None:
        raise NotFoundError("SKU 不存在")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(sku, key, value)
    await db.commit()
    await db.refresh(sku)
    return resp.ok(SkuOut.model_validate(sku).model_dump(mode="json"))
