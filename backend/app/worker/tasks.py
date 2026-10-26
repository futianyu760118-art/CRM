"""Worker 任务：EBMS（AEOS 契约）投递。

周期消费 `integration_outbox` 中 EBMS 事件类型，经 `EbmsTransport` 投递到 EBMS，
投递结果回写 `integration_log`（幂等/重试/对账）。
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.db.session import async_session_factory, engine
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

    async def _run() -> dict[str, Any]:
        try:
            return await _deliver_pending(limit)
        finally:
            # 每次 Celery 任务都会新建事件循环；连接池跨循环复用会抛
            # "Future attached to a different loop"，因此每轮把连接归还。
            await engine.dispose()

    return asyncio.run(_run())
