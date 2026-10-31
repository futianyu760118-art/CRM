"""文件存储服务：优先 MinIO，不可用时本地落盘。"""

from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.email import File

LOCAL_ROOT = Path(__file__).resolve().parents[2] / "storage"


def _minio_client() -> Any:
    from minio import Minio

    client = Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
    )
    if not client.bucket_exists(settings.MINIO_BUCKET):
        client.make_bucket(settings.MINIO_BUCKET)
    return client


async def save_bytes(
    db: AsyncSession,
    *,
    filename: str,
    data: bytes,
    mime: str | None,
    module: str | None = None,
    biz_id: uuid.UUID | None = None,
    uploader_id: uuid.UUID | None = None,
) -> File:
    object_key = f"{module or 'common'}/{datetime.now(UTC):%Y%m}/{uuid.uuid4().hex}_{filename}"
    local_path: str | None = None

    stored_remote = False
    try:
        client = _minio_client()
        client.put_object(
            settings.MINIO_BUCKET,
            object_key,
            io.BytesIO(data),
            length=len(data),
            content_type=mime or "application/octet-stream",
        )
        stored_remote = True
    except Exception:  # noqa: BLE001
        stored_remote = False

    if not stored_remote:
        target = LOCAL_ROOT / object_key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        local_path = str(target)

    record = File(
        name=filename,
        bucket=settings.MINIO_BUCKET,
        object_key=object_key,
        size=len(data),
        mime=mime,
        module=module,
        biz_id=biz_id,
        uploader_id=uploader_id,
        local_path=local_path,
    )
    db.add(record)
    await db.flush()
    return record


def read_bytes(file: File) -> bytes:
    if file.local_path:
        return Path(file.local_path).read_bytes()
    client = _minio_client()
    resp = client.get_object(file.bucket, file.object_key)
    try:
        return resp.read()
    finally:
        resp.close()
        resp.release_conn()
