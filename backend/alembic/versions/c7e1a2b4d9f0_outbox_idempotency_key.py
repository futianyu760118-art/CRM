"""integration_outbox 增加 idempotency_key（EBMS 契约投递对账）

Revision ID: c7e1a2b4d9f0
Revises: 139d6e2faef6
Create Date: 2026-10-07 10:00:00.000000

纯附加变更：为 IntegrationOutbox 增加与 IntegrationLog.idempotency_key 对齐的
幂等键列（可空 + 索引），用于「同一契约不重复入队」与 Outbox↔日志精确定位对账。
存量行为 NULL，不影响既有 K3 数据。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c7e1a2b4d9f0"
down_revision: str | None = "139d6e2faef6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("integration_outbox", sa.Column("idempotency_key", sa.String(length=200), nullable=True))
    op.create_index(
        op.f("ix_integration_outbox_idempotency_key"), "integration_outbox", ["idempotency_key"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_integration_outbox_idempotency_key"), table_name="integration_outbox")
    op.drop_column("integration_outbox", "idempotency_key")
