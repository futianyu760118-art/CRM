"""Worker 任务：EBMS（AEOS 契约）投递。

周期消费 `integration_outbox` 中 EBMS 事件类型，经 `EbmsTransport` 投递到 EBMS，
投递结果回写 `integration_log`（幂等/重试/对账）。
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.db.session import async_session_factory
from app.services import ebms
from app.worker.celery_app import celery_app


async def _deliver_pending(limit: int) -> dict[str, Any]:
    async with async_session_factory() as session:
        result = await ebms.deliver_pending(session, limit=limit)
        await session.commit()
        return result


@celery_app.task(name="ebms.deliver_pending")
def deliver_pending(limit: int = 50) -> dict[str, Any]:
    """投递到期未处理的 EBMS Outbox。"""
    return asyncio.run(_deliver_pending(limit))
