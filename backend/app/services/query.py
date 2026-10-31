"""查询辅助：分页、排序、软删除过滤。"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.core.exceptions import NotFoundError
from app.db.base import utcnow

_ALLOWED_ORDERS = {"asc", "desc"}


def sortable_column(model: Any, name: str, default: str = "created_at") -> InstrumentedAttribute:
    column = getattr(model, name, None)
    if column is None or not isinstance(column, InstrumentedAttribute):
        column = getattr(model, default, None)
    if column is None:
        raise AttributeError(f"{model.__name__} 无可排序字段 {name}/{default}")
    return column


def apply_sort(stmt: Select, model: Any, sort: str, order: str) -> Select:
    column = sortable_column(model, sort)
    return stmt.order_by(column.asc() if order == "asc" else column.desc())


async def paginate(db: AsyncSession, stmt: Select, page: int, page_size: int) -> tuple[list[Any], int]:
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await db.execute(stmt.offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return list(rows), int(total)


async def get_or_404(db: AsyncSession, model: Any, entity_id: uuid.UUID, name: str = "资源") -> Any:
    row = (
        await db.execute(select(model).where(model.id == entity_id, model.deleted_at.is_(None)))
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError(f"{name}不存在")
    return row


def soft_delete(row: Any) -> None:
    row.deleted_at = utcnow()


async def name_map(db: AsyncSession, model: Any, ids: set[uuid.UUID], field: str = "name") -> dict[uuid.UUID, str]:
    """批量取 id -> name，避免 N+1。"""
    clean = {i for i in ids if i is not None}
    if not clean:
        return {}
    rows = (await db.execute(select(model.id, getattr(model, field)).where(model.id.in_(clean)))).all()
    return {r[0]: r[1] for r in rows}
