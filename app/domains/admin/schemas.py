"""Pydantic schemas for the admin domain."""
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ─── Shared ───────────────────────────────────────────────────────────────────

class PaginatedResponse(BaseModel):
    total: int
    page: int
    page_size: int


class ReasonRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)


class AmountReasonRequest(ReasonRequest):
    amount: int = Field(..., gt=0)


# ─── Dashboard ────────────────────────────────────────────────────────────────

class DashboardOverviewResponse(BaseModel):
    total_users: int
    users_by_role: Dict[str, int]
    dau: int
    wau: int
    mau: int
    total_organizations: int
    total_schools: int
    tier_breakdown: Dict[str, int]
    memory_total_balance: int
    memory_total_allocated: int
    memory_total_spent: int
    alert_count: int
    health_status: str
    queue_pending: int
    queue_in_progress: int
    error_rate_24h: float


class AdminAlertItem(BaseModel):
    id: str
    severity: str
    title: str
    message: str
    created_at: datetime
    link: Optional[str] = None


class AdminAlertsResponse(BaseModel):
    items: List[AdminAlertItem]
    total: int


# ─── Memory ───────────────────────────────────────────────────────────────────

class MemoryOverviewResponse(BaseModel):
    total_balance: int
    total_allocated: int
    total_spent: int
    active_users_with_balance: int
    daily_burn_rate: float
    monthly_burn_rate: float
    estimated_runway_days: Optional[float]


class MemoryUserItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    email: str
    full_name: Optional[str]
    tenant_id: UUID
    tenant_name: Optional[str]
    balance: int
    total_allocated: int
    total_spent: int
    expires_at: Optional[datetime]
    balance_pct: Optional[float]


class MemoryUsersResponse(PaginatedResponse):
    items: List[MemoryUserItem]


class CreditTransactionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: str
    amount: int
    balance_after: int
    feature_key: Optional[str]
    description: Optional[str]
    model_used: Optional[str]
    usd_cost: Optional[Decimal]
    created_at: datetime


class MemoryUserDetailResponse(BaseModel):
    user: MemoryUserItem
    recent_transactions: List[CreditTransactionItem]


class MemoryAlertItem(BaseModel):
    alert_type: str
    severity: str
    user_id: UUID
    email: str
    message: str
    balance: Optional[int] = None
    expires_at: Optional[datetime] = None


class MemoryAlertsResponse(BaseModel):
    items: List[MemoryAlertItem]
    total: int


# ─── Users ────────────────────────────────────────────────────────────────────

class AdminUserItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    first_name: str
    last_name: str
    status: str
    tenant_id: UUID
    tenant_name: Optional[str]
    roles: List[str]
    last_login_at: Optional[datetime]
    created_at: datetime
    balance: Optional[int] = None
    subscription_tier: Optional[str] = None


class AdminUsersResponse(PaginatedResponse):
    items: List[AdminUserItem]


class AdminUserDetailResponse(BaseModel):
    user: AdminUserItem
    memory: Optional[MemoryUserItem] = None
    subscription_tier: Optional[str] = None
    subscription_status: Optional[str] = None


# ─── Organizations ────────────────────────────────────────────────────────────

class AdminOrgItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    type: str
    is_active: bool
    user_count: int
    school_count: int
    memory_total_balance: int
    created_at: datetime


class AdminOrgsResponse(PaginatedResponse):
    items: List[AdminOrgItem]


class AdminOrgDetailResponse(BaseModel):
    organization: AdminOrgItem
    schools: List[Dict[str, Any]]


# ─── Schools ──────────────────────────────────────────────────────────────────

class AdminSchoolItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    institution_type: Optional[str]
    tenant_id: UUID
    tenant_name: Optional[str]
    org_tenant_id: Optional[UUID]
    org_name: Optional[str]
    is_active: bool
    user_count: int
    created_at: Optional[datetime]


class AdminSchoolsResponse(PaginatedResponse):
    items: List[AdminSchoolItem]


# ─── Subscriptions ────────────────────────────────────────────────────────────

class AdminSubscriptionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    email: str
    full_name: Optional[str]
    tier: str
    status: str
    current_period_end: Optional[datetime]
    is_trial: bool
    is_manually_granted: bool


class AdminSubscriptionsResponse(PaginatedResponse):
    items: List[AdminSubscriptionItem]


# ─── Audit ────────────────────────────────────────────────────────────────────

class AuditLogItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_type: str
    description: str
    actor_user_id: Optional[UUID]
    target_user_id: Optional[UUID]
    tenant_id: Optional[UUID]
    event_metadata: Optional[Dict[str, Any]]
    ip_address: Optional[str]
    created_at: datetime


class AuditLogsResponse(PaginatedResponse):
    items: List[AuditLogItem]


# ─── Compliance ─────────────────────────────────────────────────────────────────

class ComplianceExportRequestCreate(BaseModel):
    subject_user_id: Optional[UUID] = None
    organization_id: Optional[UUID] = None
    request_type: str = "data_export"
    reason: str = Field(..., min_length=3, max_length=500)
    notes: Optional[str] = None


class ComplianceExportRequestItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    request_type: str
    status: str
    reason: str
    notes: Optional[str]
    requester_user_id: Optional[UUID]
    subject_user_id: Optional[UUID]
    organization_id: Optional[UUID]
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]


class ComplianceExportRequestsResponse(PaginatedResponse):
    items: List[ComplianceExportRequestItem]


# ─── Analytics ────────────────────────────────────────────────────────────────

class GrowthDataPoint(BaseModel):
    date: str
    new_users: int
    active_users: int


class GrowthAnalyticsResponse(BaseModel):
    data: List[GrowthDataPoint]
    total_users: int
    growth_rate_30d: float


class LlmCostDataPoint(BaseModel):
    date: str
    model: Optional[str]
    total_usd: float
    total_credits: int
    transaction_count: int


class LlmCostAnalyticsResponse(BaseModel):
    data: List[LlmCostDataPoint]
    total_usd_30d: float
    by_model: Dict[str, float]
