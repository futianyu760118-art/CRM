"""系统参数（``system_config``）读取与类型转换。

业务参数（汇率、折扣金额门槛等）统一落 ``system_config``，由管理员人工维护；
读取失败或值非法时回退调用方给定的默认值，保证行为可预期。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.support import SystemConfig

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def parse_bool(raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    return default


def parse_float(raw: str | None, default: float) -> float:
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


async def get_value(db: AsyncSession, key: str, default: str | None = None) -> str | None:
    value = (
        await db.execute(
            select(SystemConfig.value).where(
                SystemConfig.key == key,
                SystemConfig.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    return default if value is None else value


async def get_bool(db: AsyncSession, key: str, default: bool = False) -> bool:
    return parse_bool(await get_value(db, key), default)


async def get_float(db: AsyncSession, key: str, default: float) -> float:
    return parse_float(await get_value(db, key), default)
