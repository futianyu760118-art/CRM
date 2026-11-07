"""pand-330 M1 AEOS Object/Owner 列 + verification/sales_result + compat

Revision ID: pand330a1
Revises: aeos_lead_intake
Create Date: 2026-11-03 10:00:00.000000

架构 §5 revision_01（schema）：
- ``AeosObjectMixin`` 六列加到 10 张关键对象表（server_default 落默认值，存量无需回填即非空）；
- ``quote_library`` 升级为 ``BusinessModel``：补 ``owner_id``/``department_id``（record_owner 载体）；
- 新建 ``verification``（F5-A01）、``sales_result``（架构 §4.3）；
- ``integration_log.compat`` 兼容标记（F8-A04）。
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "pand330a1"
down_revision: str | None = "aeos_lead_intake"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: 关键对象表（架构 §4.1 适用对象）
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
        op.add_column(table, sa.Column("tenant_id", sa.String(length=50), nullable=False, server_default="default"))
        op.add_column(table, sa.Column("revision", sa.Integer(), nullable=False, server_default="1"))
        op.add_column(table, sa.Column("fact_owner", sa.String(length=30), nullable=False, server_default="M05"))
        op.add_column(table, sa.Column("processor", sa.UUID(), nullable=True))
        op.add_column(
            table,
            sa.Column(
                "consumer",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
        )
        op.add_column(table, sa.Column("verifier", sa.UUID(), nullable=True))

    # quote_library 由 BaseModel 升级为 BusinessModel：record_owner 复用 owner_id（架构 §4.1）
    op.add_column("quote_library", sa.Column("owner_id", sa.UUID(), nullable=True))
    op.add_column(
        "quote_library",
        sa.Column("department_id", sa.UUID(), sa.ForeignKey("department.id"), nullable=True),
    )
    op.create_index(op.f("ix_quote_library_owner_id"), "quote_library", ["owner_id"], unique=False)
    op.create_index(op.f("ix_quote_library_department_id"), "quote_library", ["department_id"], unique=False)

    op.create_table(
        "sales_result",
        sa.Column("result_id", sa.String(length=200), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("metric_code", sa.String(length=50), nullable=False),
        sa.Column("metric_value", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("metric_unit", sa.String(length=20), nullable=False),
        sa.Column("calculation_version", sa.String(length=50), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("order_count", sa.Integer(), nullable=False),
        sa.Column("object_ref_type", sa.String(length=50), nullable=False),
        sa.Column("object_ref_id", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "evidence_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("tenant_id", sa.String(length=50), nullable=False, server_default="default"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("fact_owner", sa.String(length=30), nullable=False, server_default="M05"),
        sa.Column("processor", sa.UUID(), nullable=True),
        sa.Column(
            "consumer",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("verifier", sa.UUID(), nullable=True),
        sa.Column("owner_id", sa.UUID(), nullable=True),
        sa.Column("department_id", sa.UUID(), sa.ForeignKey("department.id"), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_sales_result_result_id"), "sales_result", ["result_id"], unique=True)
    for col in ("metric_code", "object_ref_id", "status", "fact_owner", "owner_id", "department_id", "deleted_at"):
        op.create_index(op.f(f"ix_sales_result_{col}"), "sales_result", [col], unique=False)

    op.create_table(
        "verification",
        sa.Column("verification_id", sa.UUID(), nullable=False),
        sa.Column("subject_type", sa.String(length=30), nullable=False),
        sa.Column("subject_id", sa.String(length=100), nullable=False),
        sa.Column("subject_revision", sa.Integer(), nullable=False),
        sa.Column("object_ref_type", sa.String(length=50), nullable=False),
        sa.Column("object_ref_id", sa.String(length=100), nullable=False),
        sa.Column("verifier", sa.UUID(), nullable=True),
        sa.Column("verifier_role", sa.String(length=50), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "evidence_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("tenant_id", sa.String(length=50), nullable=False, server_default="default"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("verification_id", name="uq_verification_verification_id"),
        sa.UniqueConstraint("subject_type", "subject_id", "subject_revision", name="uq_verification_subject"),
    )
    for col in ("subject_type", "subject_id", "object_ref_id", "status", "deleted_at"):
        op.create_index(op.f(f"ix_verification_{col}"), "verification", [col], unique=False)

    op.add_column("integration_log", sa.Column("compat", sa.String(length=20), nullable=True))
    op.create_index(op.f("ix_integration_log_compat"), "integration_log", ["compat"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_integration_log_compat"), table_name="integration_log")
    op.drop_column("integration_log", "compat")

    for col in ("subject_type", "subject_id", "object_ref_id", "status", "deleted_at"):
        op.drop_index(op.f(f"ix_verification_{col}"), table_name="verification")
    op.drop_table("verification")

    sales_result_indexed = (
        "result_id",
        "metric_code",
        "object_ref_id",
        "status",
        "fact_owner",
        "owner_id",
        "department_id",
        "deleted_at",
    )
    for col in sales_result_indexed:
        op.drop_index(op.f(f"ix_sales_result_{col}"), table_name="sales_result")
    op.drop_table("sales_result")

    op.drop_index(op.f("ix_quote_library_department_id"), table_name="quote_library")
    op.drop_index(op.f("ix_quote_library_owner_id"), table_name="quote_library")
    op.drop_column("quote_library", "department_id")
    op.drop_column("quote_library", "owner_id")

    for table in reversed(_OBJECT_TABLES):
        op.drop_column(table, "verifier")
        op.drop_column(table, "consumer")
        op.drop_column(table, "processor")
        op.drop_column(table, "fact_owner")
        op.drop_column(table, "revision")
        op.drop_column(table, "tenant_id")
