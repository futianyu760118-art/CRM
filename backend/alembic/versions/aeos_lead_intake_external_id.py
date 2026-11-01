"""Add a CRM external identity for idempotent AEOS LeadIntakeV1 consumption."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "aeos_lead_intake"
down_revision: str | None = "b8f2c4d6e8a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("lead", sa.Column("external_id", sa.String(length=160), nullable=True))
    op.create_index(
        "uq_lead_external_id",
        "lead",
        ["external_id"],
        unique=True,
        postgresql_where=sa.text("external_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_lead_external_id", table_name="lead")
    op.drop_column("lead", "external_id")
