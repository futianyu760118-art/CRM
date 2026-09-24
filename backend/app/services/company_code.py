"""客户三段式编码服务。

编码规则（业务确认）：
    {业务员编号}-{该业务员第N个客户}-{公司第N个客户}
例：HJ003-176-576
    - HJ003：业务员编号，HJ 为固定前缀，003 为 K3 职员编号（user.code）
    - 176  ：该业务员名下的第 176 个客户（同一客户多币别只计 1 次）
    - 576  ：公司第 576 个客户（同一客户多币别只计 1 次）

同一客户不同币别：不新建客户记录，在 business_code 追加一条币别编码
    HJ003-176-576-1 / -2 / -3 …

未维护业务员编号（K3 职员号）时，回退为 CUS-0001 形式，保证业务不阻塞。
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business import BusinessCode, Company
from app.models.user import User
from app.services.number_sequence import (
    GLOBAL_COUNTER,
    next_counter,
    owner_counter_key,
)

FALLBACK_PREFIX = "CUS"
CURRENCY_CODE_TYPE = "CURRENCY"


def build_code(owner_code: str | None, owner_seq: int, global_seq: int) -> str:
    if owner_code:
        return f"{owner_code}-{owner_seq:03d}-{global_seq:03d}"
    return f"{FALLBACK_PREFIX}-{global_seq:04d}"


async def next_company_code(owner: User | None) -> tuple[str, int, int]:
    """返回 (客户编码, 业务员内序号, 公司序号)。"""
    global_seq = await next_counter(GLOBAL_COUNTER)
    if owner is not None and owner.code:
        owner_seq = await next_counter(owner_counter_key(owner.id))
        return build_code(owner.code, owner_seq, global_seq), owner_seq, global_seq
    return build_code(None, 0, global_seq), 0, global_seq


async def preview_next_code(owner: User | None) -> tuple[str, int, int]:
    """只读预览下一个编码（不消耗计数器），返回 (编码, 业务员序号, 公司序号)。"""
    from app.services.number_sequence import peek_counter

    global_seq = await peek_counter(GLOBAL_COUNTER)
    if owner is not None and owner.code:
        owner_seq = await peek_counter(owner_counter_key(owner.id))
        return build_code(owner.code, owner_seq, global_seq), owner_seq, global_seq
    return build_code(None, 0, global_seq), 0, global_seq


async def ensure_primary_code(db: AsyncSession, company: Company) -> BusinessCode:
    """确保客户存在内部主编码记录。"""
    existing = (
        (
            await db.execute(
                select(BusinessCode).where(
                    BusinessCode.company_id == company.id,
                    BusinessCode.code_type == "INTERNAL",
                    BusinessCode.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .first()
    )
    if existing is not None:
        existing.code = company.code
        return existing
    row = BusinessCode(
        company_id=company.id,
        code=company.code,
        code_type="INTERNAL",
        is_primary=True,
    )
    db.add(row)
    await db.flush()
    return row


async def add_currency_code(db: AsyncSession, company: Company, currency: str) -> tuple[BusinessCode, bool]:
    """为客户的某个币别追加业务编码，返回 (编码记录, 是否新建)。"""
    currency = currency.strip().upper()

    existing = (
        (
            await db.execute(
                select(BusinessCode).where(
                    BusinessCode.company_id == company.id,
                    BusinessCode.code_type == CURRENCY_CODE_TYPE,
                    BusinessCode.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )

    for row in existing:
        if (row.currency or "").upper() == currency:
            return row, False

    max_suffix = 0
    for row in existing:
        tail = row.code.rsplit("-", 1)[-1]
        if tail.isdigit():
            max_suffix = max(max_suffix, int(tail))

    row = BusinessCode(
        company_id=company.id,
        code=f"{company.code}-{max_suffix + 1}",
        code_type=CURRENCY_CODE_TYPE,
        currency=currency,
        is_primary=False,
    )
    db.add(row)
    await db.flush()
    return row, True


async def codes_of(db: AsyncSession, company_id: uuid.UUID) -> list[BusinessCode]:
    return list(
        (
            await db.execute(
                select(BusinessCode)
                .where(BusinessCode.company_id == company_id, BusinessCode.deleted_at.is_(None))
                .order_by(BusinessCode.is_primary.desc(), BusinessCode.created_at)
            )
        )
        .scalars()
        .all()
    )
