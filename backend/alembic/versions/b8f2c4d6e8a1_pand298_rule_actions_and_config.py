"""pand-298 price_multiplier rules to margin_delta and new system config

Revision ID: b8f2c4d6e8a1
Revises: 4c1f8a2b9d3e
Create Date: 2026-10-22 12:00:00.000000

M2.5-D2 之后规则引擎只调利润率，``price_multiplier`` 动作被静默忽略。
本迁移把存量规则中的 ``price_multiplier`` 等价转换为 ``margin_delta``
（``margin_delta = 原 margin_delta + (price_multiplier - 1)``），并补齐
折扣金额门槛与可维护汇率的系统参数默认值。

数据迁移不可逆：降级不回滚规则动作（无法区分转换前已存在的 margin_delta）。
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'b8f2c4d6e8a1'
down_revision: str | None = '4c1f8a2b9d3e'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_CONFIG_ROWS: list[tuple[str, str, str, str]] = [
    ("pricing.exchange_rate", "7.25", "pricing", "16-10 汇率（单一参数人工维护，报价创建时快照）"),
    (
        "approval.discount_amount_threshold_enabled",
        "false",
        "approval",
        "折扣金额门槛开关（M2.6-D1 附加条件，默认关闭）",
    ),
    (
        "approval.discount_amount_threshold",
        "50000",
        "approval",
        "折扣金额门槛（开启后金额超过门槛自动升一级审批）",
    ),
]


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE pricing_rule
            SET actions = (actions - 'price_multiplier')
                || jsonb_build_object(
                    'margin_delta',
                    COALESCE((actions ->> 'margin_delta')::numeric, 0)
                    + ((actions ->> 'price_multiplier')::numeric - 1)
                )
            WHERE actions ? 'price_multiplier'
            """
        )
    )

    for key, value, group, description in _CONFIG_ROWS:
        op.execute(
            sa.text(
                """
                INSERT INTO system_config (id, key, value, "group", description, created_at, updated_at)
                SELECT gen_random_uuid(), :key, :value, :group, :description, now(), now()
                WHERE NOT EXISTS (SELECT 1 FROM system_config WHERE key = :key)
                """
            ).bindparams(key=key, value=value, group=group, description=description)
        )


def downgrade() -> None:
    # 只回滚配置行；规则动作转换不可逆（无法判断 margin_delta 是否由本次转换产生）。
    for key, _value, _group, _description in _CONFIG_ROWS:
        op.execute(sa.text("DELETE FROM system_config WHERE key = :key").bindparams(key=key))
