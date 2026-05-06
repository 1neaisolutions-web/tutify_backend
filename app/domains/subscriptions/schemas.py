"""
Pydantic schemas for subscription domain.
"""
from typing import Optional, Dict, Any, List
from datetime import datetime
from uuid import UUID
from decimal import Decimal
from pydantic import BaseModel, Field, ConfigDict

from app.domains.subscriptions.enums import SubscriptionTier, SubscriptionStatus


# Base schemas
class SubscriptionTierResponse(BaseModel):
    """Subscription tier response."""

    tier_key: str
    tier_name: str
    tier_description: Optional[str] = None
    hierarchy_level: int
    price_monthly: Optional[Decimal] = None
    price_yearly: Optional[Decimal] = None
    currency: str = "USD"
    is_active: bool = True
    is_public: bool = True

    model_config = ConfigDict(from_attributes=True)


class FeatureAccessResponse(BaseModel):
    """Feature access check response."""

    has_access: bool
    reason: Optional[str] = None
    limit: Optional[int] = None
    limit_period: Optional[str] = None
    usage_count: Optional[int] = None
    remaining: Optional[int] = None
    upgrade_required: bool = False
    required_tier: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class SubscriptionFeatureResponse(BaseModel):
    """Feature definition response."""

    feature_key: str
    feature_name: str
    is_enabled: bool
    limit: Optional[int] = None
    limit_period: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


class SubscriptionResponse(BaseModel):
    """User subscription response."""

    tier: str
    status: str
    is_trial: bool = False
    is_manually_granted: bool = False
    current_period_end: Optional[datetime] = None
    trial_ends_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class UserFeaturesResponse(BaseModel):
    """All features available to user."""

    tier: str
    features: List[SubscriptionFeatureResponse]


class UpgradeTierRequest(BaseModel):
    """Request to upgrade user tier."""

    user_id: UUID
    tier: str = Field(..., description="Target tier (free, premium, enterprise)")
    reason: Optional[str] = None


class QuotaSummaryResponse(BaseModel):
    """Usage quota summary response."""

    daily_messages_used: int
    daily_messages_limit: int
    monthly_messages_used: int
    monthly_messages_limit: int
    requests_per_minute: int
    is_rate_limited: bool = False
    retry_after_seconds: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class UsageLogResponse(BaseModel):
    """Usage log entry response."""

    id: UUID
    action: str
    feature_key: Optional[str] = None
    tokens_used: Optional[int] = None
    cost_estimate: Optional[Decimal] = None
    model_used: Optional[str] = None
    provider_used: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── Credit system schemas ──────────────────────────────────────────────────────

class RedeemCodeRequest(BaseModel):
    code: str = Field(..., min_length=3, max_length=50, description="Access code string")


class RedeemCodeResponse(BaseModel):
    success: bool
    credits_added: int = 0
    balance: int = 0
    expires_at: Optional[datetime] = None
    auto_renew: bool = False
    error: Optional[str] = None
    error_code: Optional[str] = None


class CreditBalanceResponse(BaseModel):
    balance: int
    total_allocated: int
    total_spent: int
    expires_at: Optional[datetime] = None
    auto_renew: bool = False
    subscription_started_at: Optional[datetime] = None
    has_active_credits: bool

    model_config = ConfigDict(from_attributes=True)


class CreditTransactionResponse(BaseModel):
    id: UUID
    type: str
    amount: int
    balance_after: int
    feature_key: Optional[str] = None
    description: Optional[str] = None
    model_used: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CreditTransactionListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[CreditTransactionResponse]


class UsageBreakdownItem(BaseModel):
    feature_key: str
    display_name: str
    module_name: str
    credits: int
    call_count: int
    pct_of_total: float


class UsageBreakdownResponse(BaseModel):
    period_days: int
    total_credits: int
    breakdown: List[UsageBreakdownItem]


class UsageSummaryResponse(BaseModel):
    balance: int
    total_allocated: int
    total_spent: int
    expires_at: Optional[str] = None
    auto_renew: bool = False
    subscription_started_at: Optional[str] = None
    monthly_spent: int
    top_module: Optional[str] = None


class CreateAccessCodeRequest(BaseModel):
    code: str = Field(..., min_length=3, max_length=50)
    code_type: str = Field(..., description="'beta' or 'staff'")
    credit_allocation: int = Field(..., gt=0)
    validity_days: int = Field(30, gt=0)
    max_uses: Optional[int] = None
    auto_renew: bool = False
    auto_renew_threshold_pct: int = 20
    description: Optional[str] = None
