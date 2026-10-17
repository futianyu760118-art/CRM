"""销售中心-报价库接口（AC-M3）。"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select

from app.core import response as resp
from app.core.deps import DbSession, require_permission
from app.core.exceptions import ConflictError
from app.domain.state_machine import QUOTE_LIBRARY_CERTIFICATE_LEVELS
from app.models.sales import QuoteLibrary
from app.models.user import User
from app.schemas.sales import QuoteLibraryCreate, QuoteLibraryOut, QuoteLibraryUpdate
from app.services import ebms_sync
from app.services.query import apply_sort, get_or_404, paginate, soft_delete

router = APIRouter(prefix="/quote-library", tags=["销售中心-报价库"])


def _out(row: QuoteLibrary) -> dict[str, Any]:
    return QuoteLibraryOut.model_validate(row).model_dump(mode="json")


@router.get("", summary="报价库列表")
async def list_quotes(
    db: DbSession,
    _: User = Depends(require_permission("quote:view")),
    keyword: str | None = Query(None, description="外部型号/产品名/类目/内部型号"),
    certificate_level: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    sort: str = "created_at",
    order: str = Query("desc", pattern="^(asc|desc)$"),
) -> dict[str, Any]:
    stmt = select(QuoteLibrary).where(QuoteLibrary.deleted_at.is_(None))
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(
            or_(
                QuoteLibrary.external_model.ilike(like),
                QuoteLibrary.product_name.ilike(like),
                QuoteLibrary.category.ilike(like),
                QuoteLibrary.internal_model.ilike(like),
            )
        )
    if certificate_level:
        stmt = stmt.where(QuoteLibrary.certificate_level == certificate_level)
    stmt = apply_sort(stmt, QuoteLibrary, sort, order)
    rows, total = await paginate(db, stmt, page, page_size)
    return resp.page([_out(r) for r in rows], total, page, page_size)


@router.get("/stats", summary="报价库统计（按证书等级/类目）")
async def quote_stats(
    db: DbSession,
    _: User = Depends(require_permission("quote:view")),
) -> dict[str, Any]:
    cert_rows = (
        await db.execute(
            select(QuoteLibrary.certificate_level, func.count())
            .where(QuoteLibrary.deleted_at.is_(None))
            .group_by(QuoteLibrary.certificate_level)
        )
    ).all()
    cat_rows = (
        await db.execute(
            select(QuoteLibrary.category, func.count())
            .where(QuoteLibrary.deleted_at.is_(None), QuoteLibrary.category.isnot(None))
            .group_by(QuoteLibrary.category)
        )
    ).all()
    return resp.ok(
        {
            "by_certificate_level": {c: int(n) for c, n in cert_rows},
            "by_category": {c: int(n) for c, n in cat_rows},
        }
    )


@router.post("", summary="新建报价库条目", status_code=201)
async def create_quote(
    payload: QuoteLibraryCreate,
    db: DbSession,
    current: User = Depends(require_permission("quote:manage")),
) -> dict[str, Any]:
    cert = payload.certificate_level or ""
    if cert and cert not in QUOTE_LIBRARY_CERTIFICATE_LEVELS:
        raise ConflictError(f"非法证书等级: {cert}")
    exists = (
        await db.execute(
            select(QuoteLibrary).where(
                QuoteLibrary.external_model == payload.external_model,
                QuoteLibrary.certificate_level == cert,
                QuoteLibrary.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if exists is not None:
        raise ConflictError("该外部型号 + 证书等级已存在")
    row = QuoteLibrary(**payload.model_dump(exclude_unset=True), creator=current.name)
    db.add(row)
    await db.flush()
    await ebms_sync.emit_upsert(db, "QuoteLibrary", row)
    await db.commit()
    await db.refresh(row)
    return resp.ok(_out(row))


@router.get("/{quote_id}", summary="报价库条目详情")
async def get_quote(
    quote_id: uuid.UUID,
    db: DbSession,
    _: User = Depends(require_permission("quote:view")),
) -> dict[str, Any]:
    row = await get_or_404(db, QuoteLibrary, quote_id, "报价库条目")
    return resp.ok(_out(row))


@router.put("/{quote_id}", summary="更新报价库条目")
async def update_quote(
    quote_id: uuid.UUID,
    payload: QuoteLibraryUpdate,
    db: DbSession,
    _: User = Depends(require_permission("quote:manage")),
) -> dict[str, Any]:
    row = await get_or_404(db, QuoteLibrary, quote_id, "报价库条目")
    data = payload.model_dump(exclude_unset=True)
    cert = data.get("certificate_level")
    if cert and cert not in QUOTE_LIBRARY_CERTIFICATE_LEVELS:
        raise ConflictError(f"非法证书等级: {cert}")
    for key, value in data.items():
        setattr(row, key, value)
    await db.flush()
    await ebms_sync.emit_upsert(db, "QuoteLibrary", row)
    await db.commit()
    await db.refresh(row)
    return resp.ok(_out(row))


@router.delete("/{quote_id}", summary="删除报价库条目（软删除）")
async def delete_quote(
    quote_id: uuid.UUID,
    db: DbSession,
    _: User = Depends(require_permission("quote:delete")),
) -> dict[str, Any]:
    row = await get_or_404(db, QuoteLibrary, quote_id, "报价库条目")
    soft_delete(row)
    await db.flush()
    await ebms_sync.emit_delete(db, "QuoteLibrary", row)
    await db.commit()
    return resp.ok({"deleted": True})
