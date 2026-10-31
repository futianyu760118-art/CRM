"""部门管理接口。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from app.core import response as resp
from app.core.deps import CurrentUser, DbSession, require_permission
from app.core.exceptions import ConflictError, NotFoundError
from app.models.user import Department, User
from app.schemas.system import DepartmentCreate, DepartmentOut, DepartmentUpdate

router = APIRouter(prefix="/departments", tags=["系统-部门"])


@router.get("", summary="部门列表（树）")
async def list_departments(db: DbSession, _: CurrentUser):
    stmt = select(Department).where(Department.deleted_at.is_(None)).order_by(Department.sort)
    items = (await db.execute(stmt)).scalars().all()
    nodes = {d.id: {**DepartmentOut.model_validate(d).model_dump(mode="json"), "children": []} for d in items}
    tree: list[dict] = []
    for d in items:
        node = nodes[d.id]
        if d.parent_id and d.parent_id in nodes:
            nodes[d.parent_id]["children"].append(node)
        else:
            tree.append(node)
    return resp.ok(tree)


@router.post("", summary="创建部门", status_code=201)
async def create_department(
    payload: DepartmentCreate,
    db: DbSession,
    _: User = Depends(require_permission("department:update")),
):
    exists = (await db.execute(select(Department.id).where(Department.code == payload.code))).scalar_one_or_none()
    if exists:
        raise ConflictError("部门编码已存在")
    dept = Department(**payload.model_dump())
    db.add(dept)
    await db.commit()
    await db.refresh(dept)
    return resp.ok(DepartmentOut.model_validate(dept).model_dump(mode="json"))


@router.put("/{dept_id}", summary="更新部门")
async def update_department(
    dept_id: uuid.UUID,
    payload: DepartmentUpdate,
    db: DbSession,
    _: User = Depends(require_permission("department:update")),
):
    dept = (
        await db.execute(select(Department).where(Department.id == dept_id, Department.deleted_at.is_(None)))
    ).scalar_one_or_none()
    if dept is None:
        raise NotFoundError("部门不存在")
    if payload.parent_id == dept_id:
        raise ConflictError("上级部门不能是自己")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(dept, key, value)
    await db.commit()
    await db.refresh(dept)
    return resp.ok(DepartmentOut.model_validate(dept).model_dump(mode="json"))


@router.delete("/{dept_id}", summary="删除部门")
async def delete_department(
    dept_id: uuid.UUID,
    db: DbSession,
    _: User = Depends(require_permission("department:update")),
):
    dept = (
        await db.execute(select(Department).where(Department.id == dept_id, Department.deleted_at.is_(None)))
    ).scalar_one_or_none()
    if dept is None:
        raise NotFoundError("部门不存在")
    child_count = (
        await db.execute(
            select(func.count())
            .select_from(Department)
            .where(Department.parent_id == dept_id, Department.deleted_at.is_(None))
        )
    ).scalar_one()
    if child_count:
        raise ConflictError("存在下级部门，无法删除")
    user_count = (
        await db.execute(select(func.count()).select_from(User).where(User.department_id == dept_id))
    ).scalar_one()
    if user_count:
        raise ConflictError("部门下存在用户，无法删除")
    dept.deleted_at = datetime.now(UTC)
    dept.status = "DISABLED"
    await db.commit()
    return resp.ok({"deleted": True})
