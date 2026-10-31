"""PAND-312 客户域：线索/客户扩字段 + 联系人关联表

Revision ID: c1d2e3f4a5b6
Revises: b8f2c4d6e8a1
Create Date: 2026-10-31 12:00:00.000000

- ``lead`` 新增具体需求内容/线索等级/初步背景调查/客户渠道分类（可空，存量不回填）。
- ``company`` 新增客户类型/公司背景/主营产品/品牌/销售渠道及市场/付款方式（可空）。
- 新建 ``contact_company_link``（一人多客户 + 关系类型 + 每客户唯一主要联系人）。
- 存量 ``contact.company_id`` 逐条回填关联，``contact.kind='decision'`` 映射为决策人。
- 分组派生字段所需索引。
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: str | None = "b8f2c4d6e8a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("lead", sa.Column("requirement_text", sa.Text(), nullable=True, comment="具体需求内容 ≤5000"))
    op.add_column("lead", sa.Column("lead_level", sa.String(length=10), nullable=True, comment="A/B/C"))
    op.add_column("lead", sa.Column("background", sa.Text(), nullable=True, comment="初步背景调查 ≤5000"))
    op.add_column("lead", sa.Column("channel", sa.String(length=30), nullable=True, comment="客户渠道分类编码"))

    op.add_column("company", sa.Column("customer_type", sa.String(length=30), nullable=True, comment="客户类型编码"))
    op.add_column("company", sa.Column("company_background", sa.Text(), nullable=True, comment="公司背景 ≤5000"))
    op.add_column("company", sa.Column("main_products", sa.String(length=500), nullable=True, comment="主营产品"))
    op.add_column("company", sa.Column("brand", sa.String(length=300), nullable=True, comment="品牌"))
    op.add_column(
        "company",
        sa.Column("sales_channel_market", sa.String(length=1000), nullable=True, comment="销售渠道及市场"),
    )
    op.add_column("company", sa.Column("payment_method", sa.String(length=20), nullable=True, comment="付款方式编码"))

    op.create_table(
        "contact_company_link",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("contact_id", sa.UUID(), sa.ForeignKey("contact.id"), nullable=False),
        sa.Column("company_id", sa.UUID(), sa.ForeignKey("company.id"), nullable=False),
        sa.Column("relation_type", sa.String(length=30), nullable=False, server_default="OTHER"),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("owner_id", sa.UUID(), nullable=True),
        sa.Column("department_id", sa.UUID(), sa.ForeignKey("department.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("contact_id", "company_id", name="uq_contact_company_link"),
    )
    op.create_index("ix_contact_company_link_contact_id", "contact_company_link", ["contact_id"])
    op.create_index("ix_contact_company_link_company_id", "contact_company_link", ["company_id"])
    op.create_index("ix_contact_company_link_deleted_at", "contact_company_link", ["deleted_at"])

    op.execute(
        """
        INSERT INTO contact_company_link
            (id, contact_id, company_id, relation_type, is_primary, owner_id, department_id, created_at, updated_at)
        SELECT gen_random_uuid(), c.id, c.company_id,
               CASE WHEN c.kind = 'decision' THEN 'DECISION_MAKER' ELSE 'OTHER' END,
               COALESCE(c.is_primary, false), c.owner_id, c.department_id, now(), now()
        FROM contact c
        WHERE c.company_id IS NOT NULL AND c.deleted_at IS NULL
        ON CONFLICT (contact_id, company_id) DO NOTHING
        """
    )
    # 存量可能同客户多个主要联系人：仅保留最早一条，避免部分唯一索引创建失败
    op.execute(
        """
        WITH ranked AS (
            SELECT id, row_number() OVER (PARTITION BY company_id ORDER BY created_at, id) AS rn
            FROM contact_company_link
            WHERE is_primary AND deleted_at IS NULL
        )
        UPDATE contact_company_link l
        SET is_primary = false
        FROM ranked r
        WHERE l.id = r.id AND r.rn > 1
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_link_primary ON contact_company_link (company_id) "
        "WHERE is_primary AND deleted_at IS NULL"
    )

    op.create_index("ix_company_created_at", "company", ["created_at"])
    op.create_index("ix_activity_company_id_happened_at", "activity", ["company_id", "happened_at"])
    op.create_index("ix_sales_order_company_id_status", "sales_order", ["company_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_sales_order_company_id_status", table_name="sales_order")
    op.drop_index("ix_activity_company_id_happened_at", table_name="activity")
    op.drop_index("ix_company_created_at", table_name="company")
    op.drop_index("uq_link_primary", table_name="contact_company_link")
    op.drop_table("contact_company_link")
    for column in (
        "customer_type",
        "company_background",
        "main_products",
        "brand",
        "sales_channel_market",
        "payment_method",
    ):
        op.drop_column("company", column)
    for column in ("requirement_text", "lead_level", "background", "channel"):
        op.drop_column("lead", column)
