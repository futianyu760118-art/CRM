"""认证接口：登录 / 刷新 / 登出 / 当前用户。"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from sqlalchemy import select

from app.core import response as resp
from app.core.config import settings
from app.core.deps import CurrentUser, DbSession
from app.core.error_codes import ErrCode
from app.core.exceptions import AuthError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.db.redis_client import get_redis
from app.middleware.audit import _client_ip
from app.models.audit import AuditLog
from app.models.user import Permission, User
from app.schemas.auth import LoginRequest, LogoutRequest, MenuItem, MeOut, RefreshRequest, TokenPair

router = APIRouter(prefix="/auth", tags=["认证"])

BLACKLIST_PREFIX = "crm:token:blacklist:"


async def _blacklist(jti: str, exp: int) -> None:
    if not jti or not exp:
        return
    ttl = max(int(exp - datetime.now(UTC).timestamp()), 1)
    with contextlib.suppress(Exception):
        await get_redis().setex(BLACKLIST_PREFIX + jti, ttl, "1")


@router.post("/login", summary="登录")
async def login(payload: LoginRequest, request: Request, db: DbSession):
    user = (
        await db.execute(select(User).where(User.username == payload.username, User.deleted_at.is_(None)))
    ).scalar_one_or_none()

    if user is None or not verify_password(payload.password, user.password_hash):
        raise AuthError("账号或密码错误", ErrCode.BAD_CREDENTIALS)
    if not user.is_active:
        raise AuthError("账号已被禁用", ErrCode.ACCOUNT_DISABLED)

    user.last_login_at = datetime.now(UTC)
    db.add(
        AuditLog(
            user_id=user.id,
            username=user.username,
            module="auth",
            action="LOGIN",
            method="POST",
            path="/api/v1/auth/login",
            status_code=200,
            success=True,
            ip=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            request_id=request.headers.get("X-Request-ID"),
        )
    )
    await db.commit()

    access, _ = create_access_token(str(user.id))
    refresh, _ = create_refresh_token(str(user.id))
    return resp.ok(
        TokenPair(
            access_token=access,
            refresh_token=refresh,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        ).model_dump()
    )


@router.post("/refresh", summary="刷新 Token")
async def refresh(payload: RefreshRequest):
    try:
        data = decode_token(payload.refresh_token)
    except Exception as exc:  # noqa: BLE001
        raise AuthError("Refresh Token 无效或已过期", ErrCode.TOKEN_INVALID) from exc

    if data.get("type") != "refresh":
        raise AuthError("Token 类型错误", ErrCode.TOKEN_INVALID)

    access, _ = create_access_token(str(data.get("sub")))
    return resp.ok({"access_token": access, "token_type": "bearer"})


@router.post("/logout", summary="登出")
async def logout(payload: LogoutRequest, request: Request, _: CurrentUser):
    token_payload = getattr(request.state, "token_payload", {}) or {}
    await _blacklist(token_payload.get("jti", ""), token_payload.get("exp", 0))
    if payload.refresh_token:
        try:
            rp = decode_token(payload.refresh_token)
            await _blacklist(rp.get("jti", ""), rp.get("exp", 0))
        except Exception:  # noqa: BLE001
            pass
    return resp.ok({"logged_out": True})


@router.get("/me", summary="当前用户信息与权限")
async def me(user: CurrentUser, db: DbSession):
    stmt = (
        select(Permission)
        .where(Permission.type == "MENU", Permission.deleted_at.is_(None))
        .order_by(Permission.sort, Permission.code)
    )
    menus = (await db.execute(stmt)).scalars().all()
    if not user.is_superuser:
        owned = user.permission_codes
        menus = [m for m in menus if m.code in owned]

    return resp.ok(
        MeOut(
            id=user.id,
            username=user.username,
            name=user.name,
            email=user.email,
            avatar=user.avatar,
            is_superuser=user.is_superuser,
            roles=user.role_codes,
            permissions=sorted(user.permission_codes),
            department_id=user.department_id,
            department_name=user.department.name if user.department else None,
            menus=[MenuItem(code=m.code, name=m.name, path=m.path, icon=m.icon, sort=m.sort) for m in menus],
        ).model_dump(mode="json")
    )
