"""Redis 客户端（缓存 / 编号序列 / 令牌黑名单）。"""

from __future__ import annotations

from functools import lru_cache

import redis.asyncio as aioredis

from app.core.config import settings


@lru_cache
def get_redis() -> aioredis.Redis:
    return aioredis.from_url(settings.redis_url, decode_responses=True)
