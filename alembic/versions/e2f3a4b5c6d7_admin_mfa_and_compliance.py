"""Add MFA columns to users and compliance export requests table."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, None] = "f9a0b1c2d3e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("mfa_secret_encrypted", sa.String(500), nullable=True))
    op.add_column("users", sa.Column("mfa_enabled_at", sa.DateTime(timezone=True), nullable=True))

    compliance_status = postgresql.ENUM(
        "pending", "in_progress", "completed", "rejected",
        name="complianceexportstatus",
        create_type=False,
    )
    bind = op.get_bind()
    # Create enum only if missing; then reuse without auto-create on table DDL
    existing = bind.execute(sa.text(
        "SELECT 1 FROM pg_type WHERE typname = 'complianceexportstatus'"
    )).scalar()
    if not existing:
        postgresql.ENUM(
            "pending", "in_progress", "completed", "rejected",
            name="complianceexportstatus",
        ).create(bind, checkfirst=False)

    op.create_table(
        "compliance_export_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("requester_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("subject_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True),
        sa.Column("request_type", sa.String(50), nullable=False, server_default="data_export"),
        sa.Column("status", compliance_status, nullable=False, server_default="pending"),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("request_metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_compliance_export_requests_id", "compliance_export_requests", ["id"])
    op.create_index("ix_compliance_export_requests_status", "compliance_export_requests", ["status"])
    op.create_index("idx_compliance_export_status_created", "compliance_export_requests", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_compliance_export_status_created", table_name="compliance_export_requests")
    op.drop_index("ix_compliance_export_requests_status", table_name="compliance_export_requests")
    op.drop_index("ix_compliance_export_requests_id", table_name="compliance_export_requests")
    op.drop_table("compliance_export_requests")
    op.execute("DROP TYPE IF EXISTS complianceexportstatus")
    op.drop_column("users", "mfa_enabled_at")
    op.drop_column("users", "mfa_secret_encrypted")
