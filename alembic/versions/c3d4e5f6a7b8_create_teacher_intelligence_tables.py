"""create_teacher_intelligence_tables

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-03-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # teacher_feature_snapshots
    op.create_table(
        "teacher_feature_snapshots",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("teacher_id", sa.UUID(), nullable=False),
        sa.Column("feature_schema_version", sa.String(50), nullable=False),
        sa.Column("source_hash", sa.String(128), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("features", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_latest", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["teacher_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        op.f("ix_teacher_feature_snapshots_id"),
        "teacher_feature_snapshots",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_teacher_feature_snapshots_teacher_id"),
        "teacher_feature_snapshots",
        ["teacher_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_teacher_feature_snapshots_feature_schema_version"),
        "teacher_feature_snapshots",
        ["feature_schema_version"],
        unique=False,
    )
    op.create_index(
        op.f("ix_teacher_feature_snapshots_is_latest"),
        "teacher_feature_snapshots",
        ["is_latest"],
        unique=False,
    )
    op.create_index(
        "idx_teacher_feature_snapshot_teacher_latest",
        "teacher_feature_snapshots",
        ["teacher_id", "is_latest"],
        unique=False,
    )

    # ml_outputs
    op.create_table(
        "ml_outputs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("teacher_id", sa.UUID(), nullable=False),
        sa.Column("pipeline_name", sa.String(100), nullable=False),
        sa.Column("pipeline_version", sa.String(50), nullable=False),
        sa.Column("model_version", sa.String(50), nullable=False),
        sa.Column("feature_snapshot_id", sa.UUID(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("results", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("is_latest", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["teacher_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["feature_snapshot_id"],
            ["teacher_feature_snapshots.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(op.f("ix_ml_outputs_id"), "ml_outputs", ["id"], unique=False)
    op.create_index(op.f("ix_ml_outputs_teacher_id"), "ml_outputs", ["teacher_id"], unique=False)
    op.create_index(
        op.f("ix_ml_outputs_feature_snapshot_id"),
        "ml_outputs",
        ["feature_snapshot_id"],
        unique=False,
    )
    op.create_index(op.f("ix_ml_outputs_pipeline_name"), "ml_outputs", ["pipeline_name"], unique=False)
    op.create_index(op.f("ix_ml_outputs_is_latest"), "ml_outputs", ["is_latest"], unique=False)
    op.create_index(
        "idx_ml_outputs_teacher_latest",
        "ml_outputs",
        ["teacher_id", "is_latest"],
        unique=False,
    )
    op.create_index(
        "idx_ml_outputs_teacher_pipeline",
        "ml_outputs",
        ["teacher_id", "pipeline_name"],
        unique=False,
    )

    # pipeline_runs
    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("teacher_id", sa.UUID(), nullable=False),
        sa.Column("pipeline_name", sa.String(100), nullable=False),
        sa.Column("pipeline_version", sa.String(50), nullable=False),
        sa.Column("model_version", sa.String(50), nullable=False),
        sa.Column("feature_snapshot_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("runtime_ms", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["teacher_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["feature_snapshot_id"],
            ["teacher_feature_snapshots.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(op.f("ix_pipeline_runs_id"), "pipeline_runs", ["id"], unique=False)
    op.create_index(
        op.f("ix_pipeline_runs_teacher_id"),
        "pipeline_runs",
        ["teacher_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pipeline_runs_feature_snapshot_id"),
        "pipeline_runs",
        ["feature_snapshot_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pipeline_runs_pipeline_name"),
        "pipeline_runs",
        ["pipeline_name"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pipeline_runs_status"),
        "pipeline_runs",
        ["status"],
        unique=False,
    )
    op.create_index(
        "idx_pipeline_runs_teacher_status",
        "pipeline_runs",
        ["teacher_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_pipeline_runs_teacher_status", table_name="pipeline_runs")
    op.drop_index(op.f("ix_pipeline_runs_status"), table_name="pipeline_runs")
    op.drop_index(op.f("ix_pipeline_runs_pipeline_name"), table_name="pipeline_runs")
    op.drop_index(op.f("ix_pipeline_runs_feature_snapshot_id"), table_name="pipeline_runs")
    op.drop_index(op.f("ix_pipeline_runs_teacher_id"), table_name="pipeline_runs")
    op.drop_index(op.f("ix_pipeline_runs_id"), table_name="pipeline_runs")
    op.drop_table("pipeline_runs")

    op.drop_index("idx_ml_outputs_teacher_pipeline", table_name="ml_outputs")
    op.drop_index("idx_ml_outputs_teacher_latest", table_name="ml_outputs")
    op.drop_index(op.f("ix_ml_outputs_is_latest"), table_name="ml_outputs")
    op.drop_index(op.f("ix_ml_outputs_pipeline_name"), table_name="ml_outputs")
    op.drop_index(op.f("ix_ml_outputs_feature_snapshot_id"), table_name="ml_outputs")
    op.drop_index(op.f("ix_ml_outputs_teacher_id"), table_name="ml_outputs")
    op.drop_index(op.f("ix_ml_outputs_id"), table_name="ml_outputs")
    op.drop_table("ml_outputs")

    op.drop_index(
        "idx_teacher_feature_snapshot_teacher_latest",
        table_name="teacher_feature_snapshots",
    )
    op.drop_index(
        op.f("ix_teacher_feature_snapshots_is_latest"),
        table_name="teacher_feature_snapshots",
    )
    op.drop_index(
        op.f("ix_teacher_feature_snapshots_feature_schema_version"),
        table_name="teacher_feature_snapshots",
    )
    op.drop_index(
        op.f("ix_teacher_feature_snapshots_teacher_id"),
        table_name="teacher_feature_snapshots",
    )
    op.drop_index(
        op.f("ix_teacher_feature_snapshots_id"),
        table_name="teacher_feature_snapshots",
    )
    op.drop_table("teacher_feature_snapshots")
