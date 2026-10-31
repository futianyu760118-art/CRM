"""数据字典与功能开关接口。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.core import response as resp
from app.core.deps import CurrentUser, DbSession, require_permission
from app.core.exceptions import ConflictError, NotFoundError
from app.models.support import Dictionary, FeatureFlag
from app.models.user import User
from app.schemas.system import (
    DictionaryCreate,
    DictionaryOut,
    FeatureFlagOut,
    FeatureFlagUpdate,
)
from app.services import feature_flag as flag_service

dict_router = APIRouter(prefix="/dictionaries", tags=["系统-字典"])
flag_router = APIRouter(prefix="/feature-flags", tags=["系统-功能开关"])


@dict_router.get("", summary="字典列表")
async def list_dictionaries(
    db: DbSession,
    _: CurrentUser,
    dict_type: str | None = Query(None),
):
    stmt = select(Dictionary).where(Dictionary.deleted_at.is_(None))
    if dict_type:
        stmt = stmt.where(Dictionary.dict_type == dict_type)
    stmt = stmt.order_by(Dictionary.dict_type, Dictionary.sort)
    items = (await db.execute(stmt)).scalars().all()
    return resp.ok([DictionaryOut.model_validate(d).model_dump(mode="json") for d in items])


@dict_router.get("/types", summary="字典类型列表")
async def list_dict_types(db: DbSession, _: CurrentUser):
    stmt = select(Dictionary.dict_type).where(Dictionary.deleted_at.is_(None)).distinct()
    types = (await db.execute(stmt)).scalars().all()
    return resp.ok(sorted(types))


@dict_router.post("", summary="创建字典项", status_code=201)
async def create_dictionary(
    payload: DictionaryCreate,
    db: DbSession,
    _: User = Depends(require_permission("dictionary:view")),
):
    dup = (
        await db.execute(
            select(Dictionary.id).where(
                Dictionary.dict_type == payload.dict_type,
                Dictionary.value == payload.value,
                Dictionary.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if dup:
        raise ConflictError("同类型下字典值已存在")
    item = Dictionary(**payload.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return resp.ok(DictionaryOut.model_validate(item).model_dump(mode="json"))


@dict_router.delete("/{item_id}", summary="删除字典项")
async def delete_dictionary(
    item_id: uuid.UUID,
    db: DbSession,
    _: User = Depends(require_permission("dictionary:view")),
):
    from datetime import UTC, datetime

    item = (
        await db.execute(select(Dictionary).where(Dictionary.id == item_id, Dictionary.deleted_at.is_(None)))
    ).scalar_one_or_none()
    if item is None:
        raise NotFoundError("字典项不存在")
    item.deleted_at = datetime.now(UTC)
    await db.commit()
    return resp.ok({"deleted": True})


@flag_router.get("", summary="功能开关列表")
async def list_flags(db: DbSession, _: User = Depends(require_permission("feature_flag:view"))):
    items = (
        (await db.execute(select(FeatureFlag).where(FeatureFlag.deleted_at.is_(None)).order_by(FeatureFlag.code)))
        .scalars()
        .all()
    )
    return resp.ok([FeatureFlagOut.model_validate(f).model_dump(mode="json") for f in items])


@flag_router.put("/{code}", summary="切换功能开关")
async def update_flag(
    code: str,
    payload: FeatureFlagUpdate,
    db: DbSession,
    _: User = Depends(require_permission("feature_flag:update")),
):
    flag = (
        await db.execute(select(FeatureFlag).where(FeatureFlag.code == code, FeatureFlag.deleted_at.is_(None)))
    ).scalar_one_or_none()
    if flag is None:
        raise NotFoundError("功能开关不存在")
    flag.enabled = payload.enabled
    await db.commit()
    await flag_service.invalidate_cache()
    return resp.ok({"code": code, "enabled": flag.enabled})
