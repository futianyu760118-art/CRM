"""角色与权限管理接口。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import delete, select

from app.core import response as resp
from app.core.deps import CurrentUser, DbSession, require_permission
from app.core.exceptions import ConflictError, NotFoundError
from app.models.user import DataScope, Permission, Role, RolePermission, User
from app.schemas.system import PermissionOut, RoleCreate, RoleOut, RoleUpdate

router = APIRouter(tags=["系统-角色权限"])

SCOPE_TYPES = {"ALL", "DEPT", "DEPT_AND_CHILD", "SELF", "CUSTOM"}


def role_to_out(role: Role, scope_type: str = "SELF") -> RoleOut:
    return RoleOut(
        id=role.id,
        code=role.code,
        name=role.name,
        description=role.description,
        is_system=role.is_system,
        status=role.status,
        sort=role.sort,
        permission_codes=sorted(p.code for p in role.permissions),
        scope_type=scope_type,
        created_at=role.created_at,
    )


async def _scope_of(db, role_id: uuid.UUID) -> str:
    row = (await db.execute(select(DataScope).where(DataScope.role_id == role_id))).scalar_one_or_none()
    return row.scope_type if row else "SELF"


async def _set_permissions(db, role: Role, codes: list[str]) -> None:
    await db.execute(delete(RolePermission).where(RolePermission.role_id == role.id))
    if not codes:
        return
    if "*" in codes:
        perms = (await db.execute(select(Permission.id))).scalars().all()
    else:
        perms = (await db.execute(select(Permission.id).where(Permission.code.in_(codes)))).scalars().all()
    for pid in perms:
        db.add(RolePermission(role_id=role.id, permission_id=pid))


async def _set_scope(db, role_id: uuid.UUID, scope_type: str) -> None:
    if scope_type not in SCOPE_TYPES:
        scope_type = "SELF"
    row = (await db.execute(select(DataScope).where(DataScope.role_id == role_id))).scalar_one_or_none()
    if row is None:
        db.add(DataScope(role_id=role_id, scope_type=scope_type, department_ids=[]))
    else:
        row.scope_type = scope_type


@router.get("/roles", summary="角色列表")
async def list_roles(db: DbSession, _: User = Depends(require_permission("role:view"))):
    stmt = select(Role).where(Role.deleted_at.is_(None)).order_by(Role.sort)
    roles = (await db.execute(stmt)).scalars().all()
    out = [role_to_out(r, await _scope_of(db, r.id)).model_dump(mode="json") for r in roles]
    return resp.ok(out)


@router.post("/roles", summary="创建角色", status_code=201)
async def create_role(
    payload: RoleCreate,
    db: DbSession,
    _: User = Depends(require_permission("role:update")),
):
    exists = (await db.execute(select(Role.id).where(Role.code == payload.code))).scalar_one_or_none()
    if exists:
        raise ConflictError("角色编码已存在")
    role = Role(
        code=payload.code,
        name=payload.name,
        description=payload.description,
        sort=payload.sort,
    )
    db.add(role)
    await db.flush()
    await _set_permissions(db, role, payload.permission_codes)
    await _set_scope(db, role.id, payload.scope_type)
    await db.commit()
    await db.refresh(role)
    return resp.ok(role_to_out(role, payload.scope_type).model_dump(mode="json"))


@router.put("/roles/{role_id}", summary="更新角色")
async def update_role(
    role_id: uuid.UUID,
    payload: RoleUpdate,
    db: DbSession,
    _: User = Depends(require_permission("role:update")),
):
    role = (await db.execute(select(Role).where(Role.id == role_id, Role.deleted_at.is_(None)))).scalar_one_or_none()
    if role is None:
        raise NotFoundError("角色不存在")

    data = payload.model_dump(exclude_unset=True)
    codes = data.pop("permission_codes", None)
    scope_type = data.pop("scope_type", None)
    for key, value in data.items():
        setattr(role, key, value)
    if codes is not None:
        await _set_permissions(db, role, codes)
    if scope_type is not None:
        await _set_scope(db, role.id, scope_type)
    await db.commit()
    await db.refresh(role)
    return resp.ok(role_to_out(role, await _scope_of(db, role.id)).model_dump(mode="json"))


@router.delete("/roles/{role_id}", summary="删除角色")
async def delete_role(
    role_id: uuid.UUID,
    db: DbSession,
    _: User = Depends(require_permission("role:update")),
):
    role = (await db.execute(select(Role).where(Role.id == role_id, Role.deleted_at.is_(None)))).scalar_one_or_none()
    if role is None:
        raise NotFoundError("角色不存在")
    if role.is_system:
        raise ConflictError("系统内置角色不可删除")
    from datetime import UTC, datetime

    role.deleted_at = datetime.now(UTC)
    role.status = "DISABLED"
    await db.commit()
    return resp.ok({"deleted": True})


@router.get("/permissions", summary="权限列表")
async def list_permissions(db: DbSession, _: CurrentUser):
    stmt = select(Permission).where(Permission.deleted_at.is_(None)).order_by(Permission.sort, Permission.code)
    items = (await db.execute(stmt)).scalars().all()
    return resp.ok([PermissionOut.model_validate(p).model_dump(mode="json") for p in items])
