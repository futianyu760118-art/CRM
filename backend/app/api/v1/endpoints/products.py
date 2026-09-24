"""M3 产品 / SKU 接口。"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import Depends
from sqlalchemy import select

from app.api.crud import CrudConfig, build_crud_router
from app.core import response as resp
from app.core.deps import DbSession, require_permission
from app.core.exceptions import ConflictError, NotFoundError
from app.models.business import Product, Sku
from app.models.user import User
from app.schemas.business import (
    ProductCreate,
    ProductOut,
    ProductUpdate,
    SkuCreate,
    SkuOut,
    SkuUpdate,
)
from app.services.query import get_or_404

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
