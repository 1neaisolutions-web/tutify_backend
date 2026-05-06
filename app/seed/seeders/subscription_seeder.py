"""
Seeder for subscription tiers and features.
"""
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domains.subscriptions.models import (
    SubscriptionTierModel,
    SubscriptionTierFeature,
)
from app.domains.subscriptions.enums import SubscriptionTier

logger = get_logger(__name__)


def seed_subscription_tiers(db: Session, force: bool = False) -> dict:
    """Seed subscription tiers and features."""
    tiers_created = 0
    tiers_skipped = 0
    features_created = 0
    features_skipped = 0

    # Define tiers
    tier_data = [
        {
            "tier_key": SubscriptionTier.FREE.value,
            "tier_name": "Free",
            "tier_description": "Free tier with basic features",
            "hierarchy_level": 0,
            "display_order": 1,
            "price_monthly": None,
            "price_yearly": None,
            "currency": "USD",
            "is_active": True,
            "is_public": True,
            "features": [
                {"feature_key": "chat_messages", "feature_name": "Chat Messages", "is_enabled": True, "limit_value": 20, "limit_period": "daily"},
                {"feature_key": "general_chatbot", "feature_name": "General Teaching Assistant", "is_enabled": True, "limit_value": None, "limit_period": None},
                {"feature_key": "web_search", "feature_name": "Web Search", "is_enabled": False, "limit_value": None, "limit_period": None},
                {"feature_key": "audio_transcription", "feature_name": "Audio Transcription", "is_enabled": False, "limit_value": None, "limit_period": None},
                {"feature_key": "file_attachments", "feature_name": "File Attachments", "is_enabled": False, "limit_value": None, "limit_period": None},
                {"feature_key": "premium_chatbots", "feature_name": "Premium Chatbots", "is_enabled": False, "limit_value": None, "limit_period": None},
            ],
        },
        {
            "tier_key": SubscriptionTier.PREMIUM.value,
            "tier_name": "Premium",
            "tier_description": "Premium tier with advanced features",
            "hierarchy_level": 1,
            "display_order": 2,
            "price_monthly": 19.99,
            "price_yearly": 199.99,
            "currency": "USD",
            "is_active": True,
            "is_public": True,
            "features": [
                {"feature_key": "chat_messages", "feature_name": "Chat Messages", "is_enabled": True, "limit_value": 500, "limit_period": "daily"},
                {"feature_key": "general_chatbot", "feature_name": "General Teaching Assistant", "is_enabled": True, "limit_value": None, "limit_period": None},
                {"feature_key": "web_search", "feature_name": "Web Search", "is_enabled": True, "limit_value": None, "limit_period": None},
                {"feature_key": "audio_transcription", "feature_name": "Audio Transcription", "is_enabled": True, "limit_value": 100, "limit_period": "daily"},
                {"feature_key": "file_attachments", "feature_name": "File Attachments", "is_enabled": True, "limit_value": 50, "limit_period": "daily"},
                {"feature_key": "premium_chatbots", "feature_name": "Premium Chatbots", "is_enabled": True, "limit_value": None, "limit_period": None},
            ],
        },
        {
            "tier_key": SubscriptionTier.ENTERPRISE.value,
            "tier_name": "Enterprise",
            "tier_description": "Enterprise tier with unlimited features",
            "hierarchy_level": 2,
            "display_order": 3,
            "price_monthly": None,
            "price_yearly": None,
            "currency": "USD",
            "is_active": True,
            "is_public": False,  # Not public, requires contact
            "features": [
                {"feature_key": "chat_messages", "feature_name": "Chat Messages", "is_enabled": True, "limit_value": None, "limit_period": None},
                {"feature_key": "general_chatbot", "feature_name": "General Teaching Assistant", "is_enabled": True, "limit_value": None, "limit_period": None},
                {"feature_key": "web_search", "feature_name": "Web Search", "is_enabled": True, "limit_value": None, "limit_period": None},
                {"feature_key": "audio_transcription", "feature_name": "Audio Transcription", "is_enabled": True, "limit_value": None, "limit_period": None},
                {"feature_key": "file_attachments", "feature_name": "File Attachments", "is_enabled": True, "limit_value": None, "limit_period": None},
                {"feature_key": "premium_chatbots", "feature_name": "Premium Chatbots", "is_enabled": True, "limit_value": None, "limit_period": None},
            ],
        },
    ]

    for tier_info in tier_data:
        tier_key = tier_info["tier_key"]
        
        # Check if tier exists
        existing_tier = db.query(SubscriptionTierModel).filter(
            SubscriptionTierModel.tier_key == tier_key
        ).first()

        if existing_tier and not force:
            logger.info(f"Tier '{tier_key}' already exists, skipping")
            tiers_skipped += 1
            tier_obj = existing_tier
        else:
            if existing_tier and force:
                # Delete existing features first
                db.query(SubscriptionTierFeature).filter(
                    SubscriptionTierFeature.tier == tier_key
                ).delete()
                db.delete(existing_tier)
                db.flush()

            # Create tier
            tier_obj = SubscriptionTierModel(
                tier_key=tier_key,
                tier_name=tier_info["tier_name"],
                tier_description=tier_info["tier_description"],
                hierarchy_level=tier_info["hierarchy_level"],
                display_order=tier_info["display_order"],
                price_monthly=tier_info["price_monthly"],
                price_yearly=tier_info["price_yearly"],
                currency=tier_info["currency"],
                is_active=tier_info["is_active"],
                is_public=tier_info["is_public"],
            )
            db.add(tier_obj)
            db.flush()
            tiers_created += 1
            logger.info(f"Created tier: {tier_key}")

        # Create features
        for feature_info in tier_info["features"]:
            existing_feature = db.query(SubscriptionTierFeature).filter(
                SubscriptionTierFeature.tier == tier_key,
                SubscriptionTierFeature.feature_key == feature_info["feature_key"],
            ).first()

            if existing_feature and not force:
                features_skipped += 1
                continue

            if existing_feature and force:
                db.delete(existing_feature)
                db.flush()

            feature = SubscriptionTierFeature(
                tier=tier_key,
                feature_key=feature_info["feature_key"],
                feature_name=feature_info["feature_name"],
                is_enabled=feature_info["is_enabled"],
                limit_value=feature_info.get("limit_value"),
                limit_period=feature_info.get("limit_period"),
            )
            db.add(feature)
            features_created += 1

    db.commit()
    logger.info(f"Subscription seeding complete: {tiers_created} tiers created, {tiers_skipped} skipped, {features_created} features created")

    return {
        "tiers_created": tiers_created,
        "tiers_skipped": tiers_skipped,
        "features_created": features_created,
        "features_skipped": features_skipped,
    }
