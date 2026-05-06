"""
Subscription API routes.
"""
from typing import Optional
from uuid import UUID
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.logging import get_logger
from app.domains.auth.dependencies import get_current_user, require_role
from app.domains.auth.models import User, RoleName
from app.domains.subscriptions.services.subscription_service import SubscriptionService
from app.domains.subscriptions.services.feature_gate_service import FeatureGateService
from app.domains.subscriptions.services.quota_service import QuotaService
from app.domains.subscriptions.services.credit_service import CreditService
from app.domains.subscriptions.code_normalization import normalize_access_code
from app.domains.subscriptions.services.code_redemption_service import CodeRedemptionService
from app.domains.subscriptions.enums import SubscriptionTier
from app.domains.subscriptions.models import AccessCode, UserCreditTransaction
from app.domains.subscriptions.schemas import (
    SubscriptionResponse,
    FeatureAccessResponse,
    UserFeaturesResponse,
    UpgradeTierRequest,
    QuotaSummaryResponse,
    RedeemCodeRequest,
    RedeemCodeResponse,
    CreditBalanceResponse,
    CreditTransactionResponse,
    CreditTransactionListResponse,
    UsageBreakdownResponse,
    UsageBreakdownItem,
    UsageSummaryResponse,
    CreateAccessCodeRequest,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/subscriptions", tags=["subscriptions"])


# ── Existing endpoints ─────────────────────────────────────────────────────────

@router.get("/me", response_model=SubscriptionResponse)
def get_my_subscription(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current user's subscription."""
    service = SubscriptionService(db)
    subscription = service.get_user_subscription(current_user.id)
    return SubscriptionResponse(
        tier=subscription.tier,
        status=subscription.status,
        is_trial=subscription.is_trial,
        is_manually_granted=subscription.is_manually_granted,
        current_period_end=subscription.current_period_end,
        trial_ends_at=subscription.trial_ends_at,
    )


@router.get("/me/features", response_model=UserFeaturesResponse)
def get_my_features(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all features available to current user."""
    service = FeatureGateService(db)
    return service.get_user_features(current_user.id)


@router.get("/me/features/{feature_key}", response_model=FeatureAccessResponse)
def check_feature_access(
    feature_key: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Check if user has access to a specific feature."""
    service = FeatureGateService(db)
    result = service.check_feature_access(current_user.id, feature_key)
    if not result.has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "feature_not_available",
                "message": result.reason or "Feature not available",
                "upgrade_required": result.upgrade_required,
                "required_tier": result.required_tier,
            },
        )
    return result


@router.get("/me/quota", response_model=QuotaSummaryResponse)
def get_my_quota(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current user's quota summary."""
    service = QuotaService(db)
    summary = service.get_quota_summary(current_user.id)
    return QuotaSummaryResponse(**summary)


# ── Credit balance & history ───────────────────────────────────────────────────

@router.get("/me/balance", response_model=CreditBalanceResponse)
def get_my_balance(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current user's credit balance and plan info."""
    service = CreditService(db)
    balance = service.get_or_create_balance(current_user.id)
    now = datetime.now(timezone.utc)
    has_active = (
        balance.balance > 0
        and (balance.expires_at is None or balance.expires_at > now or balance.auto_renew)
    )
    return CreditBalanceResponse(
        balance=balance.balance,
        total_allocated=balance.total_allocated,
        total_spent=balance.total_spent,
        expires_at=balance.expires_at,
        auto_renew=balance.auto_renew,
        subscription_started_at=balance.subscription_started_at,
        has_active_credits=has_active,
    )


@router.get("/me/transactions", response_model=CreditTransactionListResponse)
def get_my_transactions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    feature_key: Optional[str] = Query(None),
):
    """Get paginated credit transaction history."""
    service = CreditService(db)
    result = service.get_transaction_history(
        user_id=current_user.id,
        page=page,
        page_size=page_size,
        feature_key=feature_key,
    )
    items = [
        CreditTransactionResponse(
            id=t.id,
            type=t.type,
            amount=t.amount,
            balance_after=t.balance_after,
            feature_key=t.feature_key,
            description=t.description,
            model_used=t.model_used,
            input_tokens=t.input_tokens,
            output_tokens=t.output_tokens,
            created_at=t.created_at,
        )
        for t in result["items"]
    ]
    return CreditTransactionListResponse(
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
        items=items,
    )


@router.get("/me/usage-breakdown", response_model=UsageBreakdownResponse)
def get_usage_breakdown(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    days: int = Query(30, ge=1, le=365),
):
    """Get credit usage breakdown by feature for the last N days."""
    service = CreditService(db)
    breakdown = service.get_usage_breakdown(current_user.id, days=days)
    total = sum(b["credits"] for b in breakdown)
    return UsageBreakdownResponse(
        period_days=days,
        total_credits=total,
        breakdown=[UsageBreakdownItem(**b) for b in breakdown],
    )


@router.get("/me/usage-summary", response_model=UsageSummaryResponse)
def get_usage_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get high-level usage summary for the dashboard."""
    service = CreditService(db)
    summary = service.get_usage_summary(current_user.id)
    return UsageSummaryResponse(**summary)


# ── Code redemption ────────────────────────────────────────────────────────────

@router.post("/redeem-code", response_model=RedeemCodeResponse)
def redeem_access_code(
    request: RedeemCodeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Activate an access code to receive credits."""
    service = CodeRedemptionService(db)
    result = service.redeem_code(user_id=current_user.id, code_str=request.code)
    return RedeemCodeResponse(
        success=result.success,
        credits_added=result.credits_added,
        balance=result.balance,
        expires_at=result.expires_at,
        auto_renew=result.auto_renew,
        error=result.error,
        error_code=result.error_code,
    )


# ── Admin endpoints ────────────────────────────────────────────────────────────

class _ToggleCodeBody(BaseModel):
    is_active: bool


@router.post("/admin/codes", status_code=status.HTTP_201_CREATED)
def create_access_code(
    request: CreateAccessCodeRequest,
    current_user: User = Depends(require_role("super_admin")),
    db: Session = Depends(get_db),
):
    """Create a new access code (super admin only)."""
    canonical = normalize_access_code(request.code)
    if len(canonical) < 3:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Access code is too short")

    for row in db.query(AccessCode).all():
        if normalize_access_code(row.code) == canonical:
            raise HTTPException(status_code=409, detail="Code already exists")

    # auto_renew is determined by code type: staff codes always auto-renew, beta codes never do
    auto_renew = request.code_type == "staff"

    code = AccessCode(
        code=canonical,
        code_type=request.code_type,
        credit_allocation=request.credit_allocation,
        validity_days=request.validity_days,
        max_uses=None if request.code_type == "staff" else request.max_uses,
        is_active=True,
        auto_renew=auto_renew,
        auto_renew_threshold_pct=request.auto_renew_threshold_pct,
        description=request.description,
        created_by=current_user.id,
    )
    db.add(code)
    db.commit()
    db.refresh(code)

    return {
        "id": str(code.id),
        "code": code.code,
        "code_type": code.code_type,
        "credit_allocation": code.credit_allocation,
        "validity_days": code.validity_days,
        "max_uses": code.max_uses,
        "times_used": code.times_used,
        "is_active": code.is_active,
        "auto_renew": code.auto_renew,
        "created_at": code.created_at.isoformat(),
    }


@router.get("/admin/codes")
def list_access_codes(
    current_user: User = Depends(require_role("super_admin")),
    db: Session = Depends(get_db),
):
    """List all access codes (super admin only)."""
    codes = db.query(AccessCode).order_by(AccessCode.created_at.desc()).all()
    return [
        {
            "id": str(c.id),
            "code": c.code,
            "code_type": c.code_type,
            "credit_allocation": c.credit_allocation,
            "validity_days": c.validity_days,
            "max_uses": c.max_uses,
            "times_used": c.times_used,
            "is_active": c.is_active,
            "auto_renew": c.auto_renew,
            "description": c.description,
            "created_at": c.created_at.isoformat(),
        }
        for c in codes
    ]


@router.patch("/admin/codes/{code_id}")
def toggle_access_code(
    code_id: UUID,
    body: _ToggleCodeBody,
    current_user: User = Depends(require_role("super_admin")),
    db: Session = Depends(get_db),
):
    """Activate or deactivate an access code (super admin only)."""
    code = db.query(AccessCode).filter(AccessCode.id == code_id).first()
    if not code:
        raise HTTPException(status_code=404, detail="Code not found")
    code.is_active = body.is_active
    db.commit()
    return {"id": str(code.id), "code": code.code, "is_active": code.is_active}


@router.post("/admin/upgrade", response_model=SubscriptionResponse)
def upgrade_user_tier(
    request: UpgradeTierRequest,
    current_user: User = Depends(require_role("super_admin")),
    db: Session = Depends(get_db),
):
    """Upgrade user tier (admin only)."""
    service = SubscriptionService(db)
    try:
        new_tier = SubscriptionTier(request.tier)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid tier: {request.tier}")

    subscription = service.upgrade_user_tier(
        user_id=request.user_id,
        new_tier=new_tier,
        granted_by_user_id=current_user.id,
        reason=request.reason or "Admin upgrade",
        is_manual=True,
    )
    return SubscriptionResponse(
        tier=subscription.tier,
        status=subscription.status,
        is_trial=subscription.is_trial,
        is_manually_granted=subscription.is_manually_granted,
        current_period_end=subscription.current_period_end,
        trial_ends_at=subscription.trial_ends_at,
    )
