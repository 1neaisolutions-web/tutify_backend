"""personalization_assignment_slate

Phase 2: Creates personalized_content_assignments, recommendation_slates,
recommendation_slate_items. Modifies recommendation_events and learning_sessions.

Revision ID: p2q3r4s5t6u7
Revises: o1p2q3r4s5t6
Create Date: 2026-03-31

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "p2q3r4s5t6u7"
down_revision: Union[str, None] = "o1p2q3r4s5t6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # personalized_content_assignments
    # ------------------------------------------------------------------
    op.create_table(
        "personalized_content_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "personalization_profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_personalization_profile.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("personalization_snapshots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("personalization_version", sa.Integer(), nullable=False),
        sa.Column("content_id", sa.String(150), nullable=False),
        sa.Column("content_type", sa.String(50), nullable=False),
        sa.Column("section", sa.String(50), nullable=False),
        sa.Column("bucket", sa.String(30), nullable=False, server_default="visible"),  # visible | locked_preview | reserve
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("reason_codes", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("ranking_signals", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("route", sa.String(255), nullable=True),
        sa.Column("content_slug", sa.String(255), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="assigned"),  # assigned | started | completed | skipped | superseded
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_by_version", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "personalization_version", "content_id", name="uq_pca_user_version_content"),
    )
    op.create_index("idx_pca_user_section_active", "personalized_content_assignments", ["user_id", "section", "is_active"])
    op.create_index("idx_pca_profile_version", "personalized_content_assignments", ["personalization_profile_id", "personalization_version"])
    op.create_index("idx_pca_content_id", "personalized_content_assignments", ["content_id"])
    op.create_index("idx_pca_status", "personalized_content_assignments", ["status", "is_active"])

    # ------------------------------------------------------------------
    # recommendation_slates
    # ------------------------------------------------------------------
    op.create_table(
        "recommendation_slates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "personalization_profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_personalization_profile.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("personalization_snapshots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("personalization_version", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("built_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("meta", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_rs_user_current", "recommendation_slates", ["user_id", "is_current"])
    op.create_index("idx_rs_profile_version", "recommendation_slates", ["personalization_profile_id", "personalization_version"])

    # ------------------------------------------------------------------
    # recommendation_slate_items
    # ------------------------------------------------------------------
    op.create_table(
        "recommendation_slate_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("slate_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("recommendation_slates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("personalized_content_assignments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("section", sa.String(50), nullable=False),
        sa.Column("bucket", sa.String(30), nullable=False),   # visible | locked_preview
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("locked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("content_id", sa.String(150), nullable=False),
        sa.Column("content_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("route", sa.String(255), nullable=True),
        sa.Column("content_slug", sa.String(255), nullable=True),
        sa.Column("score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("reason_codes", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("display_meta", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_rsi_slate_section", "recommendation_slate_items", ["slate_id", "section", "bucket", "position"])
    op.create_index("idx_rsi_user_section", "recommendation_slate_items", ["user_id", "section"])

    # ------------------------------------------------------------------
    # Modify recommendation_events
    # ------------------------------------------------------------------
    op.add_column("recommendation_events", sa.Column("slate_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("recommendation_events", sa.Column("assignment_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("recommendation_events", sa.Column("section", sa.String(50), nullable=True))
    op.add_column("recommendation_events", sa.Column("position", sa.Integer(), nullable=True))

    # ------------------------------------------------------------------
    # Modify learning_sessions
    # ------------------------------------------------------------------
    op.add_column("learning_sessions", sa.Column("personalization_profile_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("learning_sessions", sa.Column("assignment_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("learning_sessions", sa.Column("section", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("learning_sessions", "section")
    op.drop_column("learning_sessions", "assignment_id")
    op.drop_column("learning_sessions", "personalization_profile_id")

    op.drop_column("recommendation_events", "position")
    op.drop_column("recommendation_events", "section")
    op.drop_column("recommendation_events", "assignment_id")
    op.drop_column("recommendation_events", "slate_id")

    op.drop_index("idx_rsi_user_section", table_name="recommendation_slate_items")
    op.drop_index("idx_rsi_slate_section", table_name="recommendation_slate_items")
    op.drop_table("recommendation_slate_items")

    op.drop_index("idx_rs_profile_version", table_name="recommendation_slates")
    op.drop_index("idx_rs_user_current", table_name="recommendation_slates")
    op.drop_table("recommendation_slates")

    op.drop_index("idx_pca_status", table_name="personalized_content_assignments")
    op.drop_index("idx_pca_content_id", table_name="personalized_content_assignments")
    op.drop_index("idx_pca_profile_version", table_name="personalized_content_assignments")
    op.drop_index("idx_pca_user_section_active", table_name="personalized_content_assignments")
    op.drop_table("personalized_content_assignments")
