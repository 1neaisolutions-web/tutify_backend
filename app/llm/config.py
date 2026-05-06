"""
LLM configuration for provider keys, default models, pricing, rate limits, and caching.
"""
from typing import Optional, Dict, Any
from decimal import Decimal

from pydantic_settings import BaseSettings, SettingsConfigDict


# Default pricing per 1K tokens (input, output)
MODEL_PRICING_DEFAULTS: Dict[str, Dict[str, Dict[str, float]]] = {
    "openai": {
        "gpt-4o": {"input": 0.0025, "output": 0.010},
        "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
        "gpt-4": {"input": 0.03, "output": 0.06},
        "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
    },
    "anthropic": {
        "claude-3-opus-20240229": {"input": 0.015, "output": 0.075},
        "claude-3-sonnet-20240229": {"input": 0.003, "output": 0.015},
        "claude-3-haiku-20240307": {"input": 0.00025, "output": 0.00125},
    },
    "google": {
        "gemini-pro": {"input": 0.0005, "output": 0.0015},
        "gemini-1.5-pro": {"input": 0.00125, "output": 0.005},
    },
}


class LLMSettings(BaseSettings):
    """LLM-related settings."""

    # Provider API Keys
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: Optional[str] = None  # Custom OpenAI API base URL (optional)
    ANTHROPIC_API_KEY: Optional[str] = None
    GOOGLE_API_KEY: Optional[str] = None

    # Default model configuration
    DEFAULT_MODEL_PROVIDER: str = "openai"
    DEFAULT_MODEL: str = "gpt-4o-mini"
    OPENAI_IMAGE_MODEL: str = "gpt-image-1"
    DEFAULT_TEMPERATURE: float = 0.7
    DEFAULT_MAX_TOKENS: int = 4000  # Increased from 2000 to 4000 to match Activity's approach (they use 3000, we use 4000 for safety)

    # OpenAI client timeouts (seconds) - fail fast, no hang
    OPENAI_CONNECT_TIMEOUT: float = 10.0
    OPENAI_READ_TIMEOUT: float = 150.0  # Per-request read; worksheet route has total cap (e.g. 180s)

    # Feature flags
    USE_REAL_LLM: bool = False
    FALLBACK_ENABLED: bool = True  # Use FallbackProvider if all providers fail
    # When false, ModelRouter never calls OpenAI/Anthropic/Google (only FallbackProvider).
    # Use for local/CI safety so a mis-set USE_REAL_LLM cannot burn provider tokens.
    # PixGen image API and OpenAI embeddings also respect this flag (see model_adapter / embedding_providers).
    LLM_OUTBOUND_ENABLED: bool = True
    # When false, Learning Hub personalization must not enqueue or process content_factory jobs that
    # exist only to fill personalized inventory (sources inventory_expansion and user-scoped gap_detection).
    # Platform gap_detection jobs (requested_by_user_id NULL) and on-demand template flows still use LLM when LLM_OUTBOUND_ENABLED=true.
    PERSONALIZATION_LLM_OUTBOUND_ENABLED: bool = False

    # Caching
    CACHE_ENABLED: bool = True
    CACHE_TTL_SECONDS: int = 3600  # 1 hour default
    REDIS_URL: Optional[str] = None  # If set, use Redis; otherwise in-memory

    # Rate limiting
    RATE_LIMIT_ENABLED: bool = True
    OPENAI_RATE_LIMIT_RPM: int = 60  # Requests per minute
    ANTHROPIC_RATE_LIMIT_RPM: int = 60
    GOOGLE_RATE_LIMIT_RPM: int = 60
    TOKENS_PER_MINUTE: Optional[int] = None  # Optional global token limit

    # Cost tracking
    COST_TRACKING_ENABLED: bool = True
    MODEL_PRICING: Optional[Dict[str, Any]] = None  # Override pricing if needed

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    def get_model_pricing(self) -> Dict[str, Dict[str, Dict[str, float]]]:
        """Get model pricing, using override if provided, else defaults."""
        if self.MODEL_PRICING:
            return self.MODEL_PRICING
        return MODEL_PRICING_DEFAULTS


# Global LLM settings instance
llm_settings = LLMSettings()
