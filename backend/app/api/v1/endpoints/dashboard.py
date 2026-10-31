"""工作台（Dashboard）数据接口（M1 框架版，业务指标待 M2-M5 接入）。"""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import func, select

from app.core import response as resp
from app.core.deps import CurrentUser, DbSession
from app.domain.state_machine import (
    INQUIRY_STATUSES,
    OPPORTUNITY_STAGES,
    QUOTATION_STATUSES,
    STAGE_LABELS,
)
from app.models.audit import AuditLog
from app.models.user import Department, Role, User
from app.services import feature_flag as flag_service

router = APIRouter(prefix="/dashboard", tags=["工作台"])


@router.get("", summary="工作台概览")
async def overview(user: CurrentUser, db: DbSession):
    today = func.date_trunc("day", func.now())
    today_audit = (
        await db.execute(
            select(func.count()).select_from(AuditLog).where(AuditLog.created_at >= today, AuditLog.success.is_(True))
        )
    ).scalar_one()
    user_count = (
        await db.execute(select(func.count()).select_from(User).where(User.deleted_at.is_(None)))
    ).scalar_one()
    dept_count = (
        await db.execute(select(func.count()).select_from(Department).where(Department.deleted_at.is_(None)))
    ).scalar_one()
    role_count = (
        await db.execute(select(func.count()).select_from(Role).where(Role.deleted_at.is_(None)))
    ).scalar_one()
    flags = await flag_service.get_all_flags()

    stages = [{"stage": s, "label": STAGE_LABELS.get(s, s), "count": 0} for s in OPPORTUNITY_STAGES]

    return resp.ok(
        {
            "user": {
                "id": str(user.id),
                "name": user.name,
                "roles": user.role_codes,
                "department": user.department.name if user.department else None,
            },
            "stats": {
                "customers": 0,
                "leads": 0,
                "opportunities": 0,
                "inquiries": 0,
                "quotations": 0,
                "pending_approvals": 0,
            },
            "todo": {"tasks": 0},
            "system": {
                "users": user_count,
                "departments": dept_count,
                "roles": role_count,
                "today_operations": today_audit,
            },
            "opportunity_funnel": stages,
            "inquiry_statuses": INQUIRY_STATUSES,
            "quotation_statuses": QUOTATION_STATUSES,
            "feature_flags": flags,
            "milestone": {"current": "M1", "name": "系统骨架", "progress": 100},
        }
    )


@router.get("/meta", summary="系统元数据（状态机/字典/枚举）")
async def meta(user: CurrentUser, db: DbSession):
    return resp.ok(
        {
            "opportunity_stages": [{"value": s, "label": STAGE_LABELS.get(s, s)} for s in OPPORTUNITY_STAGES],
            "inquiry_statuses": INQUIRY_STATUSES,
            "quotation_statuses": QUOTATION_STATUSES,
            "feature_flags": await flag_service.get_all_flags(),
        }
    )
