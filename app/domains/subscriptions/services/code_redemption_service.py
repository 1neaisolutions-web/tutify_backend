"""
Code redemption service — activates access codes and manages renewals.
"""
from typing import Optional
from uuid import UUID
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domains.subscriptions.code_normalization import normalize_access_code
from app.domains.subscriptions.models import AccessCode, UserCodeRedemption, UserTokenBalance
from app.domains.subscriptions.services.credit_service import CreditService

logger = get_logger(__name__)


@dataclass
class RedemptionResult:
    success: bool
    credits_added: int = 0
    balance: int = 0
    expires_at: Optional[datetime] = None
    auto_renew: bool = False
    error: Optional[str] = None
    error_code: Optional[str] = None


class CodeRedemptionService:
    """Handles access code validation, activation, and auto-renewal."""

    def __init__(self, db: Session):
        self.db = db
        self.credit_service = CreditService(db)

    def redeem_code(self, user_id: UUID, code_str: str) -> RedemptionResult:
        """Validate and activate an access code for a user."""
        canonical = normalize_access_code(code_str)
        if len(canonical) < 3:
            return RedemptionResult(
                success=False,
                error="Invalid access code. Please check and try again.",
                error_code="invalid_code",
            )

        # Prefer indexed equality on normalized codes; fallback compares normalized for legacy hyphenated rows
        code = (
            self.db.query(AccessCode)
            .filter(AccessCode.code == canonical, AccessCode.is_active == True)
            .first()
        )
        if not code:
            for c in self.db.query(AccessCode).filter(AccessCode.is_active == True).all():
                if normalize_access_code(c.code) == canonical:
                    code = c
                    break

        if not code:
            return RedemptionResult(
                success=False,
                error="Invalid access code. Please check and try again.",
                error_code="invalid_code",
            )

        # Check code expiry
        if code.expires_at and code.expires_at < datetime.now(timezone.utc):
            return RedemptionResult(
                success=False,
                error="This access code has expired.",
                error_code="code_expired",
            )

        # Check max uses
        if code.max_uses is not None and code.times_used >= code.max_uses:
            return RedemptionResult(
                success=False,
                error="This access code has already been fully redeemed.",
                error_code="code_exhausted",
            )

        # Check if user already redeemed THIS specific code
        existing = self.db.query(UserCodeRedemption).filter(
            UserCodeRedemption.user_id == user_id,
            UserCodeRedemption.access_code_id == code.id,
        ).first()
        if existing:
            return RedemptionResult(
                success=False,
                error="You have already activated this code.",
                error_code="already_redeemed",
            )

        # All checks passed — activate
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=code.validity_days)

        redemption = UserCodeRedemption(
            user_id=user_id,
            access_code_id=code.id,
            expires_at=expires_at,
            credit_allocation=code.credit_allocation,
            is_active=True,
            auto_renew=code.auto_renew,
        )
        self.db.add(redemption)
        self.db.flush()

        # Increment usage counter
        code.times_used = (code.times_used or 0) + 1

        # Top up the user's balance
        balance = self.credit_service.top_up(
            user_id=user_id,
            credits=code.credit_allocation,
            expires_at=expires_at,
            auto_renew=code.auto_renew,
            source_description=f"Credits activated ({code.code})",
            reference_id=redemption.id,
        )

        return RedemptionResult(
            success=True,
            credits_added=code.credit_allocation,
            balance=balance.balance,
            expires_at=expires_at,
            auto_renew=code.auto_renew,
        )

    def get_active_redemption(self, user_id: UUID) -> Optional[UserCodeRedemption]:
        return (
            self.db.query(UserCodeRedemption)
            .filter(
                UserCodeRedemption.user_id == user_id,
                UserCodeRedemption.is_active == True,
            )
            .order_by(UserCodeRedemption.redeemed_at.desc())
            .first()
        )

    def auto_renew_if_needed(self, user_id: UUID) -> bool:
        """
        Called by the background job. Renews credits for staff codes when balance
        drops below the threshold percentage.
        """
        balance = self.db.query(UserTokenBalance).filter(
            UserTokenBalance.user_id == user_id,
            UserTokenBalance.auto_renew == True,
        ).first()

        if not balance or not balance.auto_renew:
            return False

        redemption = self.get_active_redemption(user_id)
        if not redemption or not redemption.auto_renew:
            return False

        code = self.db.query(AccessCode).filter(
            AccessCode.id == redemption.access_code_id,
            AccessCode.auto_renew == True,
            AccessCode.is_active == True,
        ).first()

        if not code:
            return False

        # Check if balance is below the renewal threshold
        threshold_pct = code.auto_renew_threshold_pct or 20
        pct_remaining = (balance.balance / code.credit_allocation * 100) if code.credit_allocation > 0 else 0

        if pct_remaining > threshold_pct:
            return False

        # Renew
        now = datetime.now(timezone.utc)
        new_expires = now + timedelta(days=code.validity_days)

        self.credit_service.top_up(
            user_id=user_id,
            credits=code.credit_allocation,
            expires_at=new_expires,
            auto_renew=True,
            source_description=f"Credits auto-renewed ({code.code})",
            reference_id=redemption.id,
        )

        redemption.last_renewed_at = now
        self.db.commit()

        logger.info(f"Auto-renewed {code.credit_allocation} credits for user {user_id}")
        return True
