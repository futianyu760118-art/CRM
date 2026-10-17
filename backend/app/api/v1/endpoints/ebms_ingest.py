"""EBMS → CRM 入站摄入端点（AEOS.Event.V1，PAND-249）。

鉴权：Bearer ``EBMS_INBOUND_TOKEN``（独立于 JWT），未配置时返回 503（生产红线：
禁止默认口令）。契约校验失败返回 422。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from app.contracts.aeos import ContractValidationError, validate_contract
from app.core import response as resp
from app.core.config import settings
from app.core.deps import DbSession, require_permission
from app.core.error_codes import ErrCode
from app.core.exceptions import ApiError
from app.models.user import User
from app.services import ebms_ingest

router = APIRouter(prefix="/integrations/ebms", tags=["M6-EBMS集成"])


def _verify_inbound_token(request: Request) -> None:
    """入站通道独立鉴权：仅接受与 EBMS_INBOUND_TOKEN 一致的 Bearer 令牌。"""
    if not settings.EBMS_INBOUND_TOKEN:
        raise ApiError(
            ErrCode.SERVICE_UNAVAILABLE,
            "EBMS 入站令牌未配置（生产禁止默认口令）",
            http_status=503,
        )
    header = request.headers.get("Authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else ""
    if token != settings.EBMS_INBOUND_TOKEN:
        raise ApiError(ErrCode.UNAUTHORIZED, "入站令牌无效", http_status=401)


@router.post("/ingest", summary="入站：消费单条 EBMS 实体事件")
async def ingest(
    payload: dict[str, Any],
    request: Request,
    db: DbSession,
    _: None = Depends(_verify_inbound_token),
) -> dict[str, Any]:
    # 优先采用发送方 X-Idempotency-Key 头；无则回退事件体/契约重算（见 _resolve_key）
    header_key = request.headers.get("X-Idempotency-Key")
    result = await ebms_ingest.ingest_event(db, payload, header_idempotency_key=header_key)
    await db.commit()
    return resp.ok(result)


@router.post("/ingest/batch", summary="入站：批量消费 EBMS 实体事件")
async def ingest_batch(
    payload: dict[str, Any],
    db: DbSession,
    _: None = Depends(_verify_inbound_token),
) -> dict[str, Any]:
    events = payload.get("events")
    if not isinstance(events, list) or not events:
        raise ApiError(ErrCode.VALIDATION_ERROR, "events 必须为非空数组", http_status=422)

    # 先整体校验，任一不合规即 422（避免半截写入）
    for idx, event in enumerate(events):
        try:
            validate_contract(event)
        except ContractValidationError as exc:
            raise ApiError(
                ErrCode.CONTRACT_INVALID,
                f"events[{idx}] 契约校验失败",
                http_status=422,
                data={"index": idx, "errors": exc.data or [{"message": exc.message}]},
            ) from exc

    results = []
    for event in events:
        results.append(await ebms_ingest.ingest_event(db, event))
    await db.commit()
    return resp.ok({"total": len(results), "results": results})


@router.get("/conflicts", summary="同步冲突列表（OWNER_KEPT / LOCKED / STALE 留痕）")
async def conflicts(
    db: DbSession,
    _: User = Depends(require_permission("integration:view")),
    object_type: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    rows, total = await ebms_ingest.list_conflicts(
        db, object_type=object_type, page=page, page_size=page_size
    )
    items = [
        {
            "id": str(r.id),
            "object_type": r.object_type,
            "object_id": r.object_id,
            "field": r.field,
            "source_system": r.source_system,
            "incoming_value": r.incoming_value,
            "local_value": r.local_value,
            "resolution": r.resolution,
            "event_id": r.event_id,
            "idempotency_key": r.idempotency_key,
            "occurred_at": r.occurred_at.isoformat() if r.occurred_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
    return resp.page(items, total, page, page_size)
