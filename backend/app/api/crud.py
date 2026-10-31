"""通用 CRUD 路由工厂。

覆盖「列表 / 详情 / 新建 / 更新 / 软删除」五类标准接口，
统一处理：权限校验、DataScope、分页排序、软删除过滤、序列化补全。
各业务模块在此基础上追加自定义动作（转客户、阶段流转、提交审批等）。

注意：本模块刻意不使用 `from __future__ import annotations`，
因为 FastAPI 需要在运行时解析 `payload: cfg.create_schema` 这类动态注解。
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import response as resp
from app.core.deps import DbSession, require_permission
from app.models.user import User
from app.services.data_scope import apply_data_scope
from app.services.query import apply_sort, get_or_404, paginate, soft_delete

EnrichFn = Callable[[AsyncSession, list[Any]], Awaitable[list[dict[str, Any]]]]


@dataclass
class CrudConfig:
    model: Any
    prefix: str
    tag: str
    name: str
    create_schema: type[BaseModel]
    update_schema: type[BaseModel]
    out_schema: type[BaseModel]
    view_permission: str
    create_permission: str | None = None
    update_permission: str | None = None
    delete_permission: str | None = None
    search_fields: tuple[str, ...] = ()
    filter_fields: dict[str, str] = field(default_factory=dict)
    order_field: str = "created_at"
    scope: bool = True
    enrich: EnrichFn | None = None
    description: str = ""


def _serialize(cfg: CrudConfig, row: Any) -> dict[str, Any]:
    return cfg.out_schema.model_validate(row).model_dump(mode="json")


async def _enriched(cfg: CrudConfig, db: AsyncSession, rows: list[Any]) -> list[dict[str, Any]]:
    if cfg.enrich is None:
        return [_serialize(cfg, r) for r in rows]
    return await cfg.enrich(db, rows)


def build_crud_router(cfg: CrudConfig) -> APIRouter:
    router = APIRouter(prefix=cfg.prefix, tags=[cfg.tag])
    view_dep = Depends(require_permission(cfg.view_permission))
    create_dep = Depends(require_permission(cfg.create_permission or cfg.view_permission))
    update_dep = Depends(require_permission(cfg.update_permission or cfg.view_permission))
    delete_dep = Depends(require_permission(cfg.delete_permission or cfg.update_permission or cfg.view_permission))

    @router.get("", summary=f"{cfg.name}列表", description=cfg.description)
    async def list_items(
        request: Request,
        db: DbSession,
        _: User = view_dep,
        keyword: str | None = Query(None, description="关键词搜索"),
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=200),
        sort: str = Query("created_at"),
        order: str = Query("desc", pattern="^(asc|desc)$"),
    ) -> dict[str, Any]:
        stmt: Any = select(cfg.model).where(cfg.model.deleted_at.is_(None))

        query = request.query_params
        for param, column_name in cfg.filter_fields.items():
            value = query.get(param)
            if value in (None, ""):
                continue
            column = getattr(cfg.model, column_name, None)
            if column is None:
                continue
            stmt = stmt.where(column == value)

        if keyword and cfg.search_fields:
            like = f"%{keyword}%"
            stmt = stmt.where(or_(*[getattr(cfg.model, f).ilike(like) for f in cfg.search_fields]))

        if cfg.scope:
            stmt = await apply_data_scope(stmt, cfg.model, _, db)

        stmt = apply_sort(stmt, cfg.model, sort or cfg.order_field, order)
        rows, total = await paginate(db, stmt, page, page_size)
        items = await _enriched(cfg, db, rows)
        return resp.page(items, total, page, page_size)

    @router.post("", summary=f"新建{cfg.name}", status_code=201)
    async def create_item(
        payload: cfg.create_schema,  # type: ignore[name-defined]
        db: DbSession,
        current: User = create_dep,
    ) -> dict[str, Any]:
        data = payload.model_dump(exclude_unset=True)
        row = cfg.model(**data)
        if cfg.scope:
            if getattr(row, "owner_id", None) is None:
                row.owner_id = current.id
            if getattr(row, "department_id", None) is None:
                row.department_id = current.department_id
        db.add(row)
        await db.commit()
        await db.refresh(row)
        items = await _enriched(cfg, db, [row])
        return resp.ok(items[0])

    @router.get("/{item_id}", summary=f"{cfg.name}详情")
    async def get_item(
        item_id: uuid.UUID,
        db: DbSession,
        current: User = view_dep,
    ) -> dict[str, Any]:
        row = await get_or_404(db, cfg.model, item_id, cfg.name)
        if cfg.scope:
            scope_type, dept_ids = await _scope(current, db)
            if not _visible(scope_type, dept_ids, row, current):
                from app.core.exceptions import ForbiddenError

                raise ForbiddenError("无权访问该数据")
        items = await _enriched(cfg, db, [row])
        return resp.ok(items[0])

    @router.put("/{item_id}", summary=f"更新{cfg.name}")
    async def update_item(
        item_id: uuid.UUID,
        payload: cfg.update_schema,  # type: ignore[name-defined]
        db: DbSession,
        _: User = update_dep,
    ) -> dict[str, Any]:
        row = await get_or_404(db, cfg.model, item_id, cfg.name)
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(row, key, value)
        await db.commit()
        await db.refresh(row)
        items = await _enriched(cfg, db, [row])
        return resp.ok(items[0])

    @router.delete("/{item_id}", summary=f"删除{cfg.name}（软删除）")
    async def remove_item(
        item_id: uuid.UUID,
        db: DbSession,
        _: User = delete_dep,
    ) -> dict[str, Any]:
        row = await get_or_404(db, cfg.model, item_id, cfg.name)
        soft_delete(row)
        await db.commit()
        return resp.ok({"deleted": True})

    return router


async def _scope(user: User, db: AsyncSession) -> tuple[str, list[uuid.UUID]]:
    from app.services.data_scope import get_user_scope

    return await get_user_scope(user, db)


def _visible(scope_type: str, dept_ids: list[uuid.UUID], row: Any, user: User) -> bool:
    if scope_type == "ALL":
        return True
    owner_id = getattr(row, "owner_id", None)
    department_id = getattr(row, "department_id", None)
    if scope_type == "SELF":
        return owner_id == user.id
    if scope_type in {"DEPT", "DEPT_AND_CHILD", "CUSTOM"}:
        return owner_id == user.id or (department_id is not None and department_id in dept_ids)
    return True
