"""m2.5 m2.6 cost structure and discount approval

Revision ID: 4c1f8a2b9d3e
Revises: e9f3a1c8b2d4
Create Date: 2026-10-17 10:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '4c1f8a2b9d3e'
down_revision: str | None = 'e9f3a1c8b2d4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # pricing_record —— M2.5 成本并轨 9 项（loss_cost 默认 0）+ 报价公式（base_cost/final_price）
    op.add_column(
        'pricing_record',
        sa.Column('loss_cost', sa.Numeric(precision=18, scale=4), server_default='0', nullable=True),
    )
    op.alter_column('pricing_record', 'loss_cost', server_default=None)
    op.add_column('pricing_record', sa.Column('base_cost', sa.Numeric(precision=18, scale=4), nullable=True))
    op.add_column('pricing_record', sa.Column('final_price', sa.Numeric(precision=18, scale=4), nullable=True))
    op.add_column(
        'pricing_record',
        sa.Column('discount_rate', sa.Numeric(precision=10, scale=4), server_default='1', nullable=False),
    )
    op.alter_column('pricing_record', 'discount_rate', server_default=None)

    # quotation —— M2.6 折扣率（审批触发 + 相对标准价）
    op.add_column(
        'quotation',
        sa.Column('discount_rate', sa.Numeric(precision=10, scale=4), server_default='1', nullable=False),
    )
    op.alter_column('quotation', 'discount_rate', server_default=None)

    # approval_instance —— 审批折扣率快照
    op.add_column('approval_instance', sa.Column('discount_rate', sa.Numeric(precision=10, scale=4), nullable=True))


def downgrade() -> None:
    op.drop_column('approval_instance', 'discount_rate')
    op.drop_column('quotation', 'discount_rate')
    op.drop_column('pricing_record', 'discount_rate')
    op.drop_column('pricing_record', 'final_price')
    op.drop_column('pricing_record', 'base_cost')
    op.drop_column('pricing_record', 'loss_cost')
