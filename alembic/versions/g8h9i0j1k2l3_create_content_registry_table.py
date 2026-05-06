"""create_content_registry_table

Revision ID: g8h9i0j1k2l3
Revises: c3d4e5f6a7b8
Create Date: 2026-03-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "g8h9i0j1k2l3"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "content_registry",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content_id", sa.String(150), nullable=False),
        sa.Column("content_type", sa.String(50), nullable=False),
        sa.Column("schema_version", sa.String(50), nullable=False),
        sa.Column("content_version_major", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("content_version_minor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content_version_patch", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locale", sa.String(20), nullable=False, server_default="en"),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("subtitle", sa.String(500), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("estimated_duration_min", sa.Integer(), nullable=True),
        sa.Column("difficulty", sa.String(50), nullable=True),
        sa.Column("impact_level", sa.String(50), nullable=True),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("alignment", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("json_blob", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source_type", sa.String(50), nullable=True),
        sa.Column("source_ref", sa.String(255), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_content_registry_id"), "content_registry", ["id"], unique=False)
    op.create_index(op.f("ix_content_registry_content_id"), "content_registry", ["content_id"], unique=True)
    op.create_index(op.f("ix_content_registry_content_type"), "content_registry", ["content_type"], unique=False)
    op.create_index(op.f("ix_content_registry_status"), "content_registry", ["status"], unique=False)
    op.create_index(op.f("ix_content_registry_locale"), "content_registry", ["locale"], unique=False)
    op.create_index(op.f("ix_content_registry_category"), "content_registry", ["category"], unique=False)
    op.create_index(op.f("ix_content_registry_difficulty"), "content_registry", ["difficulty"], unique=False)
    op.create_index(
        "idx_content_registry_type_status_locale",
        "content_registry",
        ["content_type", "status", "locale"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_content_registry_type_status_locale", table_name="content_registry")
    op.drop_index(op.f("ix_content_registry_difficulty"), table_name="content_registry")
    op.drop_index(op.f("ix_content_registry_category"), table_name="content_registry")
    op.drop_index(op.f("ix_content_registry_locale"), table_name="content_registry")
    op.drop_index(op.f("ix_content_registry_status"), table_name="content_registry")
    op.drop_index(op.f("ix_content_registry_content_type"), table_name="content_registry")
    op.drop_index(op.f("ix_content_registry_content_id"), table_name="content_registry")
    op.drop_index(op.f("ix_content_registry_id"), table_name="content_registry")
    op.drop_table("content_registry")
