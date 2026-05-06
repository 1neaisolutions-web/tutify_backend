"""
Shared credit error payloads for HTTP 402 (Payment Required).
"""
from typing import Any, Dict, Optional

from app.domains.subscriptions.services.credit_service import CreditCheckResult


def insufficient_credits_detail(
    check: CreditCheckResult,
    required: int,
    message: str,
) -> Dict[str, Any]:
    """Body shape for FastAPI HTTPException(detail=...), aligned with templates route."""
    reason: Optional[str] = check.reason or "no_credits"
    if not check.allowed and check.balance > 0 and reason != "credits_expired":
        # Low balance but not zero — still use reason from check
        pass
    return {
        "error": "insufficient_credits",
        "message": message,
        "balance": check.balance,
        "required": required,
        "reason": reason,
    }
