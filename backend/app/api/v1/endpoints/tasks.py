"""M3 任务接口（含我的任务 / 完成）。

注意：`/tasks/mine` 必须在 `/tasks/{task_id}` 之前注册，否则会被动态路由吞掉。
因此这里用一个聚合 router：先注册静态路由，再挂载通用 CRUD。
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select

from app.api.crud import CrudConfig, build_crud_router
from app.core import response as resp
from app.core.deps import CurrentUser, DbSession, require_permission
from app.db.base import utcnow
from app.models.business import Task
from app.models.user import User
from app.schemas.business import TaskCreate, TaskOut, TaskUpdate
from app.services.query import apply_sort, get_or_404, paginate

_aux = APIRouter(prefix="/tasks", tags=["M3-任务"])


@_aux.get("/mine", summary="我的任务")
async def my_tasks(
    db: DbSession,
    current: CurrentUser,
    status: str | None = Query("PENDING"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
) -> dict[str, Any]:
    stmt = select(Task).where(Task.deleted_at.is_(None))
    stmt = stmt.where(or_(Task.assignee_id == current.id, Task.assignee_id.is_(None), Task.owner_id == current.id))
    if status:
        stmt = stmt.where(Task.status == status)
    stmt = apply_sort(stmt, Task, "due_date", "asc")
    rows, total = await paginate(db, stmt, page, page_size)
    return resp.page([TaskOut.model_validate(r).model_dump(mode="json") for r in rows], total, page, page_size)


@_aux.post("/{task_id}/complete", summary="完成任务")
async def complete_task(
    task_id: uuid.UUID,
    db: DbSession,
    _: User = Depends(require_permission("task:update")),
) -> dict[str, Any]:
    task = await get_or_404(db, Task, task_id, "任务")
    task.status = "DONE"
    task.completed_at = utcnow()
    await db.commit()
    await db.refresh(task)
    return resp.ok(TaskOut.model_validate(task).model_dump(mode="json"))


_crud = build_crud_router(
    CrudConfig(
        model=Task,
        prefix="/tasks",
        tag="M3-任务",
        name="任务",
        create_schema=TaskCreate,
        update_schema=TaskUpdate,
        out_schema=TaskOut,
        view_permission="task:view",
        create_permission="task:create",
        update_permission="task:update",
        delete_permission="task:update",
        search_fields=("title", "content"),
        filter_fields={
            "status": "status",
            "priority": "priority",
            "biz_type": "biz_type",
            "biz_id": "biz_id",
        },
        description="任务 CRUD，支持按状态/优先级/关联业务过滤",
    )
)

router = APIRouter()
router.include_router(_aux)
router.include_router(_crud)
