"""
Credit service — manages user token balance, deductions, top-ups, and history.
"""
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime, timezone
from dataclasses import dataclass

from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from app.core.logging import get_logger
from app.domains.subscriptions.models import (
    UserTokenBalance,
    UserCreditTransaction,
    FeatureCreditCost,
)

logger = get_logger(__name__)


@dataclass
class CreditCheckResult:
    allowed: bool
    balance: int
    reason: Optional[str] = None
    expires_at: Optional[datetime] = None


@dataclass
class CreditChargeResult:
    credits_charged: int
    balance_after: int
    transaction_id: Optional[UUID] = None


class CreditService:
    """Core service for credit balance management."""

    def __init__(self, db: Session):
        self.db = db

    # ─── Balance ──────────────────────────────────────────────────────────────

    def get_or_create_balance(self, user_id: UUID) -> UserTokenBalance:
        balance = self.db.query(UserTokenBalance).filter(
            UserTokenBalance.user_id == user_id
        ).first()
        if not balance:
            balance = UserTokenBalance(user_id=user_id, balance=0, total_allocated=0, total_spent=0)
            self.db.add(balance)
            self.db.flush()
        return balance

    def get_balance(self, user_id: UUID) -> Optional[UserTokenBalance]:
        return self.db.query(UserTokenBalance).filter(
            UserTokenBalance.user_id == user_id
        ).first()

    def check_balance(self, user_id: UUID) -> CreditCheckResult:
        """Check if user has credits available. Call before every AI operation."""
        try:
            balance = self.get_or_create_balance(user_id)

            if balance.balance <= 0:
                return CreditCheckResult(
                    allowed=False,
                    balance=0,
                    reason="no_credits",
                )

            if balance.expires_at and balance.expires_at < datetime.now(timezone.utc):
                if not balance.auto_renew:
                    return CreditCheckResult(
                        allowed=False,
                        balance=balance.balance,
                        reason="credits_expired",
                        expires_at=balance.expires_at,
                    )

            return CreditCheckResult(
                allowed=True,
                balance=balance.balance,
                expires_at=balance.expires_at,
            )
        except Exception as e:
            logger.error(f"Credit check failed, denying request: {e}", exc_info=True)
            return CreditCheckResult(
                allowed=False,
                balance=0,
                reason="credit_check_error",
            )

    # ─── Charge ───────────────────────────────────────────────────────────────

    def get_feature_cost(self, feature_key: str) -> int:
        """Look up base credit cost for a feature. Falls back to 2 if not found."""
        try:
            cost = self.db.query(FeatureCreditCost).filter(
                FeatureCreditCost.feature_key == feature_key,
                FeatureCreditCost.is_active == True,
            ).first()
            return cost.base_credits if cost else 2
        except Exception:
            return 2

    def charge(
        self,
        user_id: UUID,
        feature_key: str,
        llm_response=None,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CreditChargeResult:
        """
        Deduct credits for an AI operation.
        Gracefully degrades — never blocks the main operation if credit tables are unavailable.
        """
        try:
            credits = self.get_feature_cost(feature_key)
            balance = self.get_or_create_balance(user_id)

            new_balance = max(0, balance.balance - credits)
            balance.balance = new_balance
            balance.total_spent = (balance.total_spent or 0) + credits
            balance.updated_at = datetime.now(timezone.utc)

            input_tokens = None
            output_tokens = None
            usd_cost = None
            model_used = None

            if llm_response and hasattr(llm_response, 'token_usage') and llm_response.token_usage:
                input_tokens = llm_response.token_usage.prompt
                output_tokens = llm_response.token_usage.completion
            if llm_response and hasattr(llm_response, 'cost_estimate') and llm_response.cost_estimate:
                usd_cost = float(llm_response.cost_estimate)
            if llm_response and hasattr(llm_response, 'model_used'):
                model_used = llm_response.model_used

            # Resolve display name for description
            if not description:
                try:
                    cost_row = self.db.query(FeatureCreditCost).filter(
                        FeatureCreditCost.feature_key == feature_key
                    ).first()
                    description = cost_row.display_name if cost_row else feature_key.replace("_", " ").title()
                except Exception:
                    description = feature_key.replace("_", " ").title()

            txn = UserCreditTransaction(
                user_id=user_id,
                type="debit",
                amount=-credits,
                balance_after=new_balance,
                feature_key=feature_key,
                description=description,
                model_used=model_used,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                usd_cost=usd_cost,
                transaction_metadata=metadata,
            )
            self.db.add(txn)
            self.db.commit()

            return CreditChargeResult(
                credits_charged=credits,
                balance_after=new_balance,
                transaction_id=txn.id,
            )
        except Exception as e:
            logger.warning(f"Credit charge failed (non-blocking): {e}")
            try:
                self.db.rollback()
            except Exception:
                pass
            return CreditChargeResult(credits_charged=0, balance_after=0)

    # ─── Top-up ───────────────────────────────────────────────────────────────

    def top_up(
        self,
        user_id: UUID,
        credits: int,
        expires_at: Optional[datetime],
        auto_renew: bool = False,
        source_description: str = "Credits activated",
        reference_id: Optional[UUID] = None,
    ) -> UserTokenBalance:
        """Add credits to a user's balance."""
        balance = self.get_or_create_balance(user_id)
        now = datetime.now(timezone.utc)

        if balance.subscription_started_at is None:
            balance.subscription_started_at = now

        balance.balance = (balance.balance or 0) + credits
        balance.total_allocated = (balance.total_allocated or 0) + credits
        balance.expires_at = expires_at
        balance.auto_renew = auto_renew
        balance.last_topped_up_at = now
        balance.updated_at = now

        txn = UserCreditTransaction(
            user_id=user_id,
            type="credit",
            amount=credits,
            balance_after=balance.balance,
            description=source_description,
            reference_id=reference_id,
        )
        self.db.add(txn)
        self.db.commit()
        self.db.refresh(balance)
        return balance

    # ─── History & Analytics ──────────────────────────────────────────────────

    def get_transaction_history(
        self,
        user_id: UUID,
        page: int = 1,
        page_size: int = 20,
        feature_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        query = self.db.query(UserCreditTransaction).filter(
            UserCreditTransaction.user_id == user_id
        )
        if feature_key:
            query = query.filter(UserCreditTransaction.feature_key == feature_key)

        total = query.count()
        items = (
            query.order_by(desc(UserCreditTransaction.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return {"total": total, "page": page, "page_size": page_size, "items": items}

    def get_usage_breakdown(self, user_id: UUID, days: int = 30) -> List[Dict[str, Any]]:
        """Credits spent per feature in the last N days."""
        from datetime import timedelta
        since = datetime.now(timezone.utc) - timedelta(days=days)

        rows = (
            self.db.query(
                UserCreditTransaction.feature_key,
                func.sum(func.abs(UserCreditTransaction.amount)).label("credits"),
                func.count(UserCreditTransaction.id).label("call_count"),
            )
            .filter(
                UserCreditTransaction.user_id == user_id,
                UserCreditTransaction.type == "debit",
                UserCreditTransaction.created_at >= since,
                UserCreditTransaction.feature_key != None,
            )
            .group_by(UserCreditTransaction.feature_key)
            .order_by(desc("credits"))
            .all()
        )

        total_credits = sum(r.credits for r in rows) or 1  # avoid div by zero

        breakdown = []
        for row in rows:
            cost_row = self.db.query(FeatureCreditCost).filter(
                FeatureCreditCost.feature_key == row.feature_key
            ).first()
            breakdown.append({
                "feature_key": row.feature_key,
                "display_name": cost_row.display_name if cost_row else row.feature_key,
                "module_name": cost_row.module_name if cost_row else "Other",
                "credits": row.credits,
                "call_count": row.call_count,
                "pct_of_total": round((row.credits / total_credits) * 100, 1),
            })
        return breakdown

    def get_usage_summary(self, user_id: UUID) -> Dict[str, Any]:
        """High-level stats for the usage dashboard header."""
        balance = self.get_or_create_balance(user_id)
        breakdown = self.get_usage_breakdown(user_id, days=30)

        top_module = breakdown[0]["module_name"] if breakdown else None
        monthly_spent = sum(b["credits"] for b in breakdown)

        return {
            "balance": balance.balance,
            "total_allocated": balance.total_allocated,
            "total_spent": balance.total_spent,
            "expires_at": balance.expires_at.isoformat() if balance.expires_at else None,
            "auto_renew": balance.auto_renew,
            "subscription_started_at": (
                balance.subscription_started_at.isoformat()
                if balance.subscription_started_at else None
            ),
            "monthly_spent": monthly_spent,
            "top_module": top_module,
        }
