"""SQLAlchemy models for the personalization domain."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base_class import Base


class UserPersonalizationProfile(Base):
    """Single source of truth for a user's personalized learning state."""

    __tablename__ = "user_personalization_profile"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    personalization_version = Column(Integer, nullable=False, default=1)
    status = Column(String(30), nullable=False, default="active")
    profile_completeness = Column(Float, nullable=False, default=0.0)
    personalization_started_at = Column(DateTime(timezone=True), nullable=True)
    last_recomputed_at = Column(DateTime(timezone=True), nullable=True)
    last_reset_at = Column(DateTime(timezone=True), nullable=True)
    staleness_threshold_days = Column(Integer, nullable=False, default=7)
    meta = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("idx_upp_user_id_model", "user_id", unique=True),
        Index("idx_upp_status_model", "status"),
    )

    def __repr__(self) -> str:
        return f"<UserPersonalizationProfile(user_id={self.user_id}, version={self.personalization_version}, status={self.status})>"


class ProfileVersion(Base):
    """Append-only log of profile versions."""

    __tablename__ = "profile_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    personalization_profile_id = Column(UUID(as_uuid=True), ForeignKey("user_personalization_profile.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    version_number = Column(Integer, nullable=False)
    profile_snapshot = Column(JSONB, nullable=False, default=dict)
    completeness = Column(Float, nullable=False, default=0.0)
    change_type = Column(String(30), nullable=True)
    changed_fields = Column(JSONB, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("idx_pv_profile_id_model", "personalization_profile_id"),
        Index("idx_pv_user_version_model", "user_id", "version_number"),
    )

    def __repr__(self) -> str:
        return f"<ProfileVersion(user_id={self.user_id}, version={self.version_number}, change={self.change_type})>"


class PersonalizationSnapshot(Base):
    """Snapshot linking feature data + ML output for a personalization compute pass."""

    __tablename__ = "personalization_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    personalization_profile_id = Column(UUID(as_uuid=True), ForeignKey("user_personalization_profile.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    personalization_version = Column(Integer, nullable=False)
    trigger = Column(String(50), nullable=True)
    feature_snapshot_id = Column(UUID(as_uuid=True), ForeignKey("teacher_feature_snapshots.id", ondelete="SET NULL"), nullable=True)
    ml_output_id = Column(UUID(as_uuid=True), ForeignKey("ml_outputs.id", ondelete="SET NULL"), nullable=True)
    ranking_signals = Column(JSONB, nullable=False, default=dict)
    is_current = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("idx_ps_profile_current_model", "personalization_profile_id", "is_current"),
        Index("idx_ps_user_version_model", "user_id", "personalization_version"),
    )

    def __repr__(self) -> str:
        return f"<PersonalizationSnapshot(user_id={self.user_id}, trigger={self.trigger}, current={self.is_current})>"


class PersonalizationJob(Base):
    """Tracks personalization background job lifecycle."""

    __tablename__ = "personalization_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    personalization_profile_id = Column(UUID(as_uuid=True), ForeignKey("user_personalization_profile.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    job_type = Column(String(50), nullable=False)
    status = Column(String(30), nullable=False, default="queued")
    section = Column(String(50), nullable=True)
    trigger = Column(String(50), nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=3)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)
    meta = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("idx_pj_profile_status_model", "personalization_profile_id", "status"),
        Index("idx_pj_user_type_model", "user_id", "job_type"),
    )

    def __repr__(self) -> str:
        return f"<PersonalizationJob(user_id={self.user_id}, type={self.job_type}, status={self.status})>"


class PersonalizedContentAssignment(Base):
    """A specific content item assigned to a user's personalized learning plan."""

    __tablename__ = "personalized_content_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    personalization_profile_id = Column(UUID(as_uuid=True), ForeignKey("user_personalization_profile.id", ondelete="CASCADE"), nullable=False)
    snapshot_id = Column(UUID(as_uuid=True), ForeignKey("personalization_snapshots.id", ondelete="SET NULL"), nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    personalization_version = Column(Integer, nullable=False)
    content_id = Column(String(150), nullable=False)
    content_type = Column(String(50), nullable=False)
    section = Column(String(50), nullable=False)
    bucket = Column(String(30), nullable=False, default="visible")
    position = Column(Integer, nullable=False, default=0)
    priority_rank = Column(Integer, nullable=False, default=0)
    diversity_key = Column(String(255), nullable=True)
    score = Column(Float, nullable=False, default=0.0)
    reason_codes = Column(JSONB, nullable=False, default=list)
    ranking_signals = Column(JSONB, nullable=False, default=dict)
    route = Column(String(255), nullable=True)
    content_slug = Column(String(255), nullable=True)
    status = Column(String(30), nullable=False, default="assigned")
    is_active = Column(Boolean, nullable=False, default=True)
    superseded_at = Column(DateTime(timezone=True), nullable=True)
    superseded_by_version = Column(Integer, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "personalization_version", "content_id", name="uq_pca_user_version_content_model"),
        Index("idx_pca_user_section_active_model", "user_id", "section", "is_active"),
        Index("idx_pca_profile_version_model", "personalization_profile_id", "personalization_version"),
        Index("idx_pca_content_id_model", "content_id"),
        Index("idx_pca_status_model", "status", "is_active"),
        Index("idx_pca_user_section_bucket_model", "user_id", "section", "bucket", "position"),
    )

    def __repr__(self) -> str:
        return f"<PersonalizedContentAssignment(user_id={self.user_id}, content_id={self.content_id}, section={self.section}, bucket={self.bucket})>"


class RecommendationSlate(Base):
    """A rendered slate of assignments served to the user."""

    __tablename__ = "recommendation_slates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    personalization_profile_id = Column(UUID(as_uuid=True), ForeignKey("user_personalization_profile.id", ondelete="CASCADE"), nullable=False)
    snapshot_id = Column(UUID(as_uuid=True), ForeignKey("personalization_snapshots.id", ondelete="SET NULL"), nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    personalization_version = Column(Integer, nullable=False)
    is_current = Column(Boolean, nullable=False, default=True)
    built_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    meta = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("idx_rs_user_current_model", "user_id", "is_current"),
        Index("idx_rs_profile_version_model", "personalization_profile_id", "personalization_version"),
    )

    def __repr__(self) -> str:
        return f"<RecommendationSlate(user_id={self.user_id}, version={self.personalization_version}, current={self.is_current})>"


class RecommendationSlateItem(Base):
    """A single card in a recommendation slate."""

    __tablename__ = "recommendation_slate_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slate_id = Column(UUID(as_uuid=True), ForeignKey("recommendation_slates.id", ondelete="CASCADE"), nullable=False)
    assignment_id = Column(UUID(as_uuid=True), ForeignKey("personalized_content_assignments.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    section = Column(String(50), nullable=False)
    bucket = Column(String(30), nullable=False)
    position = Column(Integer, nullable=False)
    locked = Column(Boolean, nullable=False, default=False)
    content_id = Column(String(150), nullable=False)
    content_type = Column(String(50), nullable=False)
    title = Column(String(500), nullable=True)
    route = Column(String(255), nullable=True)
    content_slug = Column(String(255), nullable=True)
    score = Column(Float, nullable=False, default=0.0)
    reason_codes = Column(JSONB, nullable=False, default=list)
    display_meta = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("idx_rsi_slate_section_model", "slate_id", "section", "bucket", "position"),
        Index("idx_rsi_user_section_model", "user_id", "section"),
    )

    def __repr__(self) -> str:
        return f"<RecommendationSlateItem(section={self.section}, bucket={self.bucket}, content_id={self.content_id})>"


class UnlockRule(Base):
    """Config-driven unlock rules. Admin-editable without code deploys."""

    __tablename__ = "unlock_rules"

    rule_id = Column(String(100), primary_key=True)
    section = Column(String(50), nullable=False)
    batch_order = Column(Integer, nullable=False)
    trigger_type = Column(String(50), nullable=False)
    trigger_section = Column(String(50), nullable=False)
    trigger_threshold = Column(Integer, nullable=False)
    unlock_count = Column(Integer, nullable=False)
    unlock_selection = Column(String(50), nullable=False, default="next_by_position")
    cooldown_seconds = Column(Integer, nullable=False, default=0)
    enabled = Column(Boolean, nullable=False, default=True)
    priority = Column(Integer, nullable=False, default=100)
    rule_metadata = Column("metadata", JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("idx_unlock_rules_section_enabled_model", "section", "enabled", "batch_order"),
    )

    def __repr__(self) -> str:
        return f"<UnlockRule(rule_id={self.rule_id}, section={self.section}, threshold={self.trigger_threshold})>"


class SectionInventoryConfig(Base):
    """Per-section inventory configuration. Admin-editable."""

    __tablename__ = "section_inventory_config"

    section = Column(String(50), primary_key=True)
    visible_count = Column(Integer, nullable=False)
    locked_preview_count = Column(Integer, nullable=False)
    reserve_buffer_count = Column(Integer, nullable=False)
    refill_threshold = Column(Integer, nullable=False)
    generation_trigger = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    def __repr__(self) -> str:
        return f"<SectionInventoryConfig(section={self.section}, visible={self.visible_count})>"


class UnlockState(Base):
    """Current lock/unlock state per assignment."""

    __tablename__ = "unlock_states"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assignment_id = Column(UUID(as_uuid=True), ForeignKey("personalized_content_assignments.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    section = Column(String(50), nullable=False)
    personalization_version = Column(Integer, nullable=False)
    locked = Column(Boolean, nullable=False, default=False)
    bucket = Column(String(30), nullable=False)
    unlocked_at = Column(DateTime(timezone=True), nullable=True)
    unlock_rule_id = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        UniqueConstraint("assignment_id", name="uq_unlock_states_assignment_model"),
        Index("idx_us_user_section_model", "user_id", "section", "locked"),
        Index("idx_us_assignment_model", "assignment_id"),
    )

    def __repr__(self) -> str:
        return f"<UnlockState(assignment_id={self.assignment_id}, locked={self.locked})>"


class UnlockEvent(Base):
    """Append-only log of unlock transitions."""

    __tablename__ = "unlock_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assignment_id = Column(UUID(as_uuid=True), ForeignKey("personalized_content_assignments.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    section = Column(String(50), nullable=False)
    personalization_version = Column(Integer, nullable=False)
    rule_id = Column(String(100), ForeignKey("unlock_rules.rule_id", ondelete="SET NULL"), nullable=True)
    from_state = Column(String(30), nullable=False)
    to_state = Column(String(30), nullable=False)
    trigger_event_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("idx_ue_user_section_model", "user_id", "section"),
        Index("idx_ue_rule_model", "rule_id"),
    )

    def __repr__(self) -> str:
        return f"<UnlockEvent(user_id={self.user_id}, section={self.section}, {self.from_state}->{self.to_state})>"


class UserActivityEvent(Base):
    """Append-only user behavior events. Never mutated."""

    __tablename__ = "user_activity_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    client_event_id = Column(String(100), nullable=True)
    event_type = Column(String(50), nullable=False)
    section = Column(String(50), nullable=True)
    content_id = Column(String(150), nullable=True)
    content_type = Column(String(50), nullable=True)
    assignment_id = Column(UUID(as_uuid=True), nullable=True)
    slate_id = Column(UUID(as_uuid=True), nullable=True)
    session_id = Column(UUID(as_uuid=True), nullable=True)
    dwell_ms = Column(Integer, nullable=True)
    event_metadata = Column("metadata", JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("idx_uae_user_section_model", "user_id", "section", "event_type"),
        Index("idx_uae_user_content_model", "user_id", "content_id"),
        Index("idx_uae_client_event_id_model", "user_id", "client_event_id", unique=True),
        Index("idx_uae_created_model", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<UserActivityEvent(user_id={self.user_id}, type={self.event_type}, section={self.section})>"


class SectionReadiness(Base):
    """Per-section readiness state for a user's personalization version."""

    __tablename__ = "section_readiness"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    personalization_profile_id = Column(UUID(as_uuid=True), ForeignKey("user_personalization_profile.id", ondelete="CASCADE"), nullable=False)
    section = Column(String(50), nullable=False)
    status = Column(String(30), nullable=False, default="not_started")
    personalization_version = Column(Integer, nullable=False)
    snapshot_id = Column(UUID(as_uuid=True), ForeignKey("personalization_snapshots.id", ondelete="SET NULL"), nullable=True)
    slate_id = Column(UUID(as_uuid=True), ForeignKey("recommendation_slates.id", ondelete="SET NULL"), nullable=True)
    job_id = Column(UUID(as_uuid=True), ForeignKey("personalization_jobs.id", ondelete="SET NULL"), nullable=True)
    visible_count_target = Column(Integer, nullable=False)
    visible_count_actual = Column(Integer, nullable=False, default=0)
    last_ready_at = Column(DateTime(timezone=True), nullable=True)
    last_failed_at = Column(DateTime(timezone=True), nullable=True)
    failure_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "section", "personalization_version", name="uq_sr_user_section_version_model"),
        Index("idx_sr_user_section_model", "user_id", "section"),
        Index("idx_sr_status_model", "status"),
    )

    def __repr__(self) -> str:
        return f"<SectionReadiness(user_id={self.user_id}, section={self.section}, status={self.status})>"
