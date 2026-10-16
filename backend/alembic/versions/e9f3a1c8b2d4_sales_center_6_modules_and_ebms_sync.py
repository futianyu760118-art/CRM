"""sales center 6 modules and ebms sync fields

Revision ID: e9f3a1c8b2d4
Revises: c7e1a2b4d9f0
Create Date: 2026-10-16 21:30:00.000000

PAND-249：订单 / 样品 / 报价库 / 问题反馈 4 新模块 + 同步冲突 / 询价状态日志，
并对 company / contact / inquiry / inquiry_item 追加 EBMS 双向同步与销售中心扩字段。
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e9f3a1c8b2d4"
down_revision: str | None = "c7e1a2b4d9f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------ 新增表
    op.create_table(
        "sales_order",
        sa.Column("order_no", sa.String(length=50), nullable=False),
        sa.Column("line_no", sa.String(length=50), nullable=False),
        sa.Column("external_id", sa.String(length=100), nullable=True),
        sa.Column("company_id", sa.UUID(), nullable=True),
        sa.Column("customer_name", sa.String(length=200), nullable=True),
        sa.Column("customer_code", sa.String(length=50), nullable=True),
        sa.Column("product_code", sa.String(length=50), nullable=True),
        sa.Column("product_name", sa.String(length=200), nullable=True),
        sa.Column("project_no", sa.String(length=50), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("completed_qty", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("order_amount", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("risk_level", sa.String(length=20), nullable=False),
        sa.Column("promised_date", sa.Date(), nullable=True),
        sa.Column("plan_date", sa.Date(), nullable=True),
        sa.Column("online_date", sa.Date(), nullable=True),
        sa.Column("user_status_locked", sa.Boolean(), nullable=False),
        sa.Column("user_status_modified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_status_modified_by", sa.UUID(), nullable=True),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("sync_status", sa.String(length=20), nullable=False),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("owner_id", sa.UUID(), nullable=True),
        sa.Column("department_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["company.id"], ),
        sa.ForeignKeyConstraint(["department_id"], ["department.id"], ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_no", "line_no", name="uq_sales_order_key"),
    )
    op.create_index(op.f("ix_sales_order_company_id"), "sales_order", ["company_id"], unique=False)
    op.create_index(op.f("ix_sales_order_customer_code"), "sales_order", ["customer_code"], unique=False)
    op.create_index(op.f("ix_sales_order_customer_name"), "sales_order", ["customer_name"], unique=False)
    op.create_index(op.f("ix_sales_order_deleted_at"), "sales_order", ["deleted_at"], unique=False)
    op.create_index(op.f("ix_sales_order_department_id"), "sales_order", ["department_id"], unique=False)
    op.create_index(op.f("ix_sales_order_external_id"), "sales_order", ["external_id"], unique=False)
    op.create_index(op.f("ix_sales_order_order_no"), "sales_order", ["order_no"], unique=False)
    op.create_index(op.f("ix_sales_order_owner_id"), "sales_order", ["owner_id"], unique=False)
    op.create_index(op.f("ix_sales_order_product_code"), "sales_order", ["product_code"], unique=False)
    op.create_index(op.f("ix_sales_order_product_name"), "sales_order", ["product_name"], unique=False)
    op.create_index(op.f("ix_sales_order_project_no"), "sales_order", ["project_no"], unique=False)
    op.create_index(op.f("ix_sales_order_risk_level"), "sales_order", ["risk_level"], unique=False)
    op.create_index(op.f("ix_sales_order_status"), "sales_order", ["status"], unique=False)
    op.create_index(op.f("ix_sales_order_sync_status"), "sales_order", ["sync_status"], unique=False)

    op.create_table(
        "sample",
        sa.Column("sample_no", sa.String(length=50), nullable=False),
        sa.Column("external_id", sa.String(length=100), nullable=True),
        sa.Column("company_id", sa.UUID(), nullable=True),
        sa.Column("customer_name", sa.String(length=200), nullable=False),
        sa.Column("inquiry_no", sa.String(length=50), nullable=True),
        sa.Column("inquiry_id", sa.UUID(), nullable=True),
        sa.Column("product_name", sa.String(length=200), nullable=True),
        sa.Column("product_code", sa.String(length=50), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("sample_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("send_date", sa.Date(), nullable=True),
        sa.Column("confirm_date", sa.Date(), nullable=True),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("sync_status", sa.String(length=20), nullable=False),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("owner_id", sa.UUID(), nullable=True),
        sa.Column("department_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["company.id"], ),
        sa.ForeignKeyConstraint(["department_id"], ["department.id"], ),
        sa.ForeignKeyConstraint(["inquiry_id"], ["inquiry.id"], ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_sample_company_id"), "sample", ["company_id"], unique=False)
    op.create_index(op.f("ix_sample_customer_name"), "sample", ["customer_name"], unique=False)
    op.create_index(op.f("ix_sample_deleted_at"), "sample", ["deleted_at"], unique=False)
    op.create_index(op.f("ix_sample_department_id"), "sample", ["department_id"], unique=False)
    op.create_index(op.f("ix_sample_external_id"), "sample", ["external_id"], unique=False)
    op.create_index(op.f("ix_sample_inquiry_no"), "sample", ["inquiry_no"], unique=False)
    op.create_index(op.f("ix_sample_owner_id"), "sample", ["owner_id"], unique=False)
    op.create_index(op.f("ix_sample_product_code"), "sample", ["product_code"], unique=False)
    op.create_index(op.f("ix_sample_product_name"), "sample", ["product_name"], unique=False)
    op.create_index(op.f("ix_sample_sample_no"), "sample", ["sample_no"], unique=True)
    op.create_index(op.f("ix_sample_status"), "sample", ["status"], unique=False)
    op.create_index(op.f("ix_sample_sync_status"), "sample", ["sync_status"], unique=False)

    op.create_table(
        "quote_library",
        sa.Column("external_model", sa.String(length=200), nullable=False),
        sa.Column("certificate_level", sa.String(length=50), nullable=False),
        sa.Column("external_id", sa.String(length=100), nullable=True),
        sa.Column("internal_model", sa.String(length=100), nullable=True),
        sa.Column("product_name", sa.String(length=200), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("power", sa.String(length=100), nullable=True),
        sa.Column("configuration", sa.Text(), nullable=True),
        sa.Column("specs", sa.Text(), nullable=True),
        sa.Column("price_rmb", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("price_usd", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("unit_price", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("min_price", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("validity_days", sa.Integer(), nullable=False),
        sa.Column("usage_count", sa.Integer(), nullable=False),
        sa.Column("source_inquiry_no", sa.String(length=50), nullable=True),
        sa.Column("source_inquiry_id", sa.UUID(), nullable=True),
        sa.Column("source_pricing_id", sa.String(length=100), nullable=True),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("creator", sa.String(length=100), nullable=True),
        sa.Column("sync_status", sa.String(length=20), nullable=False),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_model", "certificate_level", name="uq_quote_library_key"),
    )
    op.create_index(op.f("ix_quote_library_certificate_level"), "quote_library", ["certificate_level"], unique=False)
    op.create_index(op.f("ix_quote_library_deleted_at"), "quote_library", ["deleted_at"], unique=False)
    op.create_index(op.f("ix_quote_library_external_id"), "quote_library", ["external_id"], unique=False)
    op.create_index(op.f("ix_quote_library_external_model"), "quote_library", ["external_model"], unique=False)
    op.create_index(op.f("ix_quote_library_product_name"), "quote_library", ["product_name"], unique=False)
    op.create_index(op.f("ix_quote_library_source_inquiry_no"), "quote_library", ["source_inquiry_no"], unique=False)
    op.create_index(op.f("ix_quote_library_sync_status"), "quote_library", ["sync_status"], unique=False)

    op.create_table(
        "feedback",
        sa.Column("feedback_no", sa.String(length=50), nullable=False),
        sa.Column("external_id", sa.String(length=100), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("module", sa.String(length=100), nullable=True),
        sa.Column("submitter", sa.String(length=100), nullable=True),
        sa.Column("submitter_id", sa.UUID(), nullable=True),
        sa.Column("assignee", sa.String(length=100), nullable=True),
        sa.Column("assignee_id", sa.UUID(), nullable=True),
        sa.Column("screenshots", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_status", sa.String(length=20), nullable=False),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("owner_id", sa.UUID(), nullable=True),
        sa.Column("department_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["department_id"], ["department.id"], ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_feedback_assignee"), "feedback", ["assignee"], unique=False)
    op.create_index(op.f("ix_feedback_assignee_id"), "feedback", ["assignee_id"], unique=False)
    op.create_index(op.f("ix_feedback_deleted_at"), "feedback", ["deleted_at"], unique=False)
    op.create_index(op.f("ix_feedback_department_id"), "feedback", ["department_id"], unique=False)
    op.create_index(op.f("ix_feedback_external_id"), "feedback", ["external_id"], unique=False)
    op.create_index(op.f("ix_feedback_feedback_no"), "feedback", ["feedback_no"], unique=True)
    op.create_index(op.f("ix_feedback_owner_id"), "feedback", ["owner_id"], unique=False)
    op.create_index(op.f("ix_feedback_priority"), "feedback", ["priority"], unique=False)
    op.create_index(op.f("ix_feedback_status"), "feedback", ["status"], unique=False)
    op.create_index(op.f("ix_feedback_submitter"), "feedback", ["submitter"], unique=False)
    op.create_index(op.f("ix_feedback_sync_status"), "feedback", ["sync_status"], unique=False)
    op.create_index(op.f("ix_feedback_title"), "feedback", ["title"], unique=False)
    op.create_index(op.f("ix_feedback_type"), "feedback", ["type"], unique=False)

    op.create_table(
        "feedback_followup",
        sa.Column("feedback_id", sa.UUID(), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("status_from", sa.String(length=20), nullable=True),
        sa.Column("status_to", sa.String(length=20), nullable=True),
        sa.Column("assignee", sa.String(length=100), nullable=True),
        sa.Column("operator", sa.String(length=100), nullable=True),
        sa.Column("operator_id", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["feedback_id"], ["feedback.id"], ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_feedback_followup_deleted_at"), "feedback_followup", ["deleted_at"], unique=False)
    op.create_index(op.f("ix_feedback_followup_feedback_id"), "feedback_followup", ["feedback_id"], unique=False)

    op.create_table(
        "sync_conflict",
        sa.Column("object_type", sa.String(length=30), nullable=False),
        sa.Column("object_id", sa.String(length=100), nullable=True),
        sa.Column("field", sa.String(length=100), nullable=True),
        sa.Column("source_system", sa.String(length=30), nullable=True),
        sa.Column("incoming_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("local_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("resolution", sa.String(length=20), nullable=False),
        sa.Column("event_id", sa.String(length=100), nullable=True),
        sa.Column("idempotency_key", sa.String(length=200), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_sync_conflict_deleted_at"), "sync_conflict", ["deleted_at"], unique=False)
    op.create_index(op.f("ix_sync_conflict_event_id"), "sync_conflict", ["event_id"], unique=False)
    op.create_index(op.f("ix_sync_conflict_idempotency_key"), "sync_conflict", ["idempotency_key"], unique=False)
    op.create_index(op.f("ix_sync_conflict_object_id"), "sync_conflict", ["object_id"], unique=False)
    op.create_index(op.f("ix_sync_conflict_object_type"), "sync_conflict", ["object_type"], unique=False)
    op.create_index(op.f("ix_sync_conflict_resolution"), "sync_conflict", ["resolution"], unique=False)
    op.create_index(op.f("ix_sync_conflict_source_system"), "sync_conflict", ["source_system"], unique=False)

    op.create_table(
        "inquiry_status_log",
        sa.Column("inquiry_id", sa.UUID(), nullable=False),
        sa.Column("from_status", sa.String(length=30), nullable=True),
        sa.Column("to_status", sa.String(length=30), nullable=False),
        sa.Column("operator_id", sa.UUID(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["inquiry_id"], ["inquiry.id"], ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_inquiry_status_log_deleted_at"), "inquiry_status_log", ["deleted_at"], unique=False)
    op.create_index(op.f("ix_inquiry_status_log_inquiry_id"), "inquiry_status_log", ["inquiry_id"], unique=False)

    # ------------------------------------------------------------------ 客户扩字段
    op.add_column("company", sa.Column("former_name", sa.String(length=200), nullable=True))
    op.add_column("company", sa.Column("parent_code", sa.String(length=50), nullable=True))
    op.add_column("company", sa.Column("sales_mode", sa.String(length=30), nullable=True))
    op.add_column("company", sa.Column("customer_status", sa.String(length=30), nullable=True))
    op.add_column("company", sa.Column("decision_maker", sa.String(length=100), nullable=True))
    op.add_column("company", sa.Column("decision_maker_position", sa.String(length=100), nullable=True))
    op.add_column("company", sa.Column("decision_core_need", sa.Text(), nullable=True))
    op.add_column("company", sa.Column("last_trade_year", sa.String(length=10), nullable=True))
    op.add_column("company", sa.Column("invoice_title", sa.String(length=200), nullable=True))
    op.add_column("company", sa.Column("tax_id", sa.String(length=50), nullable=True))
    op.add_column("company", sa.Column("bank_name", sa.String(length=200), nullable=True))
    op.add_column("company", sa.Column("bank_account", sa.String(length=100), nullable=True))
    op.add_column("company", sa.Column("country_region", sa.String(length=100), nullable=True))
    op.add_column("company", sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True))
    op.alter_column(
        "company",
        "customer_level",
        existing_type=sa.String(length=20),
        type_=sa.String(length=30),
        existing_nullable=True,
    )
    op.create_index(op.f("ix_company_customer_status"), "company", ["customer_status"], unique=False)

    # ------------------------------------------------------------------ 联系人扩字段
    op.add_column("contact", sa.Column("whatsapp", sa.String(length=100), nullable=True))
    op.add_column("contact", sa.Column("skype", sa.String(length=100), nullable=True))
    op.add_column("contact", sa.Column("other_im", sa.String(length=200), nullable=True))
    op.add_column(
        "contact",
        sa.Column("kind", sa.String(length=20), nullable=True, comment="decision 决策人 / contact 对接人"),
    )

    # ------------------------------------------------------------------ 询价同步/扩字段
    op.add_column("inquiry", sa.Column("external_id", sa.String(length=100), nullable=True))
    op.add_column("inquiry", sa.Column("sync_status", sa.String(length=20), nullable=True))
    op.add_column("inquiry", sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("inquiry", sa.Column("quote_validity", sa.String(length=50), nullable=True))
    op.create_index(op.f("ix_inquiry_external_id"), "inquiry", ["external_id"], unique=False)

    # ------------------------------------------------------------------ 询价明细扩字段
    op.add_column("inquiry_item", sa.Column("internal_model", sa.String(length=100), nullable=True))
    op.add_column(
        "inquiry_item",
        sa.Column("certificate_compliant", sa.String(length=10), nullable=True, comment="是/否"),
    )
    op.add_column(
        "inquiry_item",
        sa.Column("certificate_level", sa.String(length=50), nullable=True, comment="国标/行标/企标/无证书"),
    )


def downgrade() -> None:
    op.drop_column("inquiry_item", "certificate_level")
    op.drop_column("inquiry_item", "certificate_compliant")
    op.drop_column("inquiry_item", "internal_model")

    op.drop_index(op.f("ix_inquiry_external_id"), table_name="inquiry")
    op.drop_column("inquiry", "quote_validity")
    op.drop_column("inquiry", "last_sync_at")
    op.drop_column("inquiry", "sync_status")
    op.drop_column("inquiry", "external_id")

    op.drop_column("contact", "kind")
    op.drop_column("contact", "other_im")
    op.drop_column("contact", "skype")
    op.drop_column("contact", "whatsapp")

    op.drop_index(op.f("ix_company_customer_status"), table_name="company")
    op.alter_column(
        "company",
        "customer_level",
        existing_type=sa.String(length=30),
        type_=sa.String(length=20),
        existing_nullable=True,
    )
    op.drop_column("company", "last_sync_at")
    op.drop_column("company", "country_region")
    op.drop_column("company", "bank_account")
    op.drop_column("company", "bank_name")
    op.drop_column("company", "tax_id")
    op.drop_column("company", "invoice_title")
    op.drop_column("company", "last_trade_year")
    op.drop_column("company", "decision_core_need")
    op.drop_column("company", "decision_maker_position")
    op.drop_column("company", "decision_maker")
    op.drop_column("company", "customer_status")
    op.drop_column("company", "sales_mode")
    op.drop_column("company", "parent_code")
    op.drop_column("company", "former_name")

    op.drop_index(op.f("ix_inquiry_status_log_inquiry_id"), table_name="inquiry_status_log")
    op.drop_index(op.f("ix_inquiry_status_log_deleted_at"), table_name="inquiry_status_log")
    op.drop_table("inquiry_status_log")
    op.drop_index(op.f("ix_sync_conflict_source_system"), table_name="sync_conflict")
    op.drop_index(op.f("ix_sync_conflict_resolution"), table_name="sync_conflict")
    op.drop_index(op.f("ix_sync_conflict_object_type"), table_name="sync_conflict")
    op.drop_index(op.f("ix_sync_conflict_object_id"), table_name="sync_conflict")
    op.drop_index(op.f("ix_sync_conflict_idempotency_key"), table_name="sync_conflict")
    op.drop_index(op.f("ix_sync_conflict_event_id"), table_name="sync_conflict")
    op.drop_index(op.f("ix_sync_conflict_deleted_at"), table_name="sync_conflict")
    op.drop_table("sync_conflict")
    op.drop_index(op.f("ix_feedback_followup_feedback_id"), table_name="feedback_followup")
    op.drop_index(op.f("ix_feedback_followup_deleted_at"), table_name="feedback_followup")
    op.drop_table("feedback_followup")
    op.drop_index(op.f("ix_feedback_type"), table_name="feedback")
    op.drop_index(op.f("ix_feedback_title"), table_name="feedback")
    op.drop_index(op.f("ix_feedback_sync_status"), table_name="feedback")
    op.drop_index(op.f("ix_feedback_submitter"), table_name="feedback")
    op.drop_index(op.f("ix_feedback_status"), table_name="feedback")
    op.drop_index(op.f("ix_feedback_priority"), table_name="feedback")
    op.drop_index(op.f("ix_feedback_owner_id"), table_name="feedback")
    op.drop_index(op.f("ix_feedback_feedback_no"), table_name="feedback")
    op.drop_index(op.f("ix_feedback_external_id"), table_name="feedback")
    op.drop_index(op.f("ix_feedback_department_id"), table_name="feedback")
    op.drop_index(op.f("ix_feedback_deleted_at"), table_name="feedback")
    op.drop_index(op.f("ix_feedback_assignee_id"), table_name="feedback")
    op.drop_index(op.f("ix_feedback_assignee"), table_name="feedback")
    op.drop_table("feedback")
    op.drop_index(op.f("ix_quote_library_sync_status"), table_name="quote_library")
    op.drop_index(op.f("ix_quote_library_source_inquiry_no"), table_name="quote_library")
    op.drop_index(op.f("ix_quote_library_product_name"), table_name="quote_library")
    op.drop_index(op.f("ix_quote_library_external_model"), table_name="quote_library")
    op.drop_index(op.f("ix_quote_library_external_id"), table_name="quote_library")
    op.drop_index(op.f("ix_quote_library_deleted_at"), table_name="quote_library")
    op.drop_index(op.f("ix_quote_library_certificate_level"), table_name="quote_library")
    op.drop_table("quote_library")
    op.drop_index(op.f("ix_sample_sync_status"), table_name="sample")
    op.drop_index(op.f("ix_sample_status"), table_name="sample")
    op.drop_index(op.f("ix_sample_sample_no"), table_name="sample")
    op.drop_index(op.f("ix_sample_product_name"), table_name="sample")
    op.drop_index(op.f("ix_sample_product_code"), table_name="sample")
    op.drop_index(op.f("ix_sample_owner_id"), table_name="sample")
    op.drop_index(op.f("ix_sample_inquiry_no"), table_name="sample")
    op.drop_index(op.f("ix_sample_external_id"), table_name="sample")
    op.drop_index(op.f("ix_sample_department_id"), table_name="sample")
    op.drop_index(op.f("ix_sample_deleted_at"), table_name="sample")
    op.drop_index(op.f("ix_sample_customer_name"), table_name="sample")
    op.drop_index(op.f("ix_sample_company_id"), table_name="sample")
    op.drop_table("sample")
    op.drop_index(op.f("ix_sales_order_sync_status"), table_name="sales_order")
    op.drop_index(op.f("ix_sales_order_status"), table_name="sales_order")
    op.drop_index(op.f("ix_sales_order_risk_level"), table_name="sales_order")
    op.drop_index(op.f("ix_sales_order_project_no"), table_name="sales_order")
    op.drop_index(op.f("ix_sales_order_product_name"), table_name="sales_order")
    op.drop_index(op.f("ix_sales_order_product_code"), table_name="sales_order")
    op.drop_index(op.f("ix_sales_order_owner_id"), table_name="sales_order")
    op.drop_index(op.f("ix_sales_order_order_no"), table_name="sales_order")
    op.drop_index(op.f("ix_sales_order_external_id"), table_name="sales_order")
    op.drop_index(op.f("ix_sales_order_department_id"), table_name="sales_order")
    op.drop_index(op.f("ix_sales_order_deleted_at"), table_name="sales_order")
    op.drop_index(op.f("ix_sales_order_customer_name"), table_name="sales_order")
    op.drop_index(op.f("ix_sales_order_customer_code"), table_name="sales_order")
    op.drop_index(op.f("ix_sales_order_company_id"), table_name="sales_order")
    op.drop_table("sales_order")
