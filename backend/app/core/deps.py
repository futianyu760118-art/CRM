"""依赖注入：认证、权限校验、数据范围。"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.error_codes import ErrCode
from app.core.exceptions import AuthError, ForbiddenError
from app.core.security import decode_token
from app.db.redis_client import get_redis
from app.db.session import get_db
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False, description="Bearer <access_token>")

DbSession = Annotated[AsyncSession, Depends(get_db)]

BLACKLIST_PREFIX = "crm:token:blacklist:"


async def _is_blacklisted(jti: str) -> bool:
    try:
        return bool(await get_redis().exists(BLACKLIST_PREFIX + jti))
    except Exception:  # noqa: BLE001
        return False


async def get_current_user(
    request: Request,
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    if credentials is None or not credentials.credentials:
        raise AuthError("未提供认证凭证")

    try:
        payload = decode_token(credentials.credentials)
    except Exception as exc:  # noqa: BLE001
        raise AuthError("Token 无效或已过期", ErrCode.TOKEN_INVALID) from exc

    if payload.get("type") != "access":
        raise AuthError("Token 类型错误", ErrCode.TOKEN_INVALID)
    if await _is_blacklisted(payload.get("jti", "")):
        raise AuthError("Token 已失效", ErrCode.TOKEN_EXPIRED)

    user_id = payload.get("sub")
    user = (await db.execute(select(User).where(User.id == user_id, User.deleted_at.is_(None)))).scalar_one_or_none()

    if user is None:
        raise AuthError("用户不存在", ErrCode.UNAUTHORIZED)
    if not user.is_active:
        raise AuthError("账号已被禁用", ErrCode.ACCOUNT_DISABLED)

    request.state.user = user
    request.state.token_payload = payload
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_permission(*codes: str):
    """按钮/接口级权限校验。"""

    async def _checker(user: CurrentUser) -> User:
        if user.is_superuser:
            return user
        owned = user.permission_codes
        if "*" in owned or any(c in owned for c in codes):
            return user
        raise ForbiddenError(f"缺少权限: {', '.join(codes)}", ErrCode.FORBIDDEN)

    return _checker


def require_all_permissions(*codes: str):
    async def _checker(user: CurrentUser) -> User:
        if user.is_superuser:
            return user
        owned = user.permission_codes
        if all(c in owned for c in codes):
            return user
        raise ForbiddenError(f"缺少权限: {', '.join(codes)}", ErrCode.FORBIDDEN)

    return _checker
