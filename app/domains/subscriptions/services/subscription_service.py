"""
Subscription service for managing user subscriptions.
"""
from typing import Optional
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domains.subscriptions.models import (
    UserSubscription,
    SubscriptionHistory,
    SubscriptionTierModel,
)
from app.domains.subscriptions.enums import SubscriptionTier, SubscriptionStatus

logger = get_logger(__name__)


class SubscriptionService:
    """Service for managing user subscriptions."""

    def __init__(self, db: Session):
        self.db = db

    def get_user_subscription(self, user_id: UUID) -> UserSubscription:
        """Get or create user subscription."""
        subscription = self.db.query(UserSubscription).filter(
            UserSubscription.user_id == user_id
        ).first()

        if not subscription:
            # Create free tier subscription by default
            subscription = UserSubscription(
                user_id=user_id,
                tier=SubscriptionTier.FREE.value,
                status=SubscriptionStatus.ACTIVE.value,
            )
            self.db.add(subscription)
            self.db.commit()
            self.db.refresh(subscription)

        return subscription

    def get_user_tier(self, user_id: UUID) -> SubscriptionTier:
        """Get user's current subscription tier."""
        subscription = self.get_user_subscription(user_id)
        return SubscriptionTier(subscription.tier)

    def upgrade_user_tier(
        self,
        user_id: UUID,
        new_tier: SubscriptionTier,
        granted_by_user_id: Optional[UUID] = None,
        reason: Optional[str] = None,
        is_manual: bool = False,
    ) -> UserSubscription:
        """Upgrade user to a new tier (for testing/admin use)."""
        subscription = self.get_user_subscription(user_id)
        old_tier = subscription.tier

        # Update subscription
        subscription.tier = new_tier.value
        subscription.status = SubscriptionStatus.ACTIVE.value

        if is_manual:
            subscription.is_manually_granted = True
            subscription.granted_by_user_id = granted_by_user_id
            subscription.granted_at = datetime.now(timezone.utc)
            subscription.grant_reason = reason or "Manually granted for testing"

        # Log history
        self._log_tier_change(
            user_id=user_id,
            subscription_id=subscription.id,
            from_tier=old_tier,
            to_tier=new_tier.value,
            changed_by_user_id=granted_by_user_id,
            reason=reason,
        )

        self.db.commit()
        self.db.refresh(subscription)

        return subscription

    def get_available_upgrades(self, user_id: UUID) -> list[dict]:
        """Get available tier upgrades for user."""
        subscription = self.get_user_subscription(user_id)
        current_tier = subscription.tier

        # Get tier hierarchy level
        current_tier_model = self.db.query(SubscriptionTierModel).filter(
            SubscriptionTierModel.tier_key == current_tier
        ).first()

        if not current_tier_model:
            return []

        current_level = current_tier_model.hierarchy_level

        # Get all tiers above current level
        available_tiers = self.db.query(SubscriptionTierModel).filter(
            SubscriptionTierModel.hierarchy_level > current_level,
            SubscriptionTierModel.is_public == True,
            SubscriptionTierModel.is_active == True,
        ).order_by(SubscriptionTierModel.hierarchy_level).all()

        return [
            {
                "tier_key": tier.tier_key,
                "tier_name": tier.tier_name,
                "tier_description": tier.tier_description,
                "price_monthly": float(tier.price_monthly) if tier.price_monthly else None,
                "price_yearly": float(tier.price_yearly) if tier.price_yearly else None,
            }
            for tier in available_tiers
        ]

    def _log_tier_change(
        self,
        user_id: UUID,
        subscription_id: UUID,
        from_tier: str,
        to_tier: str,
        changed_by_user_id: Optional[UUID],
        reason: Optional[str],
    ):
        """Log subscription tier change for audit."""
        history = SubscriptionHistory(
            user_id=user_id,
            subscription_id=subscription_id,
            action="tier_changed",
            from_tier=from_tier,
            to_tier=to_tier,
            changed_by_user_id=changed_by_user_id,
            reason=reason,
        )
        self.db.add(history)
