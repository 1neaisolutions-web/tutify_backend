"""create_recommendation_performance_snapshots_table

Revision ID: l2m3n4o5p6q7
Revises: k1l2m3n4o5p6
Create Date: 2026-03-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "l2m3n4o5p6q7"
down_revision: Union[str, None] = "k1l2m3n4o5p6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "recommendation_performance_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content_id", sa.String(150), nullable=False),
        sa.Column("content_type", sa.String(50), nullable=True),
        sa.Column("recommendation_source", sa.String(100), nullable=True),
        sa.Column("impressions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("clicks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("starts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("dismissals", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ctr", sa.Float(), nullable=True),
        sa.Column("start_rate", sa.Float(), nullable=True),
        sa.Column("completion_rate", sa.Float(), nullable=True),
        sa.Column("dismissal_rate", sa.Float(), nullable=True),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_recommendation_performance_snapshots_id"),
        "recommendation_performance_snapshots",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_recommendation_performance_snapshots_content_id"),
        "recommendation_performance_snapshots",
        ["content_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_recommendation_performance_snapshots_recommendation_source"),
        "recommendation_performance_snapshots",
        ["recommendation_source"],
        unique=False,
    )
    op.create_index(
        op.f("ix_recommendation_performance_snapshots_snapshot_date"),
        "recommendation_performance_snapshots",
        ["snapshot_date"],
        unique=False,
    )
    op.create_index(
        "idx_recommendation_perf_content_source_date",
        "recommendation_performance_snapshots",
        ["content_id", "recommendation_source", "snapshot_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_recommendation_perf_content_source_date",
        table_name="recommendation_performance_snapshots",
    )
    op.drop_index(
        op.f("ix_recommendation_performance_snapshots_snapshot_date"),
        table_name="recommendation_performance_snapshots",
    )
    op.drop_index(
        op.f("ix_recommendation_performance_snapshots_recommendation_source"),
        table_name="recommendation_performance_snapshots",
    )
    op.drop_index(
        op.f("ix_recommendation_performance_snapshots_content_id"),
        table_name="recommendation_performance_snapshots",
    )
    op.drop_index(
        op.f("ix_recommendation_performance_snapshots_id"),
        table_name="recommendation_performance_snapshots",
    )
    op.drop_table("recommendation_performance_snapshots")

