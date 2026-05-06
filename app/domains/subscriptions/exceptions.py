"""Domain exceptions for subscription and credit gating."""

from app.domains.subscriptions.services.credit_service import CreditCheckResult


class InsufficientCreditsError(Exception):
    """Raised when an operation cannot proceed due to credit balance or expiry."""

    def __init__(
        self,
        check: CreditCheckResult,
        required: int,
        message: str = "You don't have enough credits to continue.",
    ):
        self.check = check
        self.required = required
        self.message = message
        super().__init__(message)
