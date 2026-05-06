"""
Rate limiting utilities using slowapi.
"""
from typing import Optional
from fastapi import Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.core.config import settings

# Create limiter instance
limiter = Limiter(key_func=get_remote_address)


def get_rate_limiter() -> Limiter:
    """Get the rate limiter instance."""
    return limiter


def login_rate_limit(request: Request) -> Optional[str]:
    """
    Custom rate limit key function for login endpoints.
    Uses IP address with stricter limits.
    """
    return get_remote_address(request)


# Rate limit decorators for common use cases
def rate_limit_login(func):
    """Rate limit decorator for login endpoints (5 requests per minute per IP)."""
    # Use get_remote_address directly - slowapi will pass the Request automatically
    return limiter.limit(f"{settings.RATE_LIMIT_LOGIN_PER_IP}/minute", key_func=get_remote_address)(func)


def rate_limit_default(func):
    """Rate limit decorator for general API endpoints (10 requests per minute per IP)."""
    return limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")(func)

