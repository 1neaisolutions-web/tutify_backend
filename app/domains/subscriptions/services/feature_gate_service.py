"""
Feature gate service for checking feature access based on subscription tier.
"""
from typing import Dict, Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domains.subscriptions.services.subscription_service import SubscriptionService
from app.domains.subscriptions.models import SubscriptionTierFeature
from app.domains.subscriptions.schemas import FeatureAccessResponse

logger = get_logger(__name__)


class FeatureGateService:
    """Service for checking feature access based on subscription tier."""

    def __init__(self, db: Session):
        self.db = db
        self.subscription_service = SubscriptionService(db)

    def check_feature_access(
        self,
        user_id: UUID,
        feature_key: str,
    ) -> FeatureAccessResponse:
        """Check if user has access to a feature."""
        # Get user's tier
        tier = self.subscription_service.get_user_tier(user_id)

        # Get feature config for this tier
        feature_config = self.db.query(SubscriptionTierFeature).filter(
            SubscriptionTierFeature.tier == tier.value,
            SubscriptionTierFeature.feature_key == feature_key,
        ).first()

        if not feature_config:
            return FeatureAccessResponse(
                has_access=False,
                reason="feature_not_found",
                upgrade_required=True,
            )

        if not feature_config.is_enabled:
            return FeatureAccessResponse(
                has_access=False,
                reason="feature_disabled",
                upgrade_required=True,
                required_tier="premium",
            )

        # Check limits if applicable
        limit_info = None
        if feature_config.limit_value is not None:
            limit_info = {
                "limit": feature_config.limit_value,
                "period": feature_config.limit_period,
            }

        return FeatureAccessResponse(
            has_access=True,
            limit=feature_config.limit_value,
            limit_period=feature_config.limit_period,
            metadata=dict(feature_config.feature_metadata) if feature_config.feature_metadata else {},
        )

    def get_user_features(self, user_id: UUID):
        """Get all features available to user."""
        from app.domains.subscriptions.schemas import (
            SubscriptionFeatureResponse,
            UserFeaturesResponse,
        )
        
        tier = self.subscription_service.get_user_tier(user_id)

        features = self.db.query(SubscriptionTierFeature).filter(
            SubscriptionTierFeature.tier == tier.value,
            SubscriptionTierFeature.is_enabled == True,
        ).all()

        return UserFeaturesResponse(
            tier=tier.value,
            features=[
                SubscriptionFeatureResponse(
                    feature_key=feature.feature_key,
                    feature_name=feature.feature_name,
                    is_enabled=feature.is_enabled,
                    limit=feature.limit_value,
                    limit_period=feature.limit_period,
                    metadata=dict(feature.feature_metadata) if feature.feature_metadata else None,
                )
                for feature in features
            ],
        )
