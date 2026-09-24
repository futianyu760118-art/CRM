"""通用文件接口：上传 / 下载（产品图、附件）。

下载支持 `?token=` 查询参数，便于 <img src> 直接引用受保护资源。
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, File, Query, Request, UploadFile
from fastapi.responses import Response

from app.core import response as resp
from app.core.deps import CurrentUser, DbSession
from app.core.exceptions import AuthError
from app.core.security import decode_token
from app.models.email import File as FileModel
from app.services import storage
from app.services.query import get_or_404

router = APIRouter(prefix="/files", tags=["文件"])

MAX_SIZE = 20 * 1024 * 1024
ALLOWED_PREFIX = "image/"


@router.post("/upload", summary="上传文件（产品图等）", status_code=201)
async def upload(
    db: DbSession,
    current: CurrentUser,
    file: UploadFile = File(...),
    module: str = Query("common"),
    biz_id: uuid.UUID | None = Query(None),
) -> dict[str, Any]:
    data = await file.read()
    if len(data) > MAX_SIZE:
        raise AuthError("文件超过 20MB 限制")
    mime = file.content_type or "application/octet-stream"
    record = await storage.save_bytes(
        db,
        filename=file.filename or "upload.bin",
        data=data,
        mime=mime,
        module=module,
        biz_id=biz_id,
        uploader_id=current.id,
    )
    await db.commit()
    return resp.ok(
        {
            "id": str(record.id),
            "name": record.name,
            "mime": record.mime,
            "size": record.size,
            "url": f"/api/v1/files/{record.id}",
        }
    )


def _resolve_token(request: Request) -> str:
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1]
    return ""


@router.get("/{file_id}", summary="下载/预览文件")
async def download(
    file_id: uuid.UUID,
    db: DbSession,
    request: Request,
    token: str = Query("", description="图片 <img> 场景可直接传 access_token"),
) -> Response:
    raw = _resolve_token(request) or token
    if not raw:
        raise AuthError("未提供认证凭证")
    try:
        decode_token(raw)
    except Exception as exc:  # noqa: BLE001
        raise AuthError("Token 无效或已过期") from exc

    record = await get_or_404(db, FileModel, file_id, "文件")
    data = storage.read_bytes(record)
    filename = record.name
    return Response(
        content=data,
        media_type=record.mime or "application/octet-stream",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.get("", summary="文件列表")
async def list_files(
    db: DbSession,
    _: CurrentUser,
    module: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
) -> dict[str, Any]:
    from sqlalchemy import func, select

    stmt = select(FileModel).where(FileModel.deleted_at.is_(None))
    if module:
        stmt = stmt.where(FileModel.module == module)
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (
        (await db.execute(stmt.order_by(FileModel.created_at.desc()).offset((page - 1) * page_size).limit(page_size)))
        .scalars()
        .all()
    )
    return resp.page(
        [
            {
                "id": str(r.id),
                "name": r.name,
                "mime": r.mime,
                "size": r.size,
                "module": r.module,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
        int(total),
        page,
        page_size,
    )
