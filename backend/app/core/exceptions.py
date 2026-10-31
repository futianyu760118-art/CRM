"""业务异常与全局异常处理器。"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.error_codes import ErrCode
from app.core.response import request_id_ctx
from app.domain.field_labels import field_label

logger = logging.getLogger("app.error")


class ApiError(Exception):
    """业务异常：抛出后由全局处理器转为统一响应。"""

    def __init__(
        self,
        code: int = ErrCode.INTERNAL_ERROR,
        message: str = "系统错误",
        http_status: int = 400,
        data: object | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.data = data


class NotFoundError(ApiError):
    def __init__(self, message: str = "资源不存在") -> None:
        super().__init__(ErrCode.NOT_FOUND, message, http_status=404)


class ConflictError(ApiError):
    def __init__(self, message: str = "数据冲突") -> None:
        super().__init__(ErrCode.CONFLICT, message, http_status=409)


class AuthError(ApiError):
    def __init__(self, message: str = "未认证", code: int = ErrCode.UNAUTHORIZED) -> None:
        super().__init__(code, message, http_status=401)


class ForbiddenError(ApiError):
    def __init__(self, message: str = "无权限", code: int = ErrCode.FORBIDDEN) -> None:
        super().__init__(code, message, http_status=403)


def _payload(code: int, message: str, data: object | None = None) -> dict[str, object]:
    return {
        "code": code,
        "message": message,
        "data": data,
        "request_id": request_id_ctx.get(),
    }


def _localized_reason(err: dict[str, Any]) -> str:
    """把 pydantic/pydantic-core 的错误类型翻译为业务可读原因。"""
    err_type = str(err.get("type") or "")
    ctx = err.get("ctx") or {}
    if err_type == "missing":
        return "不能为空"
    if err_type == "string_too_long":
        return f"最多 {ctx.get('max_length')} 字"
    if err_type == "string_too_short":
        return f"至少 {ctx.get('min_length')} 字"
    if err_type == "greater_than":
        return f"必须大于 {ctx.get('gt')}"
    if err_type == "greater_than_equal":
        return f"必须大于或等于 {ctx.get('ge')}"
    if err_type == "less_than":
        return f"必须小于 {ctx.get('lt')}"
    if err_type == "less_than_equal":
        return f"必须小于或等于 {ctx.get('le')}"
    if err_type in {"int_parsing", "int_type", "float_parsing", "float_type", "decimal_parsing"}:
        return "格式不正确（应为数字）"
    if err_type == "bool_parsing":
        return "格式不正确（应为是/否）"
    if err_type == "value_error":
        message = str(ctx.get("error") or err.get("msg") or "")
        for prefix in ("Value error, ", "Assertion failed, "):
            if message.startswith(prefix):
                message = message[len(prefix) :]
        return message or "取值不合法"
    return "格式不正确"


def _field_of(err: dict[str, Any]) -> str:
    loc = err.get("loc") or ()
    for part in reversed(loc):
        if isinstance(part, str) and part not in {"body", "query", "path", "header", "cookie"}:
            return field_label(part)
    return ""


def localize_validation_errors(errors: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """输出「<字段中文名>：<原因>」汇总文案，并返回可 JSON 序列化的明细。"""
    messages: list[str] = []
    details: list[dict[str, Any]] = []
    for err in errors:
        label = _field_of(err)
        reason = _localized_reason(err)
        message = f"{label}：{reason}" if label else reason
        if message not in messages:
            messages.append(message)
        detail: dict[str, Any] = {
            "type": err.get("type"),
            "loc": list(err.get("loc") or ()),
            "message": message,
        }
        if "ctx" in err:
            detail["ctx"] = {key: str(value) for key, value in (err.get("ctx") or {}).items()}
        details.append(detail)
    return "；".join(messages) or "参数校验失败", details


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content=_payload(exc.code, exc.message, exc.data),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        message, details = localize_validation_errors(exc.errors())
        return JSONResponse(
            status_code=422,
            content=_payload(ErrCode.VALIDATION_ERROR, message, details),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = ErrCode.NOT_FOUND if exc.status_code == 404 else ErrCode.INTERNAL_ERROR
        if exc.status_code == 401:
            code = ErrCode.UNAUTHORIZED
        elif exc.status_code == 403:
            code = ErrCode.FORBIDDEN
        return JSONResponse(
            status_code=exc.status_code,
            content=_payload(code, str(exc.detail)),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("未处理异常 %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content=_payload(ErrCode.INTERNAL_ERROR, "系统内部错误"),
        )
