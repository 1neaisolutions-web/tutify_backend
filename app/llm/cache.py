"""
Response cache for LLM responses.
"""
import hashlib
import json
from typing import Optional
from datetime import datetime, timedelta

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

from app.core.logging import get_logger
from app.llm.schemas import LLMResponse

logger = get_logger(__name__)


class ResponseCache:
    """Cache for LLM responses (in-memory or Redis)."""

    def __init__(self, ttl_seconds: int, redis_url: Optional[str] = None):
        """
        Initialize cache.

        Args:
            ttl_seconds: Time-to-live for cached entries
            redis_url: If provided, use Redis; otherwise use in-memory dict
        """
        self.ttl_seconds = ttl_seconds
        self.redis_url = redis_url
        self.redis_client: Optional[redis.Redis] = None
        self._memory_cache: dict = {}  # In-memory fallback
        
        if redis_url and REDIS_AVAILABLE:
            try:
                self.redis_client = redis.from_url(redis_url, decode_responses=True)
                logger.info("Using Redis for LLM response cache")
            except Exception as e:
                logger.warning(f"Failed to connect to Redis: {e}, using in-memory cache")
                self.redis_client = None
        else:
            logger.info("Using in-memory cache for LLM responses")

    def _make_key(
        self,
        *,
        system_message: str,
        prompt: str,
        provider: str,
        model: str,
        temperature: Optional[float],
        max_tokens: Optional[int],
        format_type: str = "toon"
    ) -> str:
        """
        Build a stable hash key from arguments.

        Args:
            system_message: System message
            prompt: User prompt
            provider: Provider name
            model: Model name
            temperature: Temperature setting
            max_tokens: Max tokens
            format_type: Format type (TOON vs JSON)

        Returns:
            SHA256 hash string
        """
        key_data = {
            "system_message": system_message,
            "prompt": prompt,
            "provider": provider,
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "format_type": format_type,
        }
        key_json = json.dumps(key_data, sort_keys=True)
        return hashlib.sha256(key_json.encode()).hexdigest()

    async def get(self, key: str) -> Optional[LLMResponse]:
        """
        Return cached LLMResponse or None if missing/expired.

        Args:
            key: Cache key

        Returns:
            Cached LLMResponse or None
        """
        if self.redis_client:
            try:
                cached = await self.redis_client.get(key)
                if cached:
                    data = json.loads(cached)
                    return LLMResponse(**data)
            except Exception as e:
                logger.warning(f"Redis get error: {e}")
        else:
            # In-memory cache
            if key in self._memory_cache:
                entry = self._memory_cache[key]
                if datetime.now() < entry["expires_at"]:
                    return LLMResponse(**entry["data"])
                else:
                    # Expired, remove it
                    del self._memory_cache[key]
        
        return None

    async def set(self, key: str, value: LLMResponse) -> None:
        """
        Store LLMResponse with TTL.

        Args:
            key: Cache key
            value: LLMResponse to cache
        """
        data = value.model_dump()
        
        if self.redis_client:
            try:
                await self.redis_client.setex(
                    key,
                    self.ttl_seconds,
                    json.dumps(data)
                )
            except Exception as e:
                logger.warning(f"Redis set error: {e}")
        else:
            # In-memory cache
            expires_at = datetime.now() + timedelta(seconds=self.ttl_seconds)
            self._memory_cache[key] = {
                "data": data,
                "expires_at": expires_at
            }
            
            # Clean up expired entries periodically (simple cleanup)
            if len(self._memory_cache) > 1000:
                now = datetime.now()
                expired_keys = [
                    k for k, v in self._memory_cache.items()
                    if now >= v["expires_at"]
                ]
                for k in expired_keys:
                    del self._memory_cache[k]

