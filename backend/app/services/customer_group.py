"""客户分组（新 / 活跃 / 休眠，PAND-314 §2.2 / CUST-02）。

派生数据不落库：列表过滤与顶部计数共用同一组 SQL 条件（保证互斥且求和一致），
单条展示原因由 ``classify`` 按相同口径计算。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import ColumnElement, and_, exists, func, not_, or_, select

from app.models.business import Activity, Company
from app.models.sales import SalesOrder

GROUP_NEW = "new"
GROUP_ACTIVE = "active"
GROUP_DORMANT = "dormant"
GROUP_ALL = "all"
GROUPS = (GROUP_ALL, GROUP_NEW, GROUP_ACTIVE, GROUP_DORMANT)

NEW_DAYS = 90
DORMANT_DAYS = 180
DORMANT_CUSTOMER_STATUS = "未合作休眠客户"
CLOSED_ORDER_STATUSES = ("completed", "closed")


def new_condition(column: Any, now: datetime) -> ColumnElement[bool]:
    """新客户：建档 ≤90 天且不存在已完成/已关闭订单。"""
    since = now - timedelta(days=NEW_DAYS)
    closed_order = exists(
        select(SalesOrder.id).where(
            SalesOrder.company_id == column.id,
            SalesOrder.deleted_at.is_(None),
            SalesOrder.status.in_(CLOSED_ORDER_STATUSES),
        )
    )
    return and_(column.created_at >= since, not_(closed_order))


def last_followup_expr(column: Any) -> ColumnElement[datetime]:
    return (
        select(func.max(Activity.happened_at))
        .where(Activity.company_id == column.id, Activity.deleted_at.is_(None))
        .correlate_except(Activity)
        .scalar_subquery()
    )


def dormant_condition(column: Any, now: datetime) -> ColumnElement[bool]:
    """休眠：非新客户，且（状态为未合作休眠 / 最近跟进超 180 天 / 无跟进且建档超 180 天）。"""
    older = now - timedelta(days=DORMANT_DAYS)
    last_followup = last_followup_expr(column)
    return and_(
        not_(new_condition(column, now)),
        or_(
            column.customer_status == DORMANT_CUSTOMER_STATUS,
            last_followup <= older,
            and_(last_followup.is_(None), column.created_at <= older),
        ),
    )


def active_condition(column: Any, now: datetime) -> ColumnElement[bool]:
    return not_(or_(new_condition(column, now), dormant_condition(column, now)))


def group_condition(group: str | None, column: Any, now: datetime) -> ColumnElement[bool] | None:
    if not group or group == GROUP_ALL:
        return None
    if group == GROUP_NEW:
        return new_condition(column, now)
    if group == GROUP_DORMANT:
        return dormant_condition(column, now)
    return active_condition(column, now)


def classify(
    created_at: datetime | None,
    customer_status: str | None,
    last_followup_at: datetime | None,
    has_closed_order: bool,
    now: datetime,
) -> tuple[str, str]:
    """返回 ``(group, group_reason)``，口径与 SQL 条件一致（纯逻辑，便于自检）。"""
    if created_at is None:
        created_at = now
    is_new = created_at >= now - timedelta(days=NEW_DAYS) and not has_closed_order
    if is_new:
        return GROUP_NEW, "新客户：建档 90 天内且无已完成/已关闭订单"

    older = now - timedelta(days=DORMANT_DAYS)
    if customer_status == DORMANT_CUSTOMER_STATUS:
        return GROUP_DORMANT, f"休眠判定：客户状态为「{DORMANT_CUSTOMER_STATUS}」"
    if last_followup_at is not None and last_followup_at <= older:
        days = max((now - last_followup_at).days, 0)
        return GROUP_DORMANT, f"休眠判定：最近跟进 {days} 天前"
    if last_followup_at is None and created_at <= older:
        days = max((now - created_at).days, 0)
        return GROUP_DORMANT, f"休眠判定：无跟进记录且建档 {days} 天"
    return GROUP_ACTIVE, "活跃客户：近 180 天有跟进或已有成交订单"


def group_reason_for(
    company: Any,
    last_followup_at: datetime | None,
    has_closed_order: bool,
    now: datetime,
) -> tuple[str, str]:
    return classify(company.created_at, company.customer_status, last_followup_at, has_closed_order, now)


async def last_followup_map(db: Any, company_ids: set[Any]) -> dict[Any, datetime]:
    if not company_ids:
        return {}
    rows = (
        await db.execute(
            select(Activity.company_id, func.max(Activity.happened_at))
            .where(Activity.company_id.in_(company_ids), Activity.deleted_at.is_(None))
            .group_by(Activity.company_id)
        )
    ).all()
    return {row[0]: row[1] for row in rows if row[0] and row[1]}


async def closed_order_company_ids(db: Any, company_ids: set[Any]) -> set[Any]:
    if not company_ids:
        return set()
    rows = (
        await db.execute(
            select(SalesOrder.company_id)
            .where(
                SalesOrder.company_id.in_(company_ids),
                SalesOrder.deleted_at.is_(None),
                SalesOrder.status.in_(CLOSED_ORDER_STATUSES),
            )
            .distinct()
        )
    ).all()
    return {row[0] for row in rows if row[0]}


async def summary_counts(db: Any, scoped_company_ids: Any, now: datetime) -> dict[str, int]:
    """按已套用数据权限的 company.id 子查询统计四组数量。"""
    rows = (
        await db.execute(
            select(
                func.count(Company.id),
                func.count(Company.id).filter(new_condition(Company, now)),
                func.count(Company.id).filter(active_condition(Company, now)),
                func.count(Company.id).filter(dormant_condition(Company, now)),
            ).where(Company.id.in_(scoped_company_ids))
        )
    ).one()
    return {
        GROUP_ALL: int(rows[0] or 0),
        GROUP_NEW: int(rows[1] or 0),
        GROUP_ACTIVE: int(rows[2] or 0),
        GROUP_DORMANT: int(rows[3] or 0),
    }


__all__ = [
    "GROUP_ACTIVE",
    "GROUP_ALL",
    "GROUP_DORMANT",
    "GROUP_NEW",
    "GROUPS",
    "active_condition",
    "classify",
    "closed_order_company_ids",
    "dormant_condition",
    "group_condition",
    "group_reason_for",
    "last_followup_map",
    "new_condition",
    "summary_counts",
]
