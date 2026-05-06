"""personalization_core_tables

Phase 1: Creates user_personalization_profile, profile_versions, personalization_snapshots,
personalization_jobs. Also modifies teacher_profile_context and content_generation_jobs.

Revision ID: o1p2q3r4s5t6
Revises: n1o2p3q4r5s6
Create Date: 2026-03-31

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "o1p2q3r4s5t6"
down_revision: Union[str, None] = "n1o2p3q4r5s6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # user_personalization_profile
    # ------------------------------------------------------------------
    op.create_table(
        "user_personalization_profile",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("personalization_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.Column("profile_completeness", sa.Float(), nullable=False, server_default="0"),
        sa.Column("personalization_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_recomputed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_reset_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("staleness_threshold_days", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("meta", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_upp_user_id", "user_personalization_profile", ["user_id"], unique=True)
    op.create_index("idx_upp_status", "user_personalization_profile", ["status"])

    # ------------------------------------------------------------------
    # profile_versions  (append-only)
    # ------------------------------------------------------------------
    op.create_table(
        "profile_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "personalization_profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_personalization_profile.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("profile_snapshot", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("completeness", sa.Float(), nullable=False, server_default="0"),
        sa.Column("change_type", sa.String(30), nullable=True),   # none | minor_recompute | major_reset
        sa.Column("changed_fields", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_pv_profile_id", "profile_versions", ["personalization_profile_id"])
    op.create_index("idx_pv_user_version", "profile_versions", ["user_id", "version_number"])

    # ------------------------------------------------------------------
    # personalization_snapshots
    # ------------------------------------------------------------------
    op.create_table(
        "personalization_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "personalization_profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_personalization_profile.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("personalization_version", sa.Integer(), nullable=False),
        sa.Column("trigger", sa.String(50), nullable=True),  # initial | recompute | reset | scheduled
        sa.Column("feature_snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("teacher_feature_snapshots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("ml_output_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ml_outputs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("ranking_signals", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_ps_profile_current", "personalization_snapshots", ["personalization_profile_id", "is_current"])
    op.create_index("idx_ps_user_version", "personalization_snapshots", ["user_id", "personalization_version"])

    # ------------------------------------------------------------------
    # personalization_jobs
    # ------------------------------------------------------------------
    op.create_table(
        "personalization_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "personalization_profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_personalization_profile.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_type", sa.String(50), nullable=False),   # start | recompute | reset | expand_assignments | rebuild_slate | reconcile_unlocks
        sa.Column("status", sa.String(30), nullable=False, server_default="queued"),  # queued | running | completed | failed
        sa.Column("section", sa.String(50), nullable=True),     # null = applies to all sections
        sa.Column("trigger", sa.String(50), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("meta", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_pj_profile_status", "personalization_jobs", ["personalization_profile_id", "status"])
    op.create_index("idx_pj_user_type", "personalization_jobs", ["user_id", "job_type"])

    # ------------------------------------------------------------------
    # Modify teacher_profile_context
    # ------------------------------------------------------------------
    op.add_column("teacher_profile_context", sa.Column("profile_revision", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("teacher_profile_context", sa.Column("last_completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("teacher_profile_context", sa.Column("last_reset_at", sa.DateTime(timezone=True), nullable=True))

    # ------------------------------------------------------------------
    # Modify content_generation_jobs
    # ------------------------------------------------------------------
    op.add_column("content_generation_jobs", sa.Column("personalization_profile_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("content_generation_jobs", sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("content_generation_jobs", sa.Column("section", sa.String(50), nullable=True))
    op.add_column("content_generation_jobs", sa.Column("assignment_id", postgresql.UUID(as_uuid=True), nullable=True))


def downgrade() -> None:
    op.drop_column("content_generation_jobs", "assignment_id")
    op.drop_column("content_generation_jobs", "section")
    op.drop_column("content_generation_jobs", "snapshot_id")
    op.drop_column("content_generation_jobs", "personalization_profile_id")

    op.drop_column("teacher_profile_context", "last_reset_at")
    op.drop_column("teacher_profile_context", "last_completed_at")
    op.drop_column("teacher_profile_context", "profile_revision")

    op.drop_index("idx_pj_user_type", table_name="personalization_jobs")
    op.drop_index("idx_pj_profile_status", table_name="personalization_jobs")
    op.drop_table("personalization_jobs")

    op.drop_index("idx_ps_user_version", table_name="personalization_snapshots")
    op.drop_index("idx_ps_profile_current", table_name="personalization_snapshots")
    op.drop_table("personalization_snapshots")

    op.drop_index("idx_pv_user_version", table_name="profile_versions")
    op.drop_index("idx_pv_profile_id", table_name="profile_versions")
    op.drop_table("profile_versions")

    op.drop_index("idx_upp_status", table_name="user_personalization_profile")
    op.drop_index("idx_upp_user_id", table_name="user_personalization_profile")
    op.drop_table("user_personalization_profile")
