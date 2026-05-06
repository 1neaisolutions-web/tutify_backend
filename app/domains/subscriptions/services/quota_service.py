"""
Quota service for enforcing usage limits.
"""
from typing import Optional, Dict, Any
from datetime import datetime, timezone, timedelta
from uuid import UUID
from dataclasses import dataclass

from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.core.logging import get_logger
from app.domains.subscriptions.models import UserUsageQuota, UserUsageLog
from app.domains.subscriptions.services.subscription_service import SubscriptionService

logger = get_logger(__name__)


@dataclass
class QuotaCheck:
    """Quota check result."""

    allowed: bool
    reason: Optional[str] = None
    current_usage: int = 0
    remaining: int = 0
    retry_after_seconds: Optional[int] = None


class QuotaService:
    """Service for enforcing usage quotas."""

    def __init__(self, db: Session):
        self.db = db
        self.subscription_service = SubscriptionService(db)

    def check_quota(
        self,
        user_id: UUID,
        feature_key: str,
        limit: Optional[int] = None,
        period: Optional[str] = None,
        increment: bool = False,
    ) -> QuotaCheck:
        """Check if user is within quota limits."""
        quota = self._get_or_create_quota(user_id)

        # Skip checks if quota is a dummy SimpleNamespace (tables don't exist)
        if not isinstance(quota, UserUsageQuota):
            # It's a SimpleNamespace dummy - allow all requests
            return QuotaCheck(
                allowed=True,
                current_usage=0,
                remaining=None,
            )

        # Check daily message limit
        if quota.daily_messages_limit and quota.daily_messages_limit > 0:
            # Reset if needed
            if quota.daily_reset_at is None or quota.daily_reset_at < datetime.now(timezone.utc):
                self._reset_daily_quota(quota)

            if quota.daily_messages_used >= quota.daily_messages_limit:
                return QuotaCheck(
                    allowed=False,
                    reason="daily_limit_exceeded",
                    current_usage=quota.daily_messages_used,
                    remaining=0,
                    retry_after_seconds=self._calculate_daily_reset_seconds(quota),
                )

        # Check rate limit (requests per minute)
        if not self._check_rate_limit(quota):
            return QuotaCheck(
                allowed=False,
                reason="rate_limit_exceeded",
                current_usage=quota.request_count_in_window,
                remaining=0,
                retry_after_seconds=60,
            )

        # If increment is requested and quota check passes, increment usage
        if increment:
            quota.daily_messages_used += 1
            quota.monthly_messages_used += 1
            quota.last_request_at = datetime.now(timezone.utc)
            quota.request_count_in_window += 1
            self.db.commit()

        return QuotaCheck(
            allowed=True,
            current_usage=quota.daily_messages_used,
            remaining=quota.daily_messages_limit - quota.daily_messages_used if quota.daily_messages_limit else None,
        )

    def _get_or_create_quota(self, user_id: UUID) -> UserUsageQuota:
        """Get or create user quota."""
        try:
            subscription = self.subscription_service.get_user_subscription(user_id)
            tier = subscription.tier if subscription else "free"
        except Exception as e:
            # Rollback any failed transaction
            try:
                self.db.rollback()
            except Exception:
                pass
            logger.warning(f"Could not get user subscription, defaulting to free tier: {e}")
            tier = "free"

        # Check if UserUsageQuota table exists before querying
        try:
            quota = self.db.query(UserUsageQuota).filter(
                and_(
                    UserUsageQuota.user_id == user_id,
                    UserUsageQuota.subscription_tier == tier,
                )
            ).first()
        except Exception as e:
            # Table doesn't exist, create a dummy quota object that allows everything
            logger.warning(f"UserUsageQuota table not available: {e}")
            self.db.rollback()
            # Return a simple quota check that allows everything
            from types import SimpleNamespace
            quota = SimpleNamespace(
                daily_messages_limit=None,
                daily_messages_used=0,
                monthly_messages_limit=None,
                monthly_messages_used=0,
                requests_per_minute=None,
                request_window_start=None,
                request_count_in_window=0,
                daily_reset_at=None,
                last_request_at=None,
            )
            return quota

        if not quota:
            # Create quota based on tier defaults
            quota = UserUsageQuota(
                user_id=user_id,
                subscription_tier=tier,
                daily_messages_limit=20 if tier == "free" else 500,
                monthly_messages_limit=500 if tier == "free" else None,
                requests_per_minute=3 if tier == "free" else 10,
            )
            self.db.add(quota)
            self.db.commit()
            self.db.refresh(quota)

        return quota

    def _check_rate_limit(self, quota: UserUsageQuota) -> bool:
        """Check if user is within rate limit."""
        now = datetime.now(timezone.utc)

        # Initialize window if needed
        if quota.request_window_start is None:
            quota.request_window_start = now
            quota.request_count_in_window = 0
            self.db.commit()
            return True

        # Reset window if it's been more than 1 minute
        time_since_window_start = (now - quota.request_window_start).total_seconds()
        if time_since_window_start >= 60:
            quota.request_window_start = now
            quota.request_count_in_window = 0
            self.db.commit()
            return True

        # Check if within limit
        if quota.request_count_in_window >= quota.requests_per_minute:
            return False

        return True

    def _reset_daily_quota(self, quota: UserUsageQuota):
        """Reset daily quota counters."""
        quota.daily_messages_used = 0
        quota.daily_reset_at = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        self.db.commit()

    def _calculate_daily_reset_seconds(self, quota: UserUsageQuota) -> int:
        """Calculate seconds until daily reset."""
        if quota.daily_reset_at:
            now = datetime.now(timezone.utc)
            delta = quota.daily_reset_at - now
            return max(0, int(delta.total_seconds()))
        return 86400  # Default to 24 hours

    def log_usage(
        self,
        user_id: UUID,
        action: str,
        feature_key: Optional[str] = None,
        tokens_used: Optional[int] = None,
        cost_estimate: Optional[float] = None,
        model_used: Optional[str] = None,
        provider_used: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Log usage for analytics."""
        try:
            log = UserUsageLog(
                user_id=user_id,
                action=action,
                feature_key=feature_key,
                tokens_used=tokens_used,
                cost_estimate=cost_estimate,
                model_used=model_used,
                provider_used=provider_used,
                metadata=metadata,
            )
            self.db.add(log)
            self.db.commit()
        except Exception as e:
            # Rollback on error and log warning - don't fail the main operation
            try:
                self.db.rollback()
            except Exception:
                pass
            logger.warning(f"Usage logging failed (table may not exist), continuing: {e}")

    def get_quota_summary(self, user_id: UUID) -> Dict[str, Any]:
        """Get quota summary for user."""
        quota = self._get_or_create_quota(user_id)

        is_rate_limited = False
        retry_after = None
        if not self._check_rate_limit(quota):
            is_rate_limited = True
            retry_after = 60

        return {
            "daily_messages_used": quota.daily_messages_used,
            "daily_messages_limit": quota.daily_messages_limit,
            "monthly_messages_used": quota.monthly_messages_used,
            "monthly_messages_limit": quota.monthly_messages_limit,
            "requests_per_minute": quota.requests_per_minute,
            "is_rate_limited": is_rate_limited,
            "retry_after_seconds": retry_after,
        }
