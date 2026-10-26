"""CRM 客户存量回填 EBMS（PAND-309 R2）。

切流前创建的客户只有 CRM 侧记录；本脚本对指定客户重新入队 ``customer.upserted``，
由 crm-worker 按 60s 周期投递，EBMS 按自然键（名称）幂等落库。

同时提供测试残留清理：``--delete-name`` 只做本地软删除，不产生出站事件
（该客户从未进入 EBMS，发 deleted 反而制造噪声）。

用法（在 crm-backend 容器内执行）::

    python /tmp/ebms_backfill_customers.py --ids-file /tmp/backfill_ids.txt
    python /tmp/ebms_backfill_customers.py --delete-name "冒烟测试客户有限公司"
    python /tmp/ebms_backfill_customers.py --ids-file /tmp/backfill_ids.txt --dry-run

``--ids-file`` 每行一个 company.id；重复执行安全（同内容事件在 EBMS 侧返回 skipped）。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from typing import Any

from sqlalchemy import select

from app.db.base import utcnow
from app.db.session import async_session_factory
from app.models.business import Company
from app.services import ebms_sync


def _load_ids(path: str) -> list[uuid.UUID]:
    ids: list[uuid.UUID] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            raw = line.strip()
            if not raw or raw.startswith("#"):
                continue
            ids.append(uuid.UUID(raw))
    return ids


async def _backfill(ids: list[uuid.UUID], dry_run: bool) -> dict[str, Any]:
    summary: dict[str, Any] = {"requested": len(ids), "found": 0, "queued": 0, "skipped_existing": 0, "missing": []}
    async with async_session_factory() as db:
        rows = (
            (await db.execute(select(Company).where(Company.id.in_(ids), Company.deleted_at.is_(None))))
            .scalars()
            .all()
        )
        summary["found"] = len(rows)
        summary["missing"] = sorted({str(i) for i in ids} - {str(r.id) for r in rows})
        for company in rows:
            company.sync_status = "PENDING"
            if dry_run:
                summary["queued"] += 1
                continue
            result = await ebms_sync.emit_upsert(db, "Customer", company)
            if result.get("created"):
                summary["queued"] += 1
            else:
                summary["skipped_existing"] += 1
        if dry_run:
            await db.rollback()
        else:
            await db.commit()
    return summary


async def _delete_by_name(name: str, dry_run: bool) -> dict[str, Any]:
    async with async_session_factory() as db:
        rows = (
            (await db.execute(select(Company).where(Company.name == name, Company.deleted_at.is_(None))))
            .scalars()
            .all()
        )
        for company in rows:
            company.deleted_at = utcnow()
        if dry_run:
            await db.rollback()
        else:
            await db.commit()
    return {"name": name, "matched": len(rows), "deleted": 0 if dry_run else len(rows)}


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ids-file", help="待回填的 company.id 列表（每行一个 UUID）")
    parser.add_argument("--delete-name", help="按精确名称软删除测试残留（不发出站事件）")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.ids_file and not args.delete_name:
        parser.error("至少提供 --ids-file 或 --delete-name")

    if args.ids_file:
        print(await _backfill(_load_ids(args.ids_file), args.dry_run), flush=True)
    if args.delete_name:
        print(await _delete_by_name(args.delete_name, args.dry_run), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
