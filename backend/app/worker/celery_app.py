"""Celery 应用（M1 预留：邮件收发 / K3 同步 / EBMS 投递 / PDF 生成）。"""

from __future__ import annotations

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "crm",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    beat_schedule={
        # EBMS（AEOS 契约）投递：每分钟消费一次 Outbox
        "ebms-deliver-pending": {
            "task": "ebms.deliver_pending",
            "schedule": 60.0,
            "kwargs": {"limit": 50},
        },
    },
)


@celery_app.task(name="health.ping")
def ping() -> str:
    return "pong"
