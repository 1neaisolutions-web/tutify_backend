"""
Subscription domain models.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional
from decimal import Decimal

from sqlalchemy import (
    Column, String, Text, Boolean, Integer, DateTime, ForeignKey, JSON,
    Enum as SQLEnum, Index, UniqueConstraint, Numeric
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.db.base_class import Base
from app.domains.subscriptions.enums import SubscriptionTier, SubscriptionStatus


class SubscriptionTierModel(Base):
    """Subscription tier definition model."""

    __tablename__ = "subscription_tiers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tier_key = Column(String(50), unique=True, nullable=False, index=True)
    tier_name = Column(String(200), nullable=False)
    tier_description = Column(Text, nullable=True)
    hierarchy_level = Column(Integer, nullable=False, default=0)
    display_order = Column(Integer, nullable=False, default=0)
    price_monthly = Column(Numeric(10, 2), nullable=True)
    price_yearly = Column(Numeric(10, 2), nullable=True)
    currency = Column(String(3), default="USD", nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_public = Column(Boolean, default=True, nullable=False)
    tier_metadata = Column("metadata", JSONB, nullable=True)  # Use 'metadata' as DB column name but 'tier_metadata' as Python attr

    # Timestamps

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    features = relationship("SubscriptionTierFeature", back_populates="tier_model", cascade="all, delete-orphan")
    user_subscriptions = relationship("UserSubscription", back_populates="tier_model")

    def __repr__(self) -> str:
        return f"<SubscriptionTier(id={self.id}, tier_key={self.tier_key}, tier_name={self.tier_name})>"


class SubscriptionTierFeature(Base):
    """Feature matrix per subscription tier."""

    __tablename__ = "subscription_tier_features"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tier = Column(String(20), ForeignKey("subscription_tiers.tier_key", ondelete="CASCADE"), nullable=False, index=True)
    feature_key = Column(String(100), nullable=False, index=True)
    feature_name = Column(String(200), nullable=False)
    is_enabled = Column(Boolean, default=True, nullable=False)
    limit_value = Column(Integer, nullable=True)  # NULL = unlimited
    limit_period = Column(String(20), nullable=True)  # 'daily', 'monthly', 'lifetime', 'minute', 'hour'
    feature_metadata = Column("metadata", JSONB, nullable=True)  # Use 'metadata' as DB column name but 'feature_metadata' as Python attr

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    tier_model = relationship("SubscriptionTierModel", back_populates="features", foreign_keys=[tier], primaryjoin="SubscriptionTierFeature.tier == SubscriptionTierModel.tier_key")

    __table_args__ = (
        UniqueConstraint("tier", "feature_key", name="uq_tier_feature"),
        Index("idx_tier_feature", "tier", "feature_key"),
    )

    def __repr__(self) -> str:
        return f"<SubscriptionTierFeature(id={self.id}, tier={self.tier}, feature_key={self.feature_key})>"


class UserSubscription(Base):
    """User subscription state model."""

    __tablename__ = "user_subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    tier = Column(String(20), ForeignKey("subscription_tiers.tier_key", ondelete="RESTRICT"), nullable=False, default=SubscriptionTier.FREE.value, index=True)
    status = Column(String(20), nullable=False, default=SubscriptionStatus.ACTIVE.value, index=True)

    # Trial period
    trial_started_at = Column(DateTime(timezone=True), nullable=True)
    trial_ends_at = Column(DateTime(timezone=True), nullable=True)
    is_trial = Column(Boolean, default=False, nullable=False)

    # Subscription period
    current_period_start = Column(DateTime(timezone=True), nullable=True)
    current_period_end = Column(DateTime(timezone=True), nullable=True)

    # Payment integration (for future)
    payment_provider = Column(String(50), nullable=True)  # 'stripe', 'paypal', 'manual', 'admin_granted'
    payment_customer_id = Column(String(200), nullable=True)
    payment_subscription_id = Column(String(200), nullable=True)

    # Admin override (for testing/unlocking)
    is_manually_granted = Column(Boolean, default=False, nullable=False)
    granted_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    granted_at = Column(DateTime(timezone=True), nullable=True)
    grant_reason = Column(Text, nullable=True)

    # Metadata
    subscription_metadata = Column("metadata", JSONB, nullable=True)  # Use 'metadata' as DB column name but 'subscription_metadata' as Python attr
    notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    tier_model = relationship("SubscriptionTierModel", foreign_keys=[tier], primaryjoin="UserSubscription.tier == SubscriptionTierModel.tier_key")
    granted_by = relationship("User", foreign_keys=[granted_by_user_id])
    history = relationship("SubscriptionHistory", back_populates="subscription", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_user_tier", "user_id", "tier"),
        Index("idx_tier_status", "tier", "status"),
    )

    def __repr__(self) -> str:
        return f"<UserSubscription(id={self.id}, user_id={self.user_id}, tier={self.tier}, status={self.status})>"


class SubscriptionHistory(Base):
    """Subscription history audit trail."""

    __tablename__ = "subscription_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("user_subscriptions.id", ondelete="CASCADE"), nullable=False)
    action = Column(String(50), nullable=False)  # 'tier_changed', 'trial_started', 'payment_processed', etc.
    from_tier = Column(String(20), nullable=True)
    to_tier = Column(String(20), nullable=True)
    changed_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reason = Column(Text, nullable=True)
    history_metadata = Column("metadata", JSONB, nullable=True)  # Use 'metadata' as DB column name but 'history_metadata' as Python attr

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    subscription = relationship("UserSubscription", back_populates="history")
    changed_by = relationship("User", foreign_keys=[changed_by_user_id])

    __table_args__ = (
        Index("idx_user_history", "user_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<SubscriptionHistory(id={self.id}, user_id={self.user_id}, action={self.action})>"


class UserUsageQuota(Base):
    """User usage quota tracking model."""

    __tablename__ = "user_usage_quotas"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    subscription_tier = Column(String(20), ForeignKey("subscription_tiers.tier_key", ondelete="RESTRICT"), nullable=False)

    # Daily limits
    daily_messages_limit = Column(Integer, nullable=False, default=20)
    daily_messages_used = Column(Integer, nullable=False, default=0)
    daily_reset_at = Column(DateTime(timezone=True), nullable=True)

    # Monthly limits
    monthly_messages_limit = Column(Integer, nullable=False, default=500)
    monthly_messages_used = Column(Integer, nullable=False, default=0)
    monthly_reset_at = Column(DateTime(timezone=True), nullable=True)

    # Rate limiting
    requests_per_minute = Column(Integer, nullable=False, default=3)
    requests_per_hour = Column(Integer, nullable=False, default=50)
    last_request_at = Column(DateTime(timezone=True), nullable=True)
    request_window_start = Column(DateTime(timezone=True), nullable=True)
    request_count_in_window = Column(Integer, nullable=False, default=0)

    # Feature flags
    features = Column(JSONB, nullable=True)  # Store feature-specific limits

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        UniqueConstraint("user_id", "subscription_tier", name="uq_user_tier"),
        # Distinct from UserSubscription.idx_user_tier — SQLite requires globally unique index names.
        Index("idx_user_usage_quota_user_tier", "user_id", "subscription_tier"),
    )

    def __repr__(self) -> str:
        return f"<UserUsageQuota(id={self.id}, user_id={self.user_id}, tier={self.subscription_tier})>"


class UserUsageLog(Base):
    """User usage log for analytics."""

    __tablename__ = "user_usage_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    action = Column(String(50), nullable=False)  # 'message_sent', 'audio_transcribed', 'web_search', etc.
    feature_key = Column(String(100), nullable=True, index=True)
    tokens_used = Column(Integer, nullable=True)
    cost_estimate = Column(Numeric(10, 6), nullable=True)
    model_used = Column(String(100), nullable=True)
    provider_used = Column(String(50), nullable=True)
    usage_metadata = Column("metadata", JSONB, nullable=True)  # Use 'metadata' as DB column name but 'usage_metadata' as Python attr

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        Index("idx_user_date", "user_id", "created_at"),
        Index("idx_action_date", "action", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<UserUsageLog(id={self.id}, user_id={self.user_id}, action={self.action})>"


class FeatureCreditCost(Base):
    """Credit cost configuration per feature key."""

    __tablename__ = "feature_credit_costs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    feature_key = Column(String(100), unique=True, nullable=False, index=True)
    display_name = Column(String(200), nullable=False)
    module_name = Column(String(100), nullable=False)
    base_credits = Column(Integer, nullable=False, default=1)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    def __repr__(self) -> str:
        return f"<FeatureCreditCost(feature_key={self.feature_key}, base_credits={self.base_credits})>"


class AccessCode(Base):
    """Access codes for activating credits (beta and staff)."""

    __tablename__ = "access_codes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    code_type = Column(String(20), nullable=False)  # 'beta' | 'staff'
    credit_allocation = Column(Integer, nullable=False)
    validity_days = Column(Integer, nullable=False, default=30)
    max_uses = Column(Integer, nullable=True)  # null = unlimited
    times_used = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, default=True, nullable=False)
    auto_renew = Column(Boolean, default=False, nullable=False)
    auto_renew_threshold_pct = Column(Integer, nullable=True, default=20)
    description = Column(Text, nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    redemptions = relationship("UserCodeRedemption", back_populates="access_code", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<AccessCode(code={self.code}, type={self.code_type}, allocation={self.credit_allocation})>"


class UserCodeRedemption(Base):
    """Record of every access code activation per user."""

    __tablename__ = "user_code_redemptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    access_code_id = Column(UUID(as_uuid=True), ForeignKey("access_codes.id", ondelete="CASCADE"), nullable=False)
    redeemed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    credit_allocation = Column(Integer, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    auto_renew = Column(Boolean, default=False, nullable=False)
    last_renewed_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", foreign_keys=[user_id])
    access_code = relationship("AccessCode", back_populates="redemptions")

    __table_args__ = (
        Index("idx_redemption_user_active", "user_id", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<UserCodeRedemption(user_id={self.user_id}, code_id={self.access_code_id})>"


class UserTokenBalance(Base):
    """The user's live credit wallet — one row per user."""

    __tablename__ = "user_token_balances"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                     unique=True, nullable=False, index=True)
    balance = Column(Integer, nullable=False, default=0)
    total_allocated = Column(Integer, nullable=False, default=0)
    total_spent = Column(Integer, nullable=False, default=0)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    auto_renew = Column(Boolean, default=False, nullable=False)
    subscription_started_at = Column(DateTime(timezone=True), nullable=True)
    last_topped_up_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", foreign_keys=[user_id])

    def __repr__(self) -> str:
        return f"<UserTokenBalance(user_id={self.user_id}, balance={self.balance})>"


class UserCreditTransaction(Base):
    """Append-only credit ledger — every debit and credit event."""

    __tablename__ = "user_credit_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(String(20), nullable=False)  # 'debit' | 'credit' | 'renewal' | 'expiry_adjustment'
    amount = Column(Integer, nullable=False)   # positive = credit added, negative = credits spent
    balance_after = Column(Integer, nullable=False)
    feature_key = Column(String(100), nullable=True, index=True)
    description = Column(String(500), nullable=True)
    reference_id = Column(UUID(as_uuid=True), nullable=True)
    model_used = Column(String(100), nullable=True)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    usd_cost = Column(Numeric(10, 6), nullable=True)
    transaction_metadata = Column("metadata", JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        Index("idx_txn_user_date", "user_id", "created_at"),
        Index("idx_txn_feature_key", "user_id", "feature_key"),
    )

    def __repr__(self) -> str:
        return f"<UserCreditTransaction(user_id={self.user_id}, type={self.type}, amount={self.amount})>"
