"""Super Admin API routes — all require super_admin + MFA when enabled."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.rate_limit import rate_limit_admin_write
from app.db.session import get_db
from app.domains.admin import schemas
from app.domains.admin.dependencies import require_super_admin_mfa
from app.domains.admin.services import (
    AdminAnalyticsService,
    AdminAuditService,
    AdminComplianceService,
    AdminDashboardService,
    AdminMemoryService,
    AdminOrgService,
    AdminSchoolService,
    AdminSubscriptionService,
    AdminUserService,
)
from app.domains.auth.models import User

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


# ─── Dashboard ────────────────────────────────────────────────────────────────

@router.get("/dashboard/overview", response_model=schemas.DashboardOverviewResponse)
def dashboard_overview(
    current_user: User = Depends(require_super_admin_mfa),
    db: Session = Depends(get_db),
):
    return AdminDashboardService(db).get_overview()


@router.get("/alerts", response_model=schemas.AdminAlertsResponse)
def admin_alerts(
    current_user: User = Depends(require_super_admin_mfa),
    db: Session = Depends(get_db),
):
    items = AdminDashboardService(db).get_alerts()
    return {"items": items, "total": len(items)}


# ─── Memory ───────────────────────────────────────────────────────────────────

@router.get("/memory/overview", response_model=schemas.MemoryOverviewResponse)
def memory_overview(
    current_user: User = Depends(require_super_admin_mfa),
    db: Session = Depends(get_db),
):
    return AdminMemoryService(db).get_platform_overview()


@router.get("/memory/users", response_model=schemas.MemoryUsersResponse)
def memory_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    org_id: Optional[UUID] = None,
    low_memory: bool = False,
    expiring_days: Optional[int] = None,
    search: Optional[str] = None,
    current_user: User = Depends(require_super_admin_mfa),
    db: Session = Depends(get_db),
):
    items, total = AdminMemoryService(db).list_user_balances(
        page=page, page_size=page_size, org_id=org_id,
        low_memory=low_memory, expiring_days=expiring_days, search=search,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/memory/users/{user_id}", response_model=schemas.MemoryUserDetailResponse)
def memory_user_detail(
    user_id: UUID,
    current_user: User = Depends(require_super_admin_mfa),
    db: Session = Depends(get_db),
):
    detail = AdminMemoryService(db).get_user_detail(user_id)
    if not detail:
        raise HTTPException(status_code=404, detail="User not found")
    return detail


@router.get("/memory/alerts", response_model=schemas.MemoryAlertsResponse)
def memory_alerts(
    current_user: User = Depends(require_super_admin_mfa),
    db: Session = Depends(get_db),
):
    items = AdminMemoryService(db).get_alerts()
    return {"items": items, "total": len(items)}


@router.post("/memory/users/{user_id}/grant")
@rate_limit_admin_write
def memory_grant(
    user_id: UUID,
    body: schemas.AmountReasonRequest,
    request: Request,
    current_user: User = Depends(require_super_admin_mfa),
    db: Session = Depends(get_db),
):
    try:
        return AdminMemoryService(db).grant(current_user.id, user_id, body.amount, body.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/memory/users/{user_id}/deduct")
@rate_limit_admin_write
def memory_deduct(
    user_id: UUID,
    body: schemas.AmountReasonRequest,
    request: Request,
    current_user: User = Depends(require_super_admin_mfa),
    db: Session = Depends(get_db),
):
    try:
        return AdminMemoryService(db).deduct(current_user.id, user_id, body.amount, body.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── Users ────────────────────────────────────────────────────────────────────

@router.get("/users", response_model=schemas.AdminUsersResponse)
def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    search: Optional[str] = None,
    status: Optional[str] = None,
    role: Optional[str] = None,
    org_id: Optional[UUID] = None,
    current_user: User = Depends(require_super_admin_mfa),
    db: Session = Depends(get_db),
):
    items, total = AdminUserService(db).list_users(
        page=page, page_size=page_size, search=search,
        status=status, role=role, org_id=org_id,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/users/{user_id}", response_model=schemas.AdminUserDetailResponse)
def get_user(
    user_id: UUID,
    current_user: User = Depends(require_super_admin_mfa),
    db: Session = Depends(get_db),
):
    detail = AdminUserService(db).get_user(user_id)
    if not detail:
        raise HTTPException(status_code=404, detail="User not found")
    return detail


@router.post("/users/{user_id}/suspend")
@rate_limit_admin_write
def suspend_user(
    user_id: UUID,
    body: schemas.ReasonRequest,
    request: Request,
    current_user: User = Depends(require_super_admin_mfa),
    db: Session = Depends(get_db),
):
    try:
        AdminUserService(db).suspend(current_user.id, user_id, body.reason)
        return {"status": "suspended"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/users/{user_id}/reactivate")
@rate_limit_admin_write
def reactivate_user(
    user_id: UUID,
    body: schemas.ReasonRequest,
    request: Request,
    current_user: User = Depends(require_super_admin_mfa),
    db: Session = Depends(get_db),
):
    try:
        AdminUserService(db).reactivate(current_user.id, user_id, body.reason)
        return {"status": "reactivated"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/users/{user_id}/force-password-reset")
@rate_limit_admin_write
def force_password_reset(
    user_id: UUID,
    body: schemas.ReasonRequest,
    request: Request,
    current_user: User = Depends(require_super_admin_mfa),
    db: Session = Depends(get_db),
):
    try:
        AdminUserService(db).force_password_reset(current_user.id, user_id, body.reason)
        return {"status": "reset_initiated"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── Organizations ────────────────────────────────────────────────────────────

@router.get("/organizations", response_model=schemas.AdminOrgsResponse)
def list_organizations(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    search: Optional[str] = None,
    current_user: User = Depends(require_super_admin_mfa),
    db: Session = Depends(get_db),
):
    items, total = AdminOrgService(db).list_orgs(page=page, page_size=page_size, search=search)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/organizations/{org_id}", response_model=schemas.AdminOrgDetailResponse)
def get_organization(
    org_id: UUID,
    current_user: User = Depends(require_super_admin_mfa),
    db: Session = Depends(get_db),
):
    detail = AdminOrgService(db).get_org(org_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Organization not found")
    return detail


@router.post("/organizations/{org_id}/suspend")
@rate_limit_admin_write
def suspend_organization(
    org_id: UUID,
    body: schemas.ReasonRequest,
    request: Request,
    current_user: User = Depends(require_super_admin_mfa),
    db: Session = Depends(get_db),
):
    try:
        AdminOrgService(db).suspend(current_user.id, org_id, body.reason)
        return {"status": "suspended"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/organizations/{org_id}/reactivate")
@rate_limit_admin_write
def reactivate_organization(
    org_id: UUID,
    body: schemas.ReasonRequest,
    request: Request,
    current_user: User = Depends(require_super_admin_mfa),
    db: Session = Depends(get_db),
):
    try:
        AdminOrgService(db).reactivate(current_user.id, org_id, body.reason)
        return {"status": "reactivated"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── Schools ──────────────────────────────────────────────────────────────────

@router.get("/institutions", response_model=schemas.AdminSchoolsResponse)
def list_institutions(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    search: Optional[str] = None,
    org_id: Optional[UUID] = None,
    current_user: User = Depends(require_super_admin_mfa),
    db: Session = Depends(get_db),
):
    items, total = AdminSchoolService(db).list_schools(
        page=page, page_size=page_size, search=search, org_id=org_id,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


# ─── Subscriptions ────────────────────────────────────────────────────────────

@router.get("/subscriptions", response_model=schemas.AdminSubscriptionsResponse)
def list_subscriptions(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    tier: Optional[str] = None,
    search: Optional[str] = None,
    current_user: User = Depends(require_super_admin_mfa),
    db: Session = Depends(get_db),
):
    items, total = AdminSubscriptionService(db).list_subscriptions(
        page=page, page_size=page_size, tier=tier, search=search,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


# ─── Audit ────────────────────────────────────────────────────────────────────

@router.get("/audit-logs", response_model=schemas.AuditLogsResponse)
def list_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    event_type: Optional[str] = None,
    actor_id: Optional[UUID] = None,
    search: Optional[str] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    current_user: User = Depends(require_super_admin_mfa),
    db: Session = Depends(get_db),
):
    items, total = AdminAuditService(db).list_logs(
        page=page, page_size=page_size, event_type=event_type,
        actor_id=actor_id, search=search, from_date=from_date, to_date=to_date,
    )
    return {
        "items": [
            {
                "id": i.id,
                "event_type": i.event_type.value if hasattr(i.event_type, "value") else str(i.event_type),
                "description": i.description,
                "actor_user_id": i.actor_user_id,
                "target_user_id": i.target_user_id,
                "tenant_id": i.tenant_id,
                "event_metadata": i.event_metadata,
                "ip_address": i.ip_address,
                "created_at": i.created_at,
            }
            for i in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


# ─── Compliance ─────────────────────────────────────────────────────────────────

@router.post("/compliance/export-requests", response_model=schemas.ComplianceExportRequestItem)
@rate_limit_admin_write
def create_compliance_request(
    body: schemas.ComplianceExportRequestCreate,
    request: Request,
    current_user: User = Depends(require_super_admin_mfa),
    db: Session = Depends(get_db),
):
    req = AdminComplianceService(db).create_request(current_user.id, body.model_dump())
    return req


@router.get("/compliance/export-requests", response_model=schemas.ComplianceExportRequestsResponse)
def list_compliance_requests(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    status: Optional[str] = None,
    current_user: User = Depends(require_super_admin_mfa),
    db: Session = Depends(get_db),
):
    items, total = AdminComplianceService(db).list_requests(page=page, page_size=page_size, status=status)
    return {
        "items": [
            {
                "id": i.id,
                "request_type": i.request_type,
                "status": i.status.value if hasattr(i.status, "value") else str(i.status),
                "reason": i.reason,
                "notes": i.notes,
                "requester_user_id": i.requester_user_id,
                "subject_user_id": i.subject_user_id,
                "organization_id": i.organization_id,
                "created_at": i.created_at,
                "updated_at": i.updated_at,
                "completed_at": i.completed_at,
            }
            for i in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


# ─── Analytics ────────────────────────────────────────────────────────────────

@router.get("/analytics/growth", response_model=schemas.GrowthAnalyticsResponse)
def analytics_growth(
    days: int = Query(30, ge=7, le=90),
    current_user: User = Depends(require_super_admin_mfa),
    db: Session = Depends(get_db),
):
    return AdminAnalyticsService(db).get_growth(days=days)


@router.get("/analytics/llm-cost", response_model=schemas.LlmCostAnalyticsResponse)
def analytics_llm_cost(
    days: int = Query(30, ge=7, le=90),
    current_user: User = Depends(require_super_admin_mfa),
    db: Session = Depends(get_db),
):
    return AdminAnalyticsService(db).get_llm_cost(days=days)
