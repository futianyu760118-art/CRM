"""用户管理接口。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete, func, or_, select

from app.core import response as resp
from app.core.deps import CurrentUser, DbSession, require_permission
from app.core.exceptions import ConflictError, NotFoundError
from app.core.security import hash_password
from app.models.user import Role, User, UserRole
from app.schemas.system import UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/users", tags=["系统-用户"])


def user_to_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        code=user.code,
        name=user.name,
        email=user.email,
        phone=user.phone,
        avatar=user.avatar,
        department_id=user.department_id,
        department_name=user.department.name if user.department else None,
        is_superuser=user.is_superuser,
        status=user.status,
        roles=user.role_codes,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


async def _set_roles(db, user: User, role_ids: list[uuid.UUID]) -> None:
    await db.execute(delete(UserRole).where(UserRole.user_id == user.id))
    if not role_ids:
        return
    rows = (await db.execute(select(Role.id).where(Role.id.in_(role_ids)))).scalars().all()
    for rid in rows:
        db.add(UserRole(user_id=user.id, role_id=rid))


@router.get("", summary="用户列表")
async def list_users(
    db: DbSession,
    _: User = Depends(require_permission("user:view")),
    keyword: str | None = Query(None, description="用户名/姓名/邮箱模糊搜索"),
    department_id: uuid.UUID | None = None,
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    stmt = select(User).where(User.deleted_at.is_(None))
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(or_(User.username.ilike(like), User.name.ilike(like), User.email.ilike(like)))
    if department_id:
        stmt = stmt.where(User.department_id == department_id)
    if status:
        stmt = stmt.where(User.status == status)

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    stmt = stmt.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(stmt)).scalars().all()
    return resp.page([user_to_out(u).model_dump(mode="json") for u in items], total, page, page_size)


@router.post("", summary="创建用户", status_code=201)
async def create_user(
    payload: UserCreate,
    db: DbSession,
    current: User = Depends(require_permission("user:create")),
):
    exists = (await db.execute(select(User.id).where(User.username == payload.username))).scalar_one_or_none()
    if exists:
        raise ConflictError("用户名已存在")

    if payload.code:
        dup = (await db.execute(select(User.id).where(User.code == payload.code))).scalar_one_or_none()
        if dup:
            raise ConflictError(f"业务员编号 {payload.code} 已被占用")

    user = User(
        username=payload.username,
        code=payload.code,
        password_hash=hash_password(payload.password),
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        department_id=payload.department_id,
        is_superuser=payload.is_superuser,
        status=payload.status,
    )
    db.add(user)
    await db.flush()
    await _set_roles(db, user, payload.role_ids)
    await db.commit()
    await db.refresh(user)
    return resp.ok(user_to_out(user).model_dump(mode="json"))


@router.get("/options", summary="用户下拉选项（仅 id/姓名/部门）")
async def user_options(db: DbSession, _: CurrentUser) -> dict[str, Any]:
    stmt = select(User).where(User.deleted_at.is_(None), User.status == "ACTIVE").order_by(User.name)
    rows = (await db.execute(stmt)).scalars().all()
    return resp.ok(
        [
            {
                "id": str(u.id),
                "name": u.name,
                "username": u.username,
                "code": u.code,
                "department_name": u.department.name if u.department else None,
            }
            for u in rows
        ]
    )


@router.get("/{user_id}", summary="用户详情")
async def get_user(
    user_id: uuid.UUID,
    db: DbSession,
    _: User = Depends(require_permission("user:view")),
):
    user = (await db.execute(select(User).where(User.id == user_id, User.deleted_at.is_(None)))).scalar_one_or_none()
    if user is None:
        raise NotFoundError("用户不存在")
    return resp.ok(user_to_out(user).model_dump(mode="json"))


@router.put("/{user_id}", summary="更新用户")
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    db: DbSession,
    _: User = Depends(require_permission("user:update")),
):
    user = (await db.execute(select(User).where(User.id == user_id, User.deleted_at.is_(None)))).scalar_one_or_none()
    if user is None:
        raise NotFoundError("用户不存在")

    data = payload.model_dump(exclude_unset=True)
    role_ids = data.pop("role_ids", None)
    new_code = data.get("code")
    if new_code:
        dup = (await db.execute(select(User.id).where(User.code == new_code, User.id != user_id))).scalar_one_or_none()
        if dup:
            raise ConflictError(f"业务员编号 {new_code} 已被占用")
    for key, value in data.items():
        setattr(user, key, value)
    if role_ids is not None:
        await _set_roles(db, user, role_ids)
    await db.commit()
    await db.refresh(user)
    return resp.ok(user_to_out(user).model_dump(mode="json"))


@router.delete("/{user_id}", summary="删除用户（软删除）")
async def delete_user(
    user_id: uuid.UUID,
    db: DbSession,
    current: User = Depends(require_permission("user:update")),
):
    if user_id == current.id:
        raise ConflictError("不能删除当前登录用户")
    user = (await db.execute(select(User).where(User.id == user_id, User.deleted_at.is_(None)))).scalar_one_or_none()
    if user is None:
        raise NotFoundError("用户不存在")
    user.deleted_at = datetime.now(UTC)
    user.status = "DISABLED"
    await db.commit()
    return resp.ok({"deleted": True})
