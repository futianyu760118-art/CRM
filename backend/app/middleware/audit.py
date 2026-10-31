"""审计日志中间件：所有写操作（POST/PUT/PATCH/DELETE）自动落库。"""

from __future__ import annotations

import json
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

from app.core.config import settings
from app.core.security import decode_token
from app.db.session import async_session_factory
from app.models.audit import AuditLog

_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_ACTION_MAP = {"POST": "CREATE", "PUT": "UPDATE", "PATCH": "UPDATE", "DELETE": "DELETE"}
_SKIP_PREFIXES = (
    "/docs",
    "/redoc",
    "/openapi.json",
    "/health",
)
_MAX_BODY = 8000


def _module_of(path: str) -> str:
    parts = [p for p in path.strip("/").split("/") if p]
    if "api" in parts and "v1" in parts:
        idx = parts.index("v1")
        parts = parts[idx + 1 :]
    return parts[0] if parts else "root"


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


class AuditMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        if (
            request.method not in _WRITE_METHODS
            or not request.url.path.startswith(settings.API_V1_PREFIX)
            or any(request.url.path.startswith(p) for p in _SKIP_PREFIXES)
        ):
            return await call_next(request)

        start = time.perf_counter()
        body = await self._safe_body(request)

        status_code = 500
        error_message: str | None = None
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as exc:  # noqa: BLE001
            error_message = str(exc)
            duration = int((time.perf_counter() - start) * 1000)
            await self._write_log(request, body, status_code, duration, error_message)
            raise
        duration = int((time.perf_counter() - start) * 1000)
        if status_code >= 400:
            error_message = f"HTTP {status_code}"
        await self._write_log(request, body, status_code, duration, error_message)
        return response

    @staticmethod
    async def _safe_body(request: Request) -> dict | None:
        try:
            raw = await request.body()
            if not raw:
                return None
            if len(raw) > _MAX_BODY:
                return {"_truncated": True, "_size": len(raw)}
            data = json.loads(raw)
            if isinstance(data, dict):
                for secret in ("password", "old_password", "new_password"):
                    if secret in data:
                        data[secret] = "***"
            return data if isinstance(data, dict) else {"_data": data}
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _identity(request: Request) -> tuple[str | None, str | None]:
        auth = request.headers.get("authorization") or ""
        if not auth.lower().startswith("bearer "):
            return None, None
        try:
            payload = decode_token(auth.split(" ", 1)[1])
            return payload.get("sub"), payload.get("sub")
        except Exception:  # noqa: BLE001
            return None, None

    async def _write_log(
        self,
        request: Request,
        body: dict | None,
        status_code: int,
        duration_ms: int,
        error_message: str | None,
    ) -> None:
        user_id, username = self._identity(request)
        path_parts = [p for p in request.url.path.strip("/").split("/") if p]
        resource_id = path_parts[3] if len(path_parts) > 3 else None
        try:
            async with async_session_factory() as session:
                session.add(
                    AuditLog(
                        user_id=user_id,
                        username=str(user_id) if user_id else None,
                        module=_module_of(request.url.path),
                        action=_ACTION_MAP.get(request.method, request.method),
                        method=request.method,
                        path=request.url.path,
                        resource_id=resource_id,
                        request_body=body,
                        status_code=status_code,
                        success=200 <= status_code < 400,
                        duration_ms=duration_ms,
                        ip=_client_ip(request),
                        user_agent=request.headers.get("user-agent"),
                        error_message=error_message,
                        request_id=request.headers.get("X-Request-ID"),
                    )
                )
                await session.commit()
        except Exception:  # noqa: BLE001
            # 审计失败不得影响主流程
            pass
