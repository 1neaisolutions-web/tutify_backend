"""
FastAPI dependencies for subscription domain.
"""
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domains.auth.dependencies import get_current_user
from app.domains.auth.models import User
from app.domains.subscriptions.services.subscription_service import SubscriptionService
from app.domains.subscriptions.services.feature_gate_service import FeatureGateService
from app.domains.subscriptions.services.quota_service import QuotaService
from app.domains.subscriptions.schemas import FeatureAccessResponse


def get_subscription_service(db: Session = Depends(get_db)) -> SubscriptionService:
    """Get subscription service instance."""
    return SubscriptionService(db)


def get_feature_gate_service(db: Session = Depends(get_db)) -> FeatureGateService:
    """Get feature gate service instance."""
    return FeatureGateService(db)


def get_quota_service(db: Session = Depends(get_db)) -> QuotaService:
    """Get quota service instance."""
    return QuotaService(db)


def require_feature(
    feature_key: str,
    feature_gate: FeatureGateService = Depends(get_feature_gate_service),
    current_user: User = Depends(get_current_user),
) -> FeatureAccessResponse:
    """Dependency to check feature access in routes."""
    access = feature_gate.check_feature_access(
        user_id=current_user.id,
        feature_key=feature_key,
    )

    if not access.has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "feature_not_available",
                "message": f"Feature '{feature_key}' is not available for your tier",
                "upgrade_required": access.upgrade_required,
                "required_tier": access.required_tier,
                "reason": access.reason,
            },
        )

    return access
