"""数据范围（DataScope）服务。

scope_type: ALL / DEPT / DEPT_AND_CHILD / SELF / CUSTOM
- 业务员：SELF（只看自己的数据）
- 主管：DEPT_AND_CHILD（本部门及下级）
- 老板/核价员/管理员：ALL
"""

from __future__ import annotations

import uuid

from sqlalchemy import Select, or_, select

from app.models.user import DataScope, Department, User

# 数据范围优先级（数值越大范围越大）
_SCOPE_PRIORITY = {
    "SELF": 1,
    "CUSTOM": 2,
    "DEPT": 3,
    "DEPT_AND_CHILD": 4,
    "ALL": 5,
}


async def get_user_scope(user: User, session) -> tuple[str, list[uuid.UUID]]:
    """返回 (scope_type, department_ids)。"""
    if user.is_superuser:
        return "ALL", []
    if not user.roles:
        return "SELF", []

    role_ids = [r.id for r in user.roles]
    rows = (await session.execute(select(DataScope).where(DataScope.role_id.in_(role_ids)))).scalars().all()
    if not rows:
        return "SELF", []

    best = max(rows, key=lambda r: _SCOPE_PRIORITY.get(r.scope_type, 0))
    scope_type = best.scope_type
    dept_ids: list[uuid.UUID] = list(best.department_ids or [])

    if scope_type == "DEPT":
        dept_ids = [user.department_id] if user.department_id else []
    elif scope_type == "DEPT_AND_CHILD":
        dept_ids = await _descendant_dept_ids(user.department_id, session)
    elif scope_type == "SELF":
        dept_ids = []

    return scope_type, dept_ids


async def _descendant_dept_ids(root_id: uuid.UUID | None, session) -> list[uuid.UUID]:
    if root_id is None:
        return []
    all_depts = (await session.execute(select(Department.id, Department.parent_id))).all()
    children: dict[uuid.UUID | None, list[uuid.UUID]] = {}
    for dept_id, parent_id in all_depts:
        children.setdefault(parent_id, []).append(dept_id)

    result: list[uuid.UUID] = []
    stack = [root_id]
    while stack:
        current = stack.pop()
        result.append(current)
        stack.extend(children.get(current, []))
    return result


async def apply_data_scope(
    stmt: Select,
    model: type,
    user: User,
    session,
    owner_field: str = "owner_id",
    dept_field: str = "department_id",
) -> Select:
    """按数据范围对查询附加过滤条件。"""
    scope_type, dept_ids = await get_user_scope(user, session)

    if scope_type == "ALL":
        return stmt
    if scope_type == "SELF":
        if hasattr(model, owner_field):
            return stmt.where(getattr(model, owner_field) == user.id)
        return stmt
    if scope_type in {"DEPT", "DEPT_AND_CHILD", "CUSTOM"}:
        conditions = []
        if dept_ids and hasattr(model, dept_field):
            conditions.append(getattr(model, dept_field).in_(dept_ids))
        if hasattr(model, owner_field):
            conditions.append(getattr(model, owner_field) == user.id)
        if conditions:
            return stmt.where(or_(*conditions))
    return stmt


def can_access_owner(user: User, scope_type: str, dept_ids: list[uuid.UUID], owner_id, dept_id) -> bool:
    """单条数据的越权校验。"""
    if scope_type == "ALL":
        return True
    if scope_type == "SELF":
        return owner_id == user.id
    if scope_type in {"DEPT", "DEPT_AND_CHILD", "CUSTOM"}:
        return owner_id == user.id or (dept_id is not None and dept_id in dept_ids)
    return False
