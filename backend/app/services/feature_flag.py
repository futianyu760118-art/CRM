"""功能开关服务：Redis 缓存 + 数据库持久化。"""

from __future__ import annotations

import contextlib

from sqlalchemy import select

from app.db.redis_client import get_redis
from app.db.session import async_session_factory
from app.models.support import FeatureFlag

_CACHE_KEY = "crm:flags"
_TTL = 30


async def is_enabled(code: str, default: bool = False) -> bool:
    flags = await get_all_flags()
    return bool(flags.get(code, default))


async def get_all_flags() -> dict[str, bool]:
    redis = get_redis()
    try:
        cached = await redis.hgetall(_CACHE_KEY)
        if cached:
            return {str(k): str(v) == "1" for k, v in cached.items()}
    except Exception:  # noqa: BLE001
        pass

    async with async_session_factory() as session:
        rows = (await session.execute(select(FeatureFlag))).scalars().all()
    flags = {r.code: r.enabled for r in rows}
    try:
        if flags:
            await redis.hset(_CACHE_KEY, mapping={k: ("1" if v else "0") for k, v in flags.items()})
            await redis.expire(_CACHE_KEY, _TTL)
    except Exception:  # noqa: BLE001
        pass
    return flags


async def invalidate_cache() -> None:
    with contextlib.suppress(Exception):
        await get_redis().delete(_CACHE_KEY)
