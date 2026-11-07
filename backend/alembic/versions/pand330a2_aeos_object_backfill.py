"""pand-330 M1 存量回填与 record_owner 覆盖率

Revision ID: pand330a2
Revises: pand330a1
Create Date: 2026-11-03 10:10:00.000000

架构 §5 revision_02（回填）：
- 10 张关键对象表按主键分页回填 ``tenant_id/revision/fact_owner/consumer``（存量统一
  ``revision=1``，不试图还原历史版本数，Q7）；
- 输出 ``record_owner(owner_id)`` 覆盖率：总数 / 已归属数 / 未归属清单（F4-A03）。
- 回填不伪造归属：``owner_id`` 为空者保持为空，只输出清单供业务清零。
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "pand330a2"
down_revision: str | None = "pand330a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OBJECT_TABLES: tuple[str, ...] = (
    "company",
    "contact",
    "lead",
    "opportunity",
    "inquiry",
    "quotation",
    "sales_order",
    "sample",
    "quote_library",
    "feedback",
)

_BATCH = 1000
_SAMPLE_LIMIT = 50


def _backfill(bind, table: str) -> None:
    while True:
        ids = bind.execute(
            sa.text(
                f"""
                SELECT id FROM {table}
                WHERE tenant_id IS DISTINCT FROM 'default'
                   OR revision IS NULL
                   OR fact_owner IS DISTINCT FROM 'M05'
                   OR consumer IS NULL
                ORDER BY id
                LIMIT :limit
                """
            ),
            {"limit": _BATCH},
        ).scalars().all()
        if not ids:
            return
        # 存量统一为默认口径（Q7：不还原历史 revision），并保证本轮选中的行全部
        # 脱离 WHERE 条件，分页不会重复命中。
        bind.execute(
            sa.text(
                f"""
                UPDATE {table}
                SET tenant_id = 'default',
                    revision = 1,
                    fact_owner = 'M05',
                    consumer = '[]'::jsonb
                WHERE id = ANY(:ids)
                """
            ),
            {"ids": ids},
        )


def _coverage(bind, table: str) -> None:
    total, owned = bind.execute(
        sa.text(f"SELECT count(*), count(owner_id) FROM {table}")
    ).one()
    orphans = bind.execute(
        sa.text(f"SELECT id FROM {table} WHERE owner_id IS NULL ORDER BY id LIMIT {_SAMPLE_LIMIT}")
    ).scalars().all()
    print(  # noqa: T201 - 迁移审计输出（F4-A03）
        f"[pand330a2] {table}: total={total} owned={owned} unowned={total - owned} "
        f"sample={[str(i) for i in orphans]}"
    )


def upgrade() -> None:
    bind = op.get_bind()
    for table in _OBJECT_TABLES:
        _backfill(bind, table)
        _coverage(bind, table)


def downgrade() -> None:
    # 回填只写默认值，不删业务数据；降级保持数据（列由 pand330a1 的 downgrade 移除）。
    pass
