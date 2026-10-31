"""统一响应结构与请求上下文。

响应格式（DOC-API-001）：{ code, message, data, request_id }
错误码分段：400xx 参数 / 401xx 认证 / 403xx 权限 / 500xx 系统
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from typing import Any

from pydantic import BaseModel

# 当前请求 ID（由 RequestIDMiddleware 写入）
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")


def new_request_id() -> str:
    return uuid.uuid4().hex


class ApiResponse(BaseModel):
    code: int = 0
    message: str = "success"
    data: Any = None
    request_id: str = ""


def ok(data: Any = None, message: str = "success") -> dict[str, Any]:
    return {
        "code": 0,
        "message": message,
        "data": data,
        "request_id": request_id_ctx.get(),
    }


def page(
    items: list[Any],
    total: int,
    pg: int,
    page_size: int,
) -> dict[str, Any]:
    return ok(
        {
            "items": items,
            "total": total,
            "page": pg,
            "page_size": page_size,
            "pages": (total + page_size - 1) // page_size if page_size else 0,
        }
    )
