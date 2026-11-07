"""pand-330 M1 fact_owner 索引收口

Revision ID: pand330a3
Revises: pand330a2
Create Date: 2026-11-03 10:20:00.000000

架构 §5 revision_03（收口）：10 张关键对象表 ``fact_owner`` 索引；NOT NULL 已由
``pand330a1`` 的 server_default 直接落定，无需二次收紧。
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "pand330a3"
down_revision: str | None = "pand330a2"
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


def upgrade() -> None:
    for table in _OBJECT_TABLES:
        op.create_index(op.f(f"ix_{table}_fact_owner"), table, ["fact_owner"], unique=False)


def downgrade() -> None:
    for table in reversed(_OBJECT_TABLES):
        op.drop_index(op.f(f"ix_{table}_fact_owner"), table_name=table)
