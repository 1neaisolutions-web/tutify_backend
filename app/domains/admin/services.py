"""Admin domain business logic."""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import desc, func, or_
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domains.admin.models import ComplianceExportRequest, ComplianceExportStatus
from app.domains.auth.models import (
    AuditEventType,
    AuditLog,
    Role,
    RoleName,
    Tenant,
    TenantType,
    User,
    UserRole,
    UserStatus,
)
from app.domains.auth.services import AuditService
from app.domains.content_factory.services.content_factory_service import ContentFactoryService
from app.domains.subscriptions.models import UserCreditTransaction, UserSubscription, UserTokenBalance
from app.domains.subscriptions.services.credit_service import CreditService

logger = get_logger(__name__)


def _log_admin_action(
    db: Session,
    actor_id: UUID,
    description: str,
    target_user_id: Optional[UUID] = None,
    tenant_id: Optional[UUID] = None,
    target_type: str = "user",
    before: Optional[dict] = None,
    after: Optional[dict] = None,
    reason: Optional[str] = None,
) -> None:
    metadata: Dict[str, Any] = {}
    if reason:
        metadata["reason"] = reason
    if before is not None:
        metadata["before"] = before
    if after is not None:
        metadata["after"] = after
    AuditService.log_event(
        db,
        AuditEventType.USER_UPDATED,
        description,
        actor_user_id=actor_id,
        tenant_id=tenant_id,
        target_user_id=target_user_id,
        target_type=target_type,
        event_metadata=metadata or None,
    )


class AdminMemoryService:
    """Platform-wide memory (credit) management."""

    def __init__(self, db: Session):
        self.db = db
        self.credit = CreditService(db)

    def get_platform_overview(self) -> dict:
        row = self.db.query(
            func.coalesce(func.sum(UserTokenBalance.balance), 0),
            func.coalesce(func.sum(UserTokenBalance.total_allocated), 0),
            func.coalesce(func.sum(UserTokenBalance.total_spent), 0),
            func.count(UserTokenBalance.id),
        ).first()

        total_balance = int(row[0] or 0)
        total_allocated = int(row[1] or 0)
        total_spent = int(row[2] or 0)
        active_users = int(row[3] or 0)

        since_7d = datetime.now(timezone.utc) - timedelta(days=7)
        since_30d = datetime.now(timezone.utc) - timedelta(days=30)

        spent_7d = (
            self.db.query(func.coalesce(func.sum(func.abs(UserCreditTransaction.amount)), 0))
            .filter(
                UserCreditTransaction.type == "debit",
                UserCreditTransaction.created_at >= since_7d,
            )
            .scalar()
            or 0
        )
        spent_30d = (
            self.db.query(func.coalesce(func.sum(func.abs(UserCreditTransaction.amount)), 0))
            .filter(
                UserCreditTransaction.type == "debit",
                UserCreditTransaction.created_at >= since_30d,
            )
            .scalar()
            or 0
        )

        daily_burn = spent_7d / 7.0
        monthly_burn = spent_30d
        runway = (total_balance / daily_burn) if daily_burn > 0 else None

        return {
            "total_balance": total_balance,
            "total_allocated": total_allocated,
            "total_spent": total_spent,
            "active_users_with_balance": active_users,
            "daily_burn_rate": round(daily_burn, 2),
            "monthly_burn_rate": float(monthly_burn),
            "estimated_runway_days": round(runway, 1) if runway else None,
        }

    def list_user_balances(
        self,
        page: int = 1,
        page_size: int = 25,
        org_id: Optional[UUID] = None,
        low_memory: bool = False,
        expiring_days: Optional[int] = None,
        search: Optional[str] = None,
    ) -> Tuple[List[dict], int]:
        query = (
            self.db.query(UserTokenBalance, User, Tenant)
            .join(User, UserTokenBalance.user_id == User.id)
            .join(Tenant, User.tenant_id == Tenant.id)
        )

        if org_id:
            query = query.filter(
                or_(
                    Tenant.id == org_id,
                    Tenant.parent_tenant_id == org_id,
                )
            )
        if low_memory:
            query = query.filter(
                UserTokenBalance.total_allocated > 0,
                UserTokenBalance.balance * 100 / UserTokenBalance.total_allocated < 20,
            )
        if expiring_days:
            cutoff = datetime.now(timezone.utc) + timedelta(days=expiring_days)
            query = query.filter(
                UserTokenBalance.expires_at.isnot(None),
                UserTokenBalance.expires_at <= cutoff,
                UserTokenBalance.expires_at >= datetime.now(timezone.utc),
            )
        if search:
            term = f"%{search.lower()}%"
            query = query.filter(
                or_(
                    func.lower(User.email).like(term),
                    func.lower(User.first_name).like(term),
                    func.lower(User.last_name).like(term),
                )
            )

        total = query.count()
        rows = (
            query.order_by(desc(UserTokenBalance.balance))
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        items = []
        for bal, user, tenant in rows:
            pct = None
            if bal.total_allocated and bal.total_allocated > 0:
                pct = round(bal.balance * 100 / bal.total_allocated, 1)
            items.append({
                "user_id": user.id,
                "email": user.email,
                "full_name": user.full_name or f"{user.first_name} {user.last_name}",
                "tenant_id": user.tenant_id,
                "tenant_name": tenant.name,
                "balance": bal.balance,
                "total_allocated": bal.total_allocated,
                "total_spent": bal.total_spent,
                "expires_at": bal.expires_at,
                "balance_pct": pct,
            })
        return items, total

    def get_user_detail(self, user_id: UUID) -> Optional[dict]:
        row = (
            self.db.query(UserTokenBalance, User, Tenant)
            .join(User, UserTokenBalance.user_id == User.id)
            .join(Tenant, User.tenant_id == Tenant.id)
            .filter(UserTokenBalance.user_id == user_id)
            .first()
        )
        if not row:
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                return None
            tenant = self.db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
            bal = self.credit.get_or_create_balance(user_id)
            user_item = {
                "user_id": user.id,
                "email": user.email,
                "full_name": user.full_name or f"{user.first_name} {user.last_name}",
                "tenant_id": user.tenant_id,
                "tenant_name": tenant.name if tenant else None,
                "balance": bal.balance,
                "total_allocated": bal.total_allocated,
                "total_spent": bal.total_spent,
                "expires_at": bal.expires_at,
                "balance_pct": None,
            }
        else:
            bal, user, tenant = row
            pct = None
            if bal.total_allocated and bal.total_allocated > 0:
                pct = round(bal.balance * 100 / bal.total_allocated, 1)
            user_item = {
                "user_id": user.id,
                "email": user.email,
                "full_name": user.full_name or f"{user.first_name} {user.last_name}",
                "tenant_id": user.tenant_id,
                "tenant_name": tenant.name,
                "balance": bal.balance,
                "total_allocated": bal.total_allocated,
                "total_spent": bal.total_spent,
                "expires_at": bal.expires_at,
                "balance_pct": pct,
            }

        history = self.credit.get_transaction_history(user_id, page=1, page_size=20)
        return {"user": user_item, "recent_transactions": history["items"]}

    def get_alerts(self) -> List[dict]:
        alerts: List[dict] = []
        now = datetime.now(timezone.utc)

        low_rows = (
            self.db.query(UserTokenBalance, User)
            .join(User, UserTokenBalance.user_id == User.id)
            .filter(
                UserTokenBalance.total_allocated > 0,
                UserTokenBalance.balance * 100 / UserTokenBalance.total_allocated < 20,
            )
            .limit(50)
            .all()
        )
        for bal, user in low_rows:
            alerts.append({
                "alert_type": "low_balance",
                "severity": "warning",
                "user_id": user.id,
                "email": user.email,
                "message": f"Balance at {round(bal.balance * 100 / bal.total_allocated, 1)}% of allocation",
                "balance": bal.balance,
            })

        for days, severity in [(7, "critical"), (30, "warning")]:
            cutoff = now + timedelta(days=days)
            exp_rows = (
                self.db.query(UserTokenBalance, User)
                .join(User, UserTokenBalance.user_id == User.id)
                .filter(
                    UserTokenBalance.expires_at.isnot(None),
                    UserTokenBalance.expires_at <= cutoff,
                    UserTokenBalance.expires_at >= now,
                )
                .limit(50)
                .all()
            )
            for bal, user in exp_rows:
                alerts.append({
                    "alert_type": f"expiring_{days}d",
                    "severity": severity,
                    "user_id": user.id,
                    "email": user.email,
                    "message": f"Credits expire within {days} days",
                    "balance": bal.balance,
                    "expires_at": bal.expires_at,
                })

        return alerts

    def grant(self, actor_id: UUID, user_id: UUID, amount: int, reason: str) -> dict:
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError("User not found")
        before_bal = self.credit.get_balance(user_id)
        before = {"balance": before_bal.balance if before_bal else 0}
        balance = self.credit.top_up(
            user_id,
            amount,
            expires_at=None,
            source_description=f"Admin grant: {reason}",
        )
        after = {"balance": balance.balance}
        _log_admin_action(
            self.db, actor_id, f"Admin granted {amount} credits to {user.email}",
            target_user_id=user_id, tenant_id=user.tenant_id,
            before=before, after=after, reason=reason,
        )
        return {"balance": balance.balance, "amount_granted": amount}

    def deduct(self, actor_id: UUID, user_id: UUID, amount: int, reason: str) -> dict:
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError("User not found")
        balance = self.credit.get_or_create_balance(user_id)
        if balance.balance < amount:
            raise ValueError("Insufficient balance")
        before = {"balance": balance.balance}
        balance.balance -= amount
        balance.total_spent = (balance.total_spent or 0) + amount
        balance.updated_at = datetime.now(timezone.utc)
        txn = UserCreditTransaction(
            user_id=user_id,
            type="debit",
            amount=-amount,
            balance_after=balance.balance,
            description=f"Admin deduct: {reason}",
            transaction_metadata={"admin_action": True, "reason": reason},
        )
        self.db.add(txn)
        self.db.commit()
        after = {"balance": balance.balance}
        _log_admin_action(
            self.db, actor_id, f"Admin deducted {amount} credits from {user.email}",
            target_user_id=user_id, tenant_id=user.tenant_id,
            before=before, after=after, reason=reason,
        )
        return {"balance": balance.balance, "amount_deducted": amount}


class AdminDashboardService:
    def __init__(self, db: Session):
        self.db = db
        self.memory = AdminMemoryService(db)

    def get_overview(self) -> dict:
        now = datetime.now(timezone.utc)
        memory = self.memory.get_platform_overview()

        total_users = self.db.query(func.count(User.id)).scalar() or 0

        role_counts = {}
        role_rows = (
            self.db.query(Role.name, func.count(UserRole.id))
            .join(UserRole, UserRole.role_id == Role.id)
            .group_by(Role.name)
            .all()
        )
        for role_name, count in role_rows:
            key = role_name.value if hasattr(role_name, "value") else str(role_name)
            role_counts[key] = count

        dau = self.db.query(func.count(User.id)).filter(
            User.last_login_at >= now - timedelta(days=1)
        ).scalar() or 0
        wau = self.db.query(func.count(User.id)).filter(
            User.last_login_at >= now - timedelta(days=7)
        ).scalar() or 0
        mau = self.db.query(func.count(User.id)).filter(
            User.last_login_at >= now - timedelta(days=30)
        ).scalar() or 0

        total_orgs = self.db.query(func.count(Tenant.id)).filter(
            Tenant.type == TenantType.ORGANIZATION
        ).scalar() or 0
        total_schools = self.db.query(func.count(Tenant.id)).filter(
            Tenant.type == TenantType.SCHOOL
        ).scalar() or 0

        tier_rows = (
            self.db.query(UserSubscription.tier, func.count(UserSubscription.id))
            .group_by(UserSubscription.tier)
            .all()
        )
        tier_breakdown = {tier: count for tier, count in tier_rows}

        alerts = self.memory.get_alerts()

        try:
            factory = ContentFactoryService(self.db)
            jobs = factory.get_jobs_summary()
            queue_pending = jobs.get("pending", 0)
            queue_in_progress = jobs.get("in_progress", 0)
        except Exception:
            queue_pending = 0
            queue_in_progress = 0

        from app.core.observability import get_error_rate_24h
        error_rate = get_error_rate_24h()

        return {
            "total_users": total_users,
            "users_by_role": role_counts,
            "dau": dau,
            "wau": wau,
            "mau": mau,
            "total_organizations": total_orgs,
            "total_schools": total_schools,
            "tier_breakdown": tier_breakdown,
            "memory_total_balance": memory["total_balance"],
            "memory_total_allocated": memory["total_allocated"],
            "memory_total_spent": memory["total_spent"],
            "alert_count": len(alerts),
            "health_status": "healthy",
            "queue_pending": queue_pending,
            "queue_in_progress": queue_in_progress,
            "error_rate_24h": error_rate,
        }

    def get_alerts(self) -> List[dict]:
        items = []
        for i, alert in enumerate(AdminMemoryService(self.db).get_alerts()):
            items.append({
                "id": f"mem-{i}",
                "severity": alert["severity"],
                "title": alert["alert_type"].replace("_", " ").title(),
                "message": f"{alert['email']}: {alert['message']}",
                "created_at": datetime.now(timezone.utc),
                "link": f"/administration/memory?user={alert['user_id']}",
            })
        return items


class AdminUserService:
    def __init__(self, db: Session):
        self.db = db

    def _user_roles(self, user_id: UUID) -> List[str]:
        rows = (
            self.db.query(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .filter(UserRole.user_id == user_id)
            .all()
        )
        return [r[0].value if hasattr(r[0], "value") else str(r[0]) for r in rows]

    def list_users(
        self,
        page: int = 1,
        page_size: int = 25,
        search: Optional[str] = None,
        status: Optional[str] = None,
        role: Optional[str] = None,
        org_id: Optional[UUID] = None,
    ) -> Tuple[List[dict], int]:
        query = self.db.query(User, Tenant).join(Tenant, User.tenant_id == Tenant.id)

        if search:
            term = f"%{search.lower()}%"
            query = query.filter(
                or_(
                    func.lower(User.email).like(term),
                    func.lower(User.first_name).like(term),
                    func.lower(User.last_name).like(term),
                )
            )
        if status:
            query = query.filter(User.status == status)
        if org_id:
            query = query.filter(
                or_(Tenant.id == org_id, Tenant.parent_tenant_id == org_id)
            )
        if role:
            query = query.join(UserRole, UserRole.user_id == User.id).join(
                Role, UserRole.role_id == Role.id
            ).filter(Role.name == role)

        total = query.count()
        rows = (
            query.order_by(desc(User.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        items = []
        for user, tenant in rows:
            sub = self.db.query(UserSubscription).filter(UserSubscription.user_id == user.id).first()
            bal = self.db.query(UserTokenBalance).filter(UserTokenBalance.user_id == user.id).first()
            items.append({
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "status": user.status.value if hasattr(user.status, "value") else str(user.status),
                "tenant_id": user.tenant_id,
                "tenant_name": tenant.name,
                "roles": self._user_roles(user.id),
                "last_login_at": user.last_login_at,
                "created_at": user.created_at,
                "balance": bal.balance if bal else 0,
                "subscription_tier": sub.tier if sub else "free",
            })
        return items, total

    def get_user(self, user_id: UUID) -> Optional[dict]:
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            return None
        tenant = self.db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
        sub = self.db.query(UserSubscription).filter(UserSubscription.user_id == user.id).first()
        bal = self.db.query(UserTokenBalance).filter(UserTokenBalance.user_id == user.id).first()
        user_item = {
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "status": user.status.value if hasattr(user.status, "value") else str(user.status),
            "tenant_id": user.tenant_id,
            "tenant_name": tenant.name if tenant else None,
            "roles": self._user_roles(user.id),
            "last_login_at": user.last_login_at,
            "created_at": user.created_at,
            "balance": bal.balance if bal else 0,
            "subscription_tier": sub.tier if sub else "free",
        }
        memory = None
        if bal:
            pct = None
            if bal.total_allocated and bal.total_allocated > 0:
                pct = round(bal.balance * 100 / bal.total_allocated, 1)
            memory = {
                "user_id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "tenant_id": user.tenant_id,
                "tenant_name": tenant.name if tenant else None,
                "balance": bal.balance,
                "total_allocated": bal.total_allocated,
                "total_spent": bal.total_spent,
                "expires_at": bal.expires_at,
                "balance_pct": pct,
            }
        return {
            "user": user_item,
            "memory": memory,
            "subscription_tier": sub.tier if sub else "free",
            "subscription_status": sub.status if sub else "active",
        }

    def suspend(self, actor_id: UUID, user_id: UUID, reason: str) -> None:
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError("User not found")
        before = {"status": user.status.value if hasattr(user.status, "value") else str(user.status)}
        user.status = UserStatus.INACTIVE
        self.db.commit()
        _log_admin_action(
            self.db, actor_id, f"User suspended: {user.email}",
            target_user_id=user_id, tenant_id=user.tenant_id,
            before=before, after={"status": "inactive"}, reason=reason,
        )

    def reactivate(self, actor_id: UUID, user_id: UUID, reason: str) -> None:
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError("User not found")
        before = {"status": user.status.value if hasattr(user.status, "value") else str(user.status)}
        user.status = UserStatus.ACTIVE
        self.db.commit()
        _log_admin_action(
            self.db, actor_id, f"User reactivated: {user.email}",
            target_user_id=user_id, tenant_id=user.tenant_id,
            before=before, after={"status": "active"}, reason=reason,
        )

    def force_password_reset(self, actor_id: UUID, user_id: UUID, reason: str) -> None:
        from app.domains.auth.models import RefreshToken
        from app.core.security import generate_token_string, hash_token as hash_pw_token
        from app.domains.auth.models import PasswordResetToken

        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError("User not found")

        self.db.query(RefreshToken).filter(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
        ).update({"revoked_at": datetime.now(timezone.utc)})
        user.must_change_password = True
        self.db.commit()

        token_string = generate_token_string()
        reset_token = PasswordResetToken(
            user_id=user_id,
            token_hash=hash_pw_token(token_string),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        self.db.add(reset_token)
        self.db.commit()

        _log_admin_action(
            self.db, actor_id, f"Force password reset: {user.email}",
            target_user_id=user_id, tenant_id=user.tenant_id, reason=reason,
        )


class AdminOrgService:
    def __init__(self, db: Session):
        self.db = db

    def list_orgs(self, page: int = 1, page_size: int = 25, search: Optional[str] = None) -> Tuple[List[dict], int]:
        query = self.db.query(Tenant).filter(Tenant.type == TenantType.ORGANIZATION)
        if search:
            term = f"%{search.lower()}%"
            query = query.filter(func.lower(Tenant.name).like(term))
        total = query.count()
        orgs = query.order_by(Tenant.name).offset((page - 1) * page_size).limit(page_size).all()
        items = [self._org_summary(o) for o in orgs]
        return items, total

    def _org_summary(self, org: Tenant) -> dict:
        user_count = self.db.query(func.count(User.id)).filter(User.tenant_id == org.id).scalar() or 0
        school_count = self.db.query(func.count(Tenant.id)).filter(
            Tenant.parent_tenant_id == org.id,
            Tenant.type == TenantType.SCHOOL,
        ).scalar() or 0
        mem = (
            self.db.query(func.coalesce(func.sum(UserTokenBalance.balance), 0))
            .join(User, UserTokenBalance.user_id == User.id)
            .filter(User.tenant_id == org.id)
            .scalar()
            or 0
        )
        return {
            "id": org.id,
            "name": org.name,
            "slug": org.slug,
            "type": org.type.value if hasattr(org.type, "value") else str(org.type),
            "is_active": org.is_active,
            "user_count": user_count,
            "school_count": school_count,
            "memory_total_balance": int(mem),
            "created_at": org.created_at,
        }

    def get_org(self, org_id: UUID) -> Optional[dict]:
        org = self.db.query(Tenant).filter(Tenant.id == org_id, Tenant.type == TenantType.ORGANIZATION).first()
        if not org:
            return None
        schools = (
            self.db.query(Tenant)
            .filter(
                Tenant.parent_tenant_id == org_id,
                Tenant.type == TenantType.SCHOOL,
            )
            .all()
        )
        return {
            "organization": self._org_summary(org),
            "schools": [
                {"id": s.id, "name": s.name, "institution_type": s.type.value if hasattr(s.type, "value") else str(s.type)}
                for s in schools
            ],
        }

    def suspend(self, actor_id: UUID, org_id: UUID, reason: str) -> None:
        org = self.db.query(Tenant).filter(Tenant.id == org_id).first()
        if not org:
            raise ValueError("Organization not found")
        before = {"is_active": org.is_active}
        org.is_active = False
        self.db.commit()
        _log_admin_action(
            self.db, actor_id, f"Organization suspended: {org.name}",
            tenant_id=org_id, target_type="tenant",
            before=before, after={"is_active": False}, reason=reason,
        )

    def reactivate(self, actor_id: UUID, org_id: UUID, reason: str) -> None:
        org = self.db.query(Tenant).filter(Tenant.id == org_id).first()
        if not org:
            raise ValueError("Organization not found")
        before = {"is_active": org.is_active}
        org.is_active = True
        self.db.commit()
        _log_admin_action(
            self.db, actor_id, f"Organization reactivated: {org.name}",
            tenant_id=org_id, target_type="tenant",
            before=before, after={"is_active": True}, reason=reason,
        )


class AdminSchoolService:
    def __init__(self, db: Session):
        self.db = db

    def list_schools(
        self, page: int = 1, page_size: int = 25, search: Optional[str] = None, org_id: Optional[UUID] = None,
    ) -> Tuple[List[dict], int]:
        query = self.db.query(Tenant).filter(
            Tenant.type == TenantType.SCHOOL
        )
        if search:
            term = f"%{search.lower()}%"
            query = query.filter(func.lower(Tenant.name).like(term))
        if org_id:
            query = query.filter(Tenant.parent_tenant_id == org_id)
        total = query.count()
        schools = query.order_by(Tenant.name).offset((page - 1) * page_size).limit(page_size).all()
        items = []
        for tenant in schools:
            user_count = self.db.query(func.count(User.id)).filter(User.tenant_id == tenant.id).scalar() or 0
            org = None
            if tenant.parent_tenant_id:
                org = self.db.query(Tenant).filter(Tenant.id == tenant.parent_tenant_id).first()
            items.append({
                "id": tenant.id,
                "name": tenant.name,
                "institution_type": tenant.type.value if hasattr(tenant.type, "value") else str(tenant.type),
                "tenant_id": tenant.id,
                "tenant_name": tenant.name,
                "org_tenant_id": org.id if org else None,
                "org_name": org.name if org else None,
                "is_active": tenant.is_active,
                "user_count": user_count,
                "created_at": tenant.created_at,
            })
        return items, total


class AdminSubscriptionService:
    def __init__(self, db: Session):
        self.db = db

    def list_subscriptions(
        self, page: int = 1, page_size: int = 25, tier: Optional[str] = None, search: Optional[str] = None,
    ) -> Tuple[List[dict], int]:
        query = self.db.query(UserSubscription, User).join(User, UserSubscription.user_id == User.id)
        if tier:
            query = query.filter(UserSubscription.tier == tier)
        if search:
            term = f"%{search.lower()}%"
            query = query.filter(
                or_(
                    func.lower(User.email).like(term),
                    func.lower(User.first_name).like(term),
                    func.lower(User.last_name).like(term),
                )
            )
        total = query.count()
        rows = (
            query.order_by(desc(UserSubscription.updated_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        items = []
        for sub, user in rows:
            items.append({
                "user_id": user.id,
                "email": user.email,
                "full_name": user.full_name or f"{user.first_name} {user.last_name}",
                "tier": sub.tier,
                "status": sub.status,
                "current_period_end": sub.current_period_end,
                "is_trial": sub.is_trial,
                "is_manually_granted": sub.is_manually_granted,
            })
        return items, total


class AdminAuditService:
    def __init__(self, db: Session):
        self.db = db

    def list_logs(
        self,
        page: int = 1,
        page_size: int = 50,
        event_type: Optional[str] = None,
        actor_id: Optional[UUID] = None,
        search: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> Tuple[List[AuditLog], int]:
        query = self.db.query(AuditLog)
        if event_type:
            query = query.filter(AuditLog.event_type == event_type)
        if actor_id:
            query = query.filter(AuditLog.actor_user_id == actor_id)
        if search:
            term = f"%{search.lower()}%"
            query = query.filter(func.lower(AuditLog.description).like(term))
        if from_date:
            query = query.filter(AuditLog.created_at >= from_date)
        if to_date:
            query = query.filter(AuditLog.created_at <= to_date)
        total = query.count()
        items = (
            query.order_by(desc(AuditLog.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return items, total


class AdminComplianceService:
    def __init__(self, db: Session):
        self.db = db

    def create_request(self, requester_id: UUID, data: dict) -> ComplianceExportRequest:
        req = ComplianceExportRequest(
            requester_user_id=requester_id,
            subject_user_id=data.get("subject_user_id"),
            organization_id=data.get("organization_id"),
            request_type=data.get("request_type", "data_export"),
            reason=data["reason"],
            notes=data.get("notes"),
        )
        self.db.add(req)
        self.db.commit()
        self.db.refresh(req)
        return req

    def list_requests(self, page: int = 1, page_size: int = 25, status: Optional[str] = None) -> Tuple[List[ComplianceExportRequest], int]:
        query = self.db.query(ComplianceExportRequest)
        if status:
            query = query.filter(ComplianceExportRequest.status == status)
        total = query.count()
        items = (
            query.order_by(desc(ComplianceExportRequest.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return items, total


class AdminAnalyticsService:
    def __init__(self, db: Session):
        self.db = db

    def get_growth(self, days: int = 30) -> dict:
        now = datetime.now(timezone.utc)
        since = now - timedelta(days=days)
        data = []
        for i in range(days):
            day_start = (since + timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)
            new_users = self.db.query(func.count(User.id)).filter(
                User.created_at >= day_start, User.created_at < day_end
            ).scalar() or 0
            active_users = self.db.query(func.count(User.id)).filter(
                User.last_login_at >= day_start, User.last_login_at < day_end
            ).scalar() or 0
            data.append({
                "date": day_start.strftime("%Y-%m-%d"),
                "new_users": new_users,
                "active_users": active_users,
            })

        total = self.db.query(func.count(User.id)).scalar() or 0
        prev_total = self.db.query(func.count(User.id)).filter(User.created_at < since).scalar() or 0
        new_in_period = total - prev_total
        growth_rate = (new_in_period / prev_total * 100) if prev_total > 0 else 0.0

        return {"data": data, "total_users": total, "growth_rate_30d": round(growth_rate, 2)}

    def get_llm_cost(self, days: int = 30) -> dict:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        rows = (
            self.db.query(
                func.date_trunc("day", UserCreditTransaction.created_at).label("day"),
                UserCreditTransaction.model_used,
                func.coalesce(func.sum(UserCreditTransaction.usd_cost), 0),
                func.coalesce(func.sum(func.abs(UserCreditTransaction.amount)), 0),
                func.count(UserCreditTransaction.id),
            )
            .filter(
                UserCreditTransaction.type == "debit",
                UserCreditTransaction.created_at >= since,
                UserCreditTransaction.usd_cost.isnot(None),
            )
            .group_by("day", UserCreditTransaction.model_used)
            .order_by("day")
            .all()
        )

        data = []
        by_model: Dict[str, float] = {}
        total_usd = 0.0
        for day, model, usd, credits, count in rows:
            usd_f = float(usd or 0)
            total_usd += usd_f
            model_key = model or "unknown"
            by_model[model_key] = by_model.get(model_key, 0) + usd_f
            data.append({
                "date": day.strftime("%Y-%m-%d") if day else "",
                "model": model,
                "total_usd": round(usd_f, 4),
                "total_credits": int(credits or 0),
                "transaction_count": count,
            })

        return {"data": data, "total_usd_30d": round(total_usd, 4), "by_model": {k: round(v, 4) for k, v in by_model.items()}}
