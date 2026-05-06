"""personalization_unlock_activity

Phase 3: Creates unlock_rules (with seed data), unlock_states, unlock_events,
user_activity_events, section_readiness, section_inventory_config (with seed data).

Revision ID: q3r4s5t6u7v8
Revises: p2q3r4s5t6u7
Create Date: 2026-03-31

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "q3r4s5t6u7v8"
down_revision: Union[str, None] = "p2q3r4s5t6u7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # unlock_rules  (config-driven, admin-editable)
    # ------------------------------------------------------------------
    op.create_table(
        "unlock_rules",
        sa.Column("rule_id", sa.String(100), primary_key=True),
        sa.Column("section", sa.String(50), nullable=False),
        sa.Column("batch_order", sa.Integer(), nullable=False),
        sa.Column("trigger_type", sa.String(50), nullable=False),
        sa.Column("trigger_section", sa.String(50), nullable=False),
        sa.Column("trigger_threshold", sa.Integer(), nullable=False),
        sa.Column("unlock_count", sa.Integer(), nullable=False),
        sa.Column("unlock_selection", sa.String(50), nullable=False, server_default="next_by_position"),
        sa.Column("cooldown_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_unlock_rules_section_enabled", "unlock_rules", ["section", "enabled", "batch_order"])

    # Seed unlock rules
    op.execute("""
        INSERT INTO unlock_rules (rule_id, section, batch_order, trigger_type, trigger_section, trigger_threshold, unlock_count, unlock_selection, priority)
        VALUES
            ('micro_courses_b1', 'micro_courses', 1, 'completion_count', 'micro_courses', 5, 5, 'next_by_position', 100),
            ('growth_recommendations_b1', 'growth_recommendations', 1, 'engagement_count', 'growth_recommendations', 3, 3, 'next_by_position', 100),
            ('tutorials_b1', 'tutorials', 1, 'completion_count', 'tutorials', 3, 3, 'next_by_position', 100),
            ('research_insights_b1', 'research_insights', 1, 'completion_count', 'research_insights', 3, 3, 'next_by_position', 100),
            ('specialist_tracks_b1', 'specialist_tracks', 1, 'completion_count', 'specialist_tracks', 2, 2, 'next_by_position', 100)
    """)

    # ------------------------------------------------------------------
    # section_inventory_config  (config-driven, admin-editable)
    # ------------------------------------------------------------------
    op.create_table(
        "section_inventory_config",
        sa.Column("section", sa.String(50), primary_key=True),
        sa.Column("visible_count", sa.Integer(), nullable=False),
        sa.Column("locked_preview_count", sa.Integer(), nullable=False),
        sa.Column("reserve_buffer_count", sa.Integer(), nullable=False),
        sa.Column("refill_threshold", sa.Integer(), nullable=False),
        sa.Column("generation_trigger", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # Seed inventory config
    op.execute("""
        INSERT INTO section_inventory_config (section, visible_count, locked_preview_count, reserve_buffer_count, refill_threshold, generation_trigger)
        VALUES
            ('micro_courses', 5, 5, 5, 3, 2),
            ('growth_recommendations', 3, 3, 4, 2, 1),
            ('tutorials', 3, 3, 4, 2, 1),
            ('research_insights', 3, 3, 4, 2, 1),
            ('specialist_tracks', 2, 2, 3, 1, 1)
    """)

    # ------------------------------------------------------------------
    # unlock_states
    # ------------------------------------------------------------------
    op.create_table(
        "unlock_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("personalized_content_assignments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("section", sa.String(50), nullable=False),
        sa.Column("personalization_version", sa.Integer(), nullable=False),
        sa.Column("locked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("bucket", sa.String(30), nullable=False),
        sa.Column("unlocked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unlock_rule_id", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("assignment_id", name="uq_unlock_states_assignment"),
    )
    op.create_index("idx_us_user_section", "unlock_states", ["user_id", "section", "locked"])
    op.create_index("idx_us_assignment", "unlock_states", ["assignment_id"])

    # ------------------------------------------------------------------
    # unlock_events  (append-only)
    # ------------------------------------------------------------------
    op.create_table(
        "unlock_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("personalized_content_assignments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("section", sa.String(50), nullable=False),
        sa.Column("personalization_version", sa.Integer(), nullable=False),
        sa.Column("rule_id", sa.String(100), sa.ForeignKey("unlock_rules.rule_id", ondelete="SET NULL"), nullable=True),
        sa.Column("from_state", sa.String(30), nullable=False),   # locked | unlocked
        sa.Column("to_state", sa.String(30), nullable=False),
        sa.Column("trigger_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_ue_user_section", "unlock_events", ["user_id", "section"])
    op.create_index("idx_ue_rule", "unlock_events", ["rule_id"])

    # ------------------------------------------------------------------
    # user_activity_events  (append-only)
    # ------------------------------------------------------------------
    op.create_table(
        "user_activity_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_event_id", sa.String(100), nullable=True),   # for idempotency
        sa.Column("event_type", sa.String(50), nullable=False),   # impression | card_clicked | content_started | content_completed | etc.
        sa.Column("section", sa.String(50), nullable=True),
        sa.Column("content_id", sa.String(150), nullable=True),
        sa.Column("content_type", sa.String(50), nullable=True),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("slate_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("dwell_ms", sa.Integer(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_uae_user_section", "user_activity_events", ["user_id", "section", "event_type"])
    op.create_index("idx_uae_user_content", "user_activity_events", ["user_id", "content_id"])
    op.create_index("idx_uae_client_event_id", "user_activity_events", ["user_id", "client_event_id"], unique=True)
    op.create_index("idx_uae_created", "user_activity_events", ["created_at"])

    # ------------------------------------------------------------------
    # section_readiness
    # ------------------------------------------------------------------
    op.create_table(
        "section_readiness",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "personalization_profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_personalization_profile.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("section", sa.String(50), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="not_started"),
        sa.Column("personalization_version", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("personalization_snapshots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("slate_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("recommendation_slates.id", ondelete="SET NULL"), nullable=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("personalization_jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("visible_count_target", sa.Integer(), nullable=False),
        sa.Column("visible_count_actual", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_ready_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "section", "personalization_version", name="uq_sr_user_section_version"),
    )
    op.create_index("idx_sr_user_section", "section_readiness", ["user_id", "section"])
    op.create_index("idx_sr_status", "section_readiness", ["status"])


def downgrade() -> None:
    op.drop_index("idx_sr_status", table_name="section_readiness")
    op.drop_index("idx_sr_user_section", table_name="section_readiness")
    op.drop_table("section_readiness")

    op.drop_index("idx_uae_created", table_name="user_activity_events")
    op.drop_index("idx_uae_client_event_id", table_name="user_activity_events")
    op.drop_index("idx_uae_user_content", table_name="user_activity_events")
    op.drop_index("idx_uae_user_section", table_name="user_activity_events")
    op.drop_table("user_activity_events")

    op.drop_index("idx_ue_rule", table_name="unlock_events")
    op.drop_index("idx_ue_user_section", table_name="unlock_events")
    op.drop_table("unlock_events")

    op.drop_index("idx_us_assignment", table_name="unlock_states")
    op.drop_index("idx_us_user_section", table_name="unlock_states")
    op.drop_table("unlock_states")

    op.drop_table("section_inventory_config")

    op.drop_index("idx_unlock_rules_section_enabled", table_name="unlock_rules")
    op.drop_table("unlock_rules")
