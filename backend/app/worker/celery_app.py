"""Celery 应用（M1 预留：邮件收发 / K3 同步 / PDF 生成）。"""

from __future__ import annotations

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "crm",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    beat_schedule={},
)


@celery_app.task(name="health.ping")
def ping() -> str:
    return "pong"
