"""PAND-316 产品资料 / 商机流转 / 样品管理：新表 + 样品扩字段 + 5 态迁移

Revision ID: d4e5f6a7b8c9
Revises: c1d2e3f4a5b6
Create Date: 2026-10-31 18:00:00.000000

- 新建 ``product_document``（销售资料/规格书/测试报告/认证文件 + 版本号 + 当前有效）。
- 新建 ``standard_quote``（币种/数量区间/单价/有效期/版本号，区间不重叠由服务层保证）。
- ``sample`` 新增 8 列（产品型号/样品要求/计划完成日期/快递公司/快递单号/客户反馈/反馈日期/关联商机）。
- ``sample.status`` 6 态 -> 5 态数据迁移：confirmed→producing、customer_confirmed/completed→feedback（pending 保持）。
- 快递单号未删除内唯一（部分唯一索引）。
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c1d2e3f4a5b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "product_document",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("product_id", sa.UUID(), sa.ForeignKey("product.id"), nullable=False),
        sa.Column("doc_type", sa.String(length=30), nullable=False),
        sa.Column("version_no", sa.String(length=20), nullable=False),
        sa.Column("file_id", sa.UUID(), sa.ForeignKey("file.id"), nullable=False),
        sa.Column("filename", sa.String(length=300), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("owner_id", sa.UUID(), nullable=True),
        sa.Column("department_id", sa.UUID(), sa.ForeignKey("department.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("product_id", "doc_type", "version_no", name="uq_product_document_version"),
    )
    op.create_index("ix_product_document_product_id", "product_document", ["product_id"])
    op.create_index("ix_product_document_doc_type", "product_document", ["doc_type"])
    op.create_index("ix_product_document_file_id", "product_document", ["file_id"])
    op.create_index("ix_product_document_deleted_at", "product_document", ["deleted_at"])

    op.create_table(
        "standard_quote",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("product_id", sa.UUID(), sa.ForeignKey("product.id"), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="USD"),
        sa.Column("qty_from", sa.Integer(), nullable=False),
        sa.Column("qty_to", sa.Integer(), nullable=True),
        sa.Column("unit_price", sa.Numeric(18, 4), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=False),
        sa.Column("version_no", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE"),
        sa.Column("owner_id", sa.UUID(), nullable=True),
        sa.Column("department_id", sa.UUID(), sa.ForeignKey("department.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("product_id", "currency", "version_no", name="uq_standard_quote_version"),
    )
    op.create_index("ix_standard_quote_product_id", "standard_quote", ["product_id"])
    op.create_index("ix_standard_quote_status", "standard_quote", ["status"])
    op.create_index("ix_standard_quote_deleted_at", "standard_quote", ["deleted_at"])

    op.add_column("sample", sa.Column("product_model", sa.String(length=100), nullable=True, comment="产品型号"))
    op.add_column("sample", sa.Column("sample_requirement", sa.Text(), nullable=True, comment="样品要求 ≤2000"))
    op.add_column("sample", sa.Column("plan_date", sa.Date(), nullable=True, comment="计划完成日期"))
    op.add_column("sample", sa.Column("courier", sa.String(length=30), nullable=True, comment="快递公司编码"))
    op.add_column("sample", sa.Column("tracking_no", sa.String(length=40), nullable=True, comment="快递单号"))
    op.add_column("sample", sa.Column("feedback", sa.Text(), nullable=True, comment="客户反馈 ≤2000"))
    op.add_column("sample", sa.Column("feedback_date", sa.Date(), nullable=True, comment="反馈日期"))
    op.add_column("sample", sa.Column("opportunity_id", sa.UUID(), nullable=True, comment="关联商机"))
    op.create_index("ix_sample_opportunity_id", "sample", ["opportunity_id"])
    op.create_index(
        "uq_sample_tracking_no",
        "sample",
        ["tracking_no"],
        unique=True,
        postgresql_where=sa.text("tracking_no IS NOT NULL AND deleted_at IS NULL"),
    )

    op.execute(
        """
        UPDATE sample
        SET status = CASE status
            WHEN 'confirmed' THEN 'producing'
            WHEN 'customer_confirmed' THEN 'feedback'
            WHEN 'completed' THEN 'feedback'
            ELSE status
        END
        WHERE status IN ('confirmed', 'customer_confirmed', 'completed')
        """
    )


def downgrade() -> None:
    # 5 态 -> 6 态（有损：testing 回退为 confirmed；feedback 回退为 customer_confirmed）
    op.execute(
        """
        UPDATE sample
        SET status = CASE status
            WHEN 'testing' THEN 'confirmed'
            WHEN 'feedback' THEN 'customer_confirmed'
            ELSE status
        END
        WHERE status IN ('testing', 'feedback')
        """
    )
    op.drop_index("uq_sample_tracking_no", table_name="sample")
    op.drop_index("ix_sample_opportunity_id", table_name="sample")
    for column in (
        "opportunity_id",
        "feedback_date",
        "feedback",
        "tracking_no",
        "courier",
        "plan_date",
        "sample_requirement",
        "product_model",
    ):
        op.drop_column("sample", column)

    op.drop_index("ix_standard_quote_deleted_at", table_name="standard_quote")
    op.drop_index("ix_standard_quote_status", table_name="standard_quote")
    op.drop_index("ix_standard_quote_product_id", table_name="standard_quote")
    op.drop_table("standard_quote")

    op.drop_index("ix_product_document_deleted_at", table_name="product_document")
    op.drop_index("ix_product_document_file_id", table_name="product_document")
    op.drop_index("ix_product_document_doc_type", table_name="product_document")
    op.drop_index("ix_product_document_product_id", table_name="product_document")
    op.drop_table("product_document")
