"""
Subscription domain enumerations.
"""
import enum
from typing import Dict


class SubscriptionTier(str, enum.Enum):
    """Subscription tier levels with hierarchy."""

    FREE = "free"
    PREMIUM = "premium"
    ENTERPRISE = "enterprise"

    @classmethod
    def get_hierarchy(cls) -> Dict[str, int]:
        """Get tier hierarchy for comparison."""
        return {
            cls.FREE: 0,
            cls.PREMIUM: 1,
            cls.ENTERPRISE: 2,
        }

    @classmethod
    def is_upgrade(cls, from_tier: str, to_tier: str) -> bool:
        """Check if tier change is an upgrade."""
        hierarchy = cls.get_hierarchy()
        return hierarchy.get(to_tier, 0) > hierarchy.get(from_tier, 0)

    @classmethod
    def get_all_tiers(cls) -> list[str]:
        """Get all tier names."""
        return [tier.value for tier in cls]


class SubscriptionStatus(str, enum.Enum):
    """Subscription status enumeration."""

    ACTIVE = "active"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    TRIAL = "trial"
    PAST_DUE = "past_due"


class FeatureCategory(str, enum.Enum):
    """Feature category enumeration."""

    CORE = "core"
    AI = "ai"
    ANALYTICS = "analytics"
    COLLABORATION = "collaboration"
    INTEGRATION = "integration"
    SUPPORT = "support"
