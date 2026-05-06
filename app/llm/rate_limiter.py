"""
Rate limiter for LLM providers using token bucket algorithm.
"""
import asyncio
import time
from typing import Dict, Optional
from collections import defaultdict

from app.core.logging import get_logger
from app.llm.config import llm_settings

logger = get_logger(__name__)


class RateLimitError(Exception):
    """Raised when rate limit is exceeded."""
    pass


class TokenBucket:
    """Simple token bucket for rate limiting."""

    def __init__(self, capacity: int, refill_rate: float):
        """
        Initialize token bucket.

        Args:
            capacity: Maximum tokens in bucket
            refill_rate: Tokens added per second
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = float(capacity)
        self.last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def consume(self, tokens: int = 1) -> bool:
        """
        Try to consume tokens from bucket.

        Args:
            tokens: Number of tokens to consume

        Returns:
            True if tokens were consumed, False if rate limited
        """
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            
            # Refill tokens based on elapsed time
            self.tokens = min(
                self.capacity,
                self.tokens + (elapsed * self.refill_rate)
            )
            self.last_refill = now
            
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            else:
                return False


class RateLimiter:
    """Rate limiter for LLM providers."""

    def __init__(self, config):
        """
        Initialize rate limiter.

        Args:
            config: LLMSettings instance
        """
        self.config = config
        self._buckets: Dict[str, TokenBucket] = {}
        self._initialize_buckets()

    def _initialize_buckets(self) -> None:
        """Initialize rate limit buckets per provider."""
        # RPM-based buckets (requests per minute)
        provider_limits = {
            "openai": self.config.OPENAI_RATE_LIMIT_RPM,
            "anthropic": self.config.ANTHROPIC_RATE_LIMIT_RPM,
            "google": self.config.GOOGLE_RATE_LIMIT_RPM,
        }
        
        for provider, rpm in provider_limits.items():
            # Convert RPM to tokens per second (1 request = 1 token for simplicity)
            # Can be adjusted for actual token-based limiting
            capacity = rpm
            refill_rate = rpm / 60.0  # Tokens per second
            self._buckets[provider] = TokenBucket(capacity, refill_rate)
        
        logger.info(f"Initialized rate limiters: {provider_limits}")

    async def check_and_consume(
        self,
        provider: str,
        model_name: str,
        tokens: Optional[int] = None,
    ) -> None:
        """
        Check if provider/model is within rate limits and consume.

        Args:
            provider: Provider name
            model_name: Model name (for future per-model limits)
            tokens: Estimated tokens (for token-based limiting)

        Raises:
            RateLimitError: If rate limit is exceeded
        """
        if not self.config.RATE_LIMIT_ENABLED:
            return
        
        bucket = self._buckets.get(provider)
        if not bucket:
            logger.warning(f"No rate limit bucket for provider: {provider}")
            return
        
        # Consume 1 token per request (or use tokens parameter if provided)
        tokens_to_consume = tokens if tokens else 1
        
        if not await bucket.consume(tokens_to_consume):
            raise RateLimitError(
                f"Rate limit exceeded for provider {provider}. "
                f"Please try again later."
            )

