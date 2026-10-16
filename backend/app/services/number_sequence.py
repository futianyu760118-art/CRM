"""编号规则服务：并发安全（Redis INCR，失败回退数据库行锁）。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.db.redis_client import get_redis
from app.db.session import async_session_factory
from app.models.support import NumberSequence

# 预置编号类型：key -> (名称, 前缀, 周期)
SEQUENCE_DEFS: dict[str, tuple[str, str, str]] = {
    "lead": ("线索编号", "LEAD", "MONTH"),
    "opportunity": ("商机编号", "OPP", "MONTH"),
    "inquiry": ("询价编号", "JFX", "DAY"),
    "quotation": ("报价编号", "QUO", "MONTH"),
    "order": ("订单编号", "ORD", "MONTH"),
    "company": ("客户编码", "CUS", "NEVER"),
    # 销售中心 6 模块（PAND-249）
    "sample": ("样品编号", "SMP", "NEVER"),
    "feedback": ("反馈编号", "FB", "DAY"),
}


def _redis_seq_key(key: str, period: str, now: datetime | None = None) -> str:
    """Redis 序列键：询价单为全局序号，其余按期间分桶。"""
    if key == "inquiry":
        return f"crm:seq:{key}"
    moment = now or datetime.now(UTC)
    return f"crm:seq:{key}:{_period_key(period, moment)}"


def _period_key(period: str, now: datetime) -> str:
    if period == "YEAR":
        return now.strftime("%Y")
    if period == "DAY":
        return now.strftime("%Y%m%d")
    if period == "MONTH":
        return now.strftime("%Y%m")
    return "0"


def _format(prefix: str, period: str, now: datetime, seq: int) -> str:
    p = _period_key(period, now)
    if period == "NEVER":
        return f"{prefix}-{seq:04d}"
    return f"{prefix}-{p}-{seq:04d}"


def format_number(key: str, now: datetime, seq: int) -> str:
    """按业务规则格式化编号。

    - inquiry（询价单）：JFX{YYYYMMDD}{序号:03d}，如 JFX20260916001（AC-M2.2 `^JFX\\d{8}\\d{3}$`）
    - feedback（反馈）：FB{YYYYMMDD}{序号:03d}
    - sample（样品）：SMP-{序号:04d}（全局递增，不按日重置）
    - 其余沿用 {PREFIX}-{期间}-{序号:04d}
    """
    if key not in SEQUENCE_DEFS:
        raise KeyError(f"未定义的编号类型: {key}")
    if key == "inquiry":
        return f"JFX{now:%Y%m%d}{seq:03d}"
    if key == "feedback":
        return f"FB{now:%Y%m%d}{seq:03d}"
    _, prefix, period = SEQUENCE_DEFS[key]
    return _format(prefix, period, now, seq)


async def next_number(key: str) -> str:
    """生成下一个编号。"""
    if key not in SEQUENCE_DEFS:
        raise KeyError(f"未定义的编号类型: {key}")
    _, _prefix, period = SEQUENCE_DEFS[key]
    now = datetime.now(UTC)
    counter_key = key if key == "inquiry" else f"{key}:{_period_key(period, now)}"

    redis = get_redis()
    try:
        seq = await redis.incr(f"crm:seq:{counter_key}")
        return format_number(key, now, seq)
    except Exception:  # noqa: BLE001 - Redis 不可用时降级
        pass

    return await _next_number_db(key, "", period, now)


async def _next_number_db(key: str, prefix: str, period: str, now: datetime) -> str:
    db_key = key if key == "inquiry" else f"{key}:{_period_key(period, now)}"
    async with async_session_factory() as session:
        stmt = select(NumberSequence).where(NumberSequence.key == db_key).with_for_update()
        row = (await session.execute(stmt)).scalar_one_or_none()
        if row is None:
            row = NumberSequence(key=db_key, name=key, pattern="{0000}", reset_period=period)
            session.add(row)
            await session.flush()
        row.current_value += 1
        value = row.current_value
        await session.commit()
    return format_number(key, now, value)


async def peek_next_number(key: str) -> str:
    """只读预览（不消耗序号），用于前端展示。"""
    if key not in SEQUENCE_DEFS:
        raise KeyError(f"未定义的编号类型: {key}")
    _, _prefix, period = SEQUENCE_DEFS[key]
    now = datetime.now(UTC)
    counter_key = key if key == "inquiry" else f"{key}:{_period_key(period, now)}"
    redis = get_redis()
    try:
        val = await redis.get(f"crm:seq:{counter_key}")
        seq = int(val) + 1 if val else 1
    except Exception:  # noqa: BLE001
        seq = 1
    return format_number(key, now, seq)


# key -> (模型, 编号字段)，用于启动时对齐序列下限
def _sequence_sources() -> dict[str, tuple[Any, str]]:
    from app.models.business import Company, Inquiry, Lead, Opportunity
    from app.models.pricing import Quotation
    from app.models.sales import Feedback, Sample

    return {
        "lead": (Lead, "lead_no"),
        "opportunity": (Opportunity, "opportunity_no"),
        "inquiry": (Inquiry, "inquiry_no"),
        "quotation": (Quotation, "quotation_no"),
        "company": (Company, "code"),
        "sample": (Sample, "sample_no"),
        "feedback": (Feedback, "feedback_no"),
    }


async def ensure_sequence_floors() -> dict[str, int]:
    """将 Redis 计数器与数据库已有编号对齐，避免主键冲突/重复编号。

    例如历史数据已存在 CUS-0002 而 Redis 计数器为 0 时，会自动抬升到 2。
    """
    from sqlalchemy import select

    from app.db.session import async_session_factory

    floors: dict[str, int] = {}
    sources = _sequence_sources()
    async with async_session_factory() as session:
        for key, (model, column) in sources.items():
            if key not in SEQUENCE_DEFS:
                continue
            _, _prefix, period = SEQUENCE_DEFS[key]
            values = (
                (await session.execute(select(getattr(model, column)).where(model.deleted_at.is_(None))))
                .scalars()
                .all()
            )
            max_seq = 0
            for value in values:
                if not value:
                    continue
                tail = str(value).rsplit("-", 1)[-1]
                if tail.isdigit():
                    max_seq = max(max_seq, int(tail))
            floors[key] = max_seq
            if max_seq <= 0:
                continue
            await _set_counter_floor(_redis_seq_key(key, period), max_seq)

        await _align_company_counters(session, floors)
    return floors


async def _align_company_counters(session: Any, floors: dict[str, int]) -> None:
    """三段式客户编码的两个计数器对齐（公司级 / 业务员级）。"""
    from sqlalchemy import func as sa_func

    from app.models.business import Company

    global_seq = (
        await session.execute(
            select(sa_func.coalesce(sa_func.max(Company.global_seq), 0)).where(Company.deleted_at.is_(None))
        )
    ).scalar_one()
    floor = max(int(global_seq), int(floors.get("company", 0)))
    floors["company_global"] = floor
    await _set_counter_floor(COUNTER_PREFIX + GLOBAL_COUNTER, floor)

    rows = (
        await session.execute(
            select(Company.owner_id, sa_func.max(Company.owner_seq))
            .where(Company.deleted_at.is_(None), Company.owner_id.isnot(None))
            .group_by(Company.owner_id)
        )
    ).all()
    for owner_id, seq in rows:
        if owner_id is None or not seq:
            continue
        await _set_counter_floor(COUNTER_PREFIX + owner_counter_key(owner_id), int(seq))


# ------------------------------------------------------------------ 通用计数器


COUNTER_PREFIX = "crm:counter:"
GLOBAL_COUNTER = "company_global"


def owner_counter_key(owner_id: Any) -> str:
    return f"company_owner_{owner_id}"


async def _set_counter_floor(full_key: str, floor: int) -> None:
    if floor <= 0:
        return
    try:
        redis = get_redis()
        current = await redis.get(full_key)
        if current is None or int(current) < floor:
            await redis.set(full_key, floor)
    except Exception:  # noqa: BLE001
        pass


async def next_counter(key: str) -> int:
    """并发安全的整数计数器（用于三段式编码）。Redis 不可用时回退数据库行锁。"""
    redis = get_redis()
    try:
        return int(await redis.incr(COUNTER_PREFIX + key))
    except Exception:  # noqa: BLE001
        pass

    from app.db.session import async_session_factory

    async with async_session_factory() as session:
        # 兜底时必须先与库内现有最大值对齐，否则 Redis 丢失/宕机后会生成重复编码
        floor = await _counter_floor(session, key)
        stmt = select(NumberSequence).where(NumberSequence.key == key).with_for_update()
        row = (await session.execute(stmt)).scalar_one_or_none()
        if row is None:
            row = NumberSequence(key=key, name=key, pattern="{0000}", reset_period="NEVER")
            session.add(row)
            await session.flush()
        row.current_value = max(int(row.current_value or 0), floor) + 1
        value = row.current_value
        await session.commit()
    return value


async def peek_counter(key: str) -> int:
    """只读预览计数器的下一个值（不消耗）。"""
    redis = get_redis()
    try:
        raw = await redis.get(COUNTER_PREFIX + key)
        return (int(raw) if raw else 0) + 1
    except Exception:  # noqa: BLE001
        pass

    from app.db.session import async_session_factory

    async with async_session_factory() as session:
        floor = await _counter_floor(session, key)
        row = (await session.execute(select(NumberSequence).where(NumberSequence.key == key))).scalar_one_or_none()
        current = max(int(row.current_value or 0) if row else 0, floor)
    return current + 1


async def _counter_floor(session: Any, key: str) -> int:
    """从业务表推导计数器的下限，保证兜底路径不会发出重复编号。"""
    from sqlalchemy import func as sa_func

    from app.models.business import Company

    if key == GLOBAL_COUNTER:
        return int(
            (
                await session.execute(
                    select(sa_func.coalesce(sa_func.max(Company.global_seq), 0)).where(Company.deleted_at.is_(None))
                )
            ).scalar_one()
            or 0
        )

    prefix = "company_owner_"
    if key.startswith(prefix):
        raw = key[len(prefix) :]
        try:
            owner_id = uuid.UUID(raw)
        except ValueError:
            return 0
        return int(
            (
                await session.execute(
                    select(sa_func.coalesce(sa_func.max(Company.owner_seq), 0)).where(
                        Company.owner_id == owner_id, Company.deleted_at.is_(None)
                    )
                )
            ).scalar_one()
            or 0
        )
    return 0
