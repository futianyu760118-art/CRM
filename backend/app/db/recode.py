"""存量数据重算：业务员编号 + 客户三段式编码 + 币别编码。

用法：
    python -m app.db.recode            # 预览（dry-run，不写库）
    python -m app.db.recode --apply    # 实际写入

规则：
    客户编码 = {业务员编号}-{该业务员第N个客户}-{公司第N个客户}，如 HJ003-176-576
    同一客户多币别 = 在主码后追加 -1 / -2 …
    - 业务员编号（user.code）为空时按创建时间顺序补 HJ001、HJ002 …
    - 客户按创建时间顺序重新编号；同一客户只计 1 次
"""

from __future__ import annotations

import sys

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory, engine
from app.models.business import BusinessCode, Company
from app.models.user import User
from app.services import company_code
from app.services.number_sequence import ensure_sequence_floors


async def allocate_user_codes(db: AsyncSession) -> dict[str, str]:
    users = (await db.execute(select(User).order_by(User.created_at, User.username))).scalars().all()
    taken = {u.code for u in users if u.code}
    seq = 0
    assigned: dict[str, str] = {}
    for user in users:
        if user.code:
            continue
        while True:
            seq += 1
            candidate = f"HJ{seq:03d}"
            if candidate not in taken:
                break
        user.code = candidate
        taken.add(candidate)
        assigned[user.username] = candidate
    return assigned


async def recode_companies(db: AsyncSession) -> list[tuple[str, str]]:
    companies = (await db.execute(select(Company).order_by(Company.created_at, Company.code))).scalars().all()
    owners = {u.id: u for u in (await db.execute(select(User))).scalars().all()}

    owner_seq: dict[str, int] = {}
    changes: list[tuple[str, str]] = []

    for global_seq, company in enumerate(companies, start=1):
        owner = owners.get(company.owner_id) if company.owner_id else None
        if owner is not None and owner.code:
            key = str(owner.id)
            owner_seq[key] = owner_seq.get(key, 0) + 1
            new_code = company_code.build_code(owner.code, owner_seq[key], global_seq)
            company.owner_seq = owner_seq[key]
        else:
            new_code = company_code.build_code(None, 0, global_seq)
            company.owner_seq = 0
        company.global_seq = global_seq
        if new_code != company.code:
            changes.append((company.code, new_code))
        company.code = new_code

    # 重写业务编码记录
    await db.flush()
    for company in companies:
        await db.execute(delete(BusinessCode).where(BusinessCode.company_id == company.id))
        await db.flush()
        await company_code.ensure_primary_code(db, company)
        if company.currency:
            await company_code.add_currency_code(db, company, company.currency)

    return changes


async def main() -> None:
    apply = "--apply" in sys.argv
    async with async_session_factory() as db:
        assigned = await allocate_user_codes(db)
        changes = await recode_companies(db)
        if apply:
            await db.commit()
        else:
            await db.rollback()

    print(f"[recode] 模式：{'APPLY（已写库）' if apply else 'DRY-RUN（未写库）'}")
    print(f"[recode] 补发业务员编号 {len(assigned)} 个：{assigned or '无'}")
    print(f"[recode] 客户编码变更 {len(changes)} 条：")
    for old, new in changes:
        print(f"         {old}  ->  {new}")

    if apply:
        await ensure_sequence_floors()
        print("[recode] 编号计数器已对齐")
    await engine.dispose()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
