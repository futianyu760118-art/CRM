"""业务异常与全局异常处理器。"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.error_codes import ErrCode
from app.core.response import request_id_ctx

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


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content=_payload(exc.code, exc.message, exc.data),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_payload(ErrCode.VALIDATION_ERROR, "参数校验失败", exc.errors()),
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
