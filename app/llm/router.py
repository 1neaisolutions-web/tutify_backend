"""
Model router for selecting LLM provider and model with fallback chains, caching, rate limiting, and cost tracking.
"""
from typing import Optional, Dict, Any, List, AsyncIterator

from app.core.logging import get_logger
from app.llm.config import llm_settings
from app.llm.base import BaseProvider
from app.llm.schemas import LLMResponse
from app.llm.cache import ResponseCache
from app.llm.rate_limiter import RateLimiter, RateLimitError
from app.llm.cost_tracker import CostTracker
from app.llm.providers import (
    OpenAIProvider,
    AnthropicProvider,
    FallbackProvider,
)

# GoogleProvider is optional
try:
    from app.llm.providers import GoogleProvider
except ImportError:
    GoogleProvider = None  # type: ignore

logger = get_logger(__name__)


def _outbound_calls_allowed(config) -> bool:
    return bool(getattr(config, "LLM_OUTBOUND_ENABLED", True))


class ModelRouter:
    """Router for LLM providers with fallback chains, caching, rate limiting, and cost tracking."""

    def __init__(
        self,
        config=None,
        cache: Optional[ResponseCache] = None,
        rate_limiter: Optional[RateLimiter] = None,
        cost_tracker: Optional[CostTracker] = None,
    ):
        """
        Initialize model router.

        Args:
            config: LLMSettings instance (defaults to llm_settings)
            cache: ResponseCache instance (optional)
            rate_limiter: RateLimiter instance (optional)
            cost_tracker: CostTracker instance (optional)
        """
        self.config = config or llm_settings
        self.cache = cache
        self.rate_limiter = rate_limiter
        self.cost_tracker = cost_tracker
        self._providers: Dict[str, BaseProvider] = {}
        self._provider_health: Dict[str, bool] = {}
        self._provider_init_error: Dict[str, str] = {}  # reason when init failed (sanitized)
        
        self._initialize_providers()

    def _initialize_providers(self) -> None:
        """Instantiate providers conditionally based on available API keys."""
        # Config source (never log the key)
        openai_key_status = "set" if (self.config.OPENAI_API_KEY and len(self.config.OPENAI_API_KEY.strip()) > 0) else ("empty" if getattr(self.config, "OPENAI_API_KEY", None) is not None else "missing")
        openai_base = getattr(self.config, "OPENAI_BASE_URL", None) or ""
        openai_base_display = openai_base if openai_base else "not set"
        if openai_base and "opeanai" in openai_base.lower():
            logger.warning("OPENAI_BASE_URL may have a typo (opeanai -> openai). API calls may fail.")

        # OpenAI
        try:
            if self.config.OPENAI_API_KEY and self.config.OPENAI_API_KEY.strip():
                self._providers["openai"] = OpenAIProvider()
                self._provider_health["openai"] = True
                logger.info("OpenAI provider initialized")
            else:
                self._provider_health["openai"] = False
                self._provider_init_error["openai"] = "OPENAI_API_KEY missing or empty"
        except Exception as e:
            err_msg = f"{type(e).__name__}: {str(e)}"[:200]
            self._provider_init_error["openai"] = err_msg
            self._provider_health["openai"] = False
            logger.warning(f"Failed to initialize OpenAI provider: {e}")

        # Anthropic
        try:
            if self.config.ANTHROPIC_API_KEY:
                self._providers["anthropic"] = AnthropicProvider()
                self._provider_health["anthropic"] = True
                logger.info("Anthropic provider initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize Anthropic provider: {e}")
            self._provider_health["anthropic"] = False

        # Google (optional - requires google-generativeai package)
        try:
            if self.config.GOOGLE_API_KEY and GoogleProvider:
                self._providers["google"] = GoogleProvider()
                self._provider_health["google"] = True
                logger.info("Google provider initialized")
            elif self.config.GOOGLE_API_KEY and not GoogleProvider:
                logger.warning("Google API key provided but google-generativeai package not installed")
                self._provider_health["google"] = False
        except Exception as e:
            logger.warning(f"Failed to initialize Google provider: {e}")
            self._provider_health["google"] = False

        # Fallback (always available)
        self._providers["fallback"] = FallbackProvider()
        self._provider_health["fallback"] = True

        # Single startup log: provider selection and why (never print keys)
        openai_status = "available" if self._provider_health.get("openai") else f"unavailable ({self._provider_init_error.get('openai', 'not initialized')})"
        logger.info(
            f"LLM provider selection: openai={openai_status}, fallback=always. "
            f"Config source: .env (OPENAI_API_KEY={openai_key_status}, OPENAI_BASE_URL={'set' if openai_base else 'not set'}, DEFAULT_MODEL_PROVIDER={getattr(self.config, 'DEFAULT_MODEL_PROVIDER', 'openai')})."
        )
        if not _outbound_calls_allowed(self.config):
            logger.warning(
                "LLM_OUTBOUND_ENABLED=false — outbound provider calls are blocked; "
                "ModelRouter will only use FallbackProvider (no paid API usage)."
            )

    def _apply_outbound_guard(self, providers_to_try: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Strip paid providers when LLM_OUTBOUND_ENABLED is false (defense in depth)."""
        if _outbound_calls_allowed(self.config):
            return providers_to_try
        filtered = [p for p in providers_to_try if p.get("provider") == "fallback"]
        if filtered:
            return filtered
        return [{"provider": "fallback", "model": "fallback"}]

    async def generate(
        self,
        system_message: str,
        prompt: str,
        model_config: Optional[Dict[str, Any]] = None,
    ) -> LLMResponse:
        """
        Generate response with caching, rate limiting, fallback chains, and cost tracking.

        Process:
        1. Build cache key and check cache (if enabled)
        2. Resolve primary provider/model from model_config or defaults
        3. Apply rate limiting before each provider call
        4. Call provider.generate()
        5. On error, try providers/models in fallback_chain
        6. After success, compute cost, store in cache, and return LLMResponse

        Args:
            system_message: System message
            prompt: User prompt
            model_config: Model configuration from TemplateVersion (optional)

        Returns:
            LLMResponse with content, model_used, provider, token_usage, cost_estimate, etc.
        """
        # Extract configuration
        provider = model_config.get("provider") if model_config else None
        model = model_config.get("model") if model_config else None
        temperature = model_config.get("temperature") if model_config else None
        max_tokens = model_config.get("max_tokens") if model_config else None
        fallback_chain = model_config.get("fallback_chain", []) if model_config else []
        cache_ttl = model_config.get("cache_ttl") if model_config else None
        format_type = "toon"  # Default to TOON format

        # Use defaults if not specified
        provider = provider or self.config.DEFAULT_MODEL_PROVIDER
        model = model or self.config.DEFAULT_MODEL
        temperature = temperature if temperature is not None else self.config.DEFAULT_TEMPERATURE
        max_tokens = max_tokens or self.config.DEFAULT_MAX_TOKENS

        # 1. Check cache
        if self.cache and self.config.CACHE_ENABLED:
            cache_key = self.cache._make_key(
                system_message=system_message,
                prompt=prompt,
                provider=provider,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                format_type=format_type
            )
            
            cached_response = await self.cache.get(cache_key)
            if cached_response:
                logger.info(f"Cache hit for provider={provider}, model={model}")
                # Mark as cache hit
                cached_response.cache_hit = True
                return cached_response

        # 2. Build list of providers to try (primary + fallback chain)
        providers_to_try: List[Dict[str, Any]] = [
            {"provider": provider, "model": model}
        ]
        
        # Add fallback chain
        for fallback in fallback_chain:
            if isinstance(fallback, dict):
                providers_to_try.append({
                    "provider": fallback.get("provider"),
                    "model": fallback.get("model")
                })

        # When OpenAI is explicitly requested and key is set, do NOT add fallback so we surface real errors
        add_final_fallback = self.config.FALLBACK_ENABLED
        if provider == "openai" and (self.config.OPENAI_API_KEY or "").strip():
            add_final_fallback = False
        if add_final_fallback:
            providers_to_try.append({"provider": "fallback", "model": "fallback"})

        providers_to_try = self._apply_outbound_guard(providers_to_try)

        # 3. If OpenAI was requested and key is set but provider is unavailable, fail fast with clear error
        if (
            _outbound_calls_allowed(self.config)
            and provider == "openai"
            and (self.config.OPENAI_API_KEY or "").strip()
        ):
            if not self._provider_health.get("openai", False):
                reason = self._provider_init_error.get("openai", "OpenAI provider init failed")
                raise RuntimeError(
                    f"OpenAI was requested but is unavailable. {reason}. "
                    "Check OPENAI_API_KEY and OPENAI_BASE_URL in .env and restart."
                )
            if provider not in self._providers or not self._providers.get(provider):
                raise RuntimeError(
                    "OpenAI was requested but provider instance is missing. Check OPENAI_API_KEY and restart."
                )

        # 4. Try each provider in sequence
        last_error = None
        
        for attempt in providers_to_try:
            attempt_provider = attempt["provider"]
            attempt_model = attempt["model"]
            
            if not attempt_provider or not attempt_model:
                continue
            
            # Check provider health
            if not self._provider_health.get(attempt_provider, False):
                logger.warning(f"Provider {attempt_provider} is not healthy, skipping")
                continue
            
            provider_instance = self._providers.get(attempt_provider)
            if not provider_instance:
                logger.warning(f"Provider {attempt_provider} not available, skipping")
                continue

            try:
                # 4. Apply rate limiting
                if self.rate_limiter and self.config.RATE_LIMIT_ENABLED:
                    try:
                        await self.rate_limiter.check_and_consume(
                            provider=attempt_provider,
                            model_name=attempt_model
                        )
                    except RateLimitError as e:
                        logger.warning(f"Rate limit exceeded for {attempt_provider}: {e}")
                        # Try next provider in chain
                        continue

                # 5. Call provider
                logger.info(f"Calling provider={attempt_provider}, model={attempt_model}")
                response = await provider_instance.generate(
                    prompt=prompt,
                    system_message=system_message,
                    model_name=attempt_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )

                # 6. Compute cost
                if self.cost_tracker and self.config.COST_TRACKING_ENABLED:
                    if response.token_usage:
                        cost = self.cost_tracker.estimate_cost(
                            provider=attempt_provider,
                            model_name=attempt_model,
                            token_usage=response.token_usage
                        )
                        response.cost_estimate = float(cost)

                # 7. Store in cache
                if self.cache and self.config.CACHE_ENABLED:
                    ttl = cache_ttl or self.config.CACHE_TTL_SECONDS
                    await self.cache.set(cache_key, response)

                # Mark as not from cache
                response.cache_hit = False
                
                logger.info(
                    f"Successfully generated response from {attempt_provider}/{attempt_model}, "
                    f"tokens={response.token_usage.total if response.token_usage else 0}, "
                    f"cost=${response.cost_estimate or 0:.6f}"
                )
                
                return response

            except Exception as e:
                logger.warning(
                    f"Provider {attempt_provider} failed: {e}, "
                    f"trying next in fallback chain"
                )
                last_error = e
                # Mark provider as unhealthy temporarily
                self._provider_health[attempt_provider] = False
                continue

        # All providers failed
        error_msg = f"All providers failed. Last error: {last_error}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)

    async def stream(
        self,
        system_message: str,
        prompt: str,
        model_config: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[str]:
        """
        Stream response with rate limiting and fallback chains.

        Yields raw text chunks from the LLM provider.
        Does not handle caching (streaming responses are typically not cached).
        Handles fallback chains: if primary provider fails before any chunk,
        tries next provider in chain.

        Args:
            system_message: System message
            prompt: User prompt
            model_config: Model configuration from TemplateVersion (optional)

        Yields:
            Raw text chunks (plain strings) as they arrive from the LLM

        Raises:
            RuntimeError: If all providers in fallback chain fail
        """
        # Extract configuration
        provider = model_config.get("provider") if model_config else None
        model = model_config.get("model") if model_config else None
        temperature = model_config.get("temperature") if model_config else None
        max_tokens = model_config.get("max_tokens") if model_config else None
        fallback_chain = model_config.get("fallback_chain", []) if model_config else []

        # Use defaults if not specified
        provider = provider or self.config.DEFAULT_MODEL_PROVIDER
        model = model or self.config.DEFAULT_MODEL
        temperature = temperature if temperature is not None else self.config.DEFAULT_TEMPERATURE
        max_tokens = max_tokens or self.config.DEFAULT_MAX_TOKENS

        # Build list of providers to try (primary + fallback chain)
        providers_to_try: List[Dict[str, Any]] = [
            {"provider": provider, "model": model}
        ]
        
        # Add fallback chain
        for fallback in fallback_chain:
            if isinstance(fallback, dict):
                providers_to_try.append({
                    "provider": fallback.get("provider"),
                    "model": fallback.get("model")
                })

        # When USE_REAL_LLM is True, do not use FallbackProvider (fail clearly instead of stub content).
        if self.config.FALLBACK_ENABLED and not getattr(self.config, "USE_REAL_LLM", False):
            providers_to_try.append({"provider": "fallback", "model": "fallback"})

        providers_to_try = self._apply_outbound_guard(providers_to_try)

        # Try each provider in sequence
        last_error = None
        stream_started = False
        
        for attempt in providers_to_try:
            attempt_provider = attempt["provider"]
            attempt_model = attempt["model"]
            
            if not attempt_provider or not attempt_model:
                continue
            
            # Check provider health
            if not self._provider_health.get(attempt_provider, False):
                logger.warning(f"Provider {attempt_provider} is not healthy, skipping")
                continue
            
            provider_instance = self._providers.get(attempt_provider)
            if not provider_instance:
                logger.warning(f"Provider {attempt_provider} not available, skipping")
                continue

            try:
                # Apply rate limiting before starting stream
                if self.rate_limiter and self.config.RATE_LIMIT_ENABLED:
                    try:
                        await self.rate_limiter.check_and_consume(
                            provider=attempt_provider,
                            model_name=attempt_model
                        )
                    except RateLimitError as e:
                        logger.warning(f"Rate limit exceeded for {attempt_provider}: {e}")
                        # Try next provider in chain
                        continue

                # Start streaming
                logger.info(f"Streaming from provider={attempt_provider}, model={attempt_model}")
                stream_started = True
                
                async for chunk in provider_instance.stream(
                    prompt=prompt,
                    system_message=system_message,
                    model_name=attempt_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ):
                    yield chunk
                
                # Stream completed successfully
                logger.info(f"Stream completed successfully from {attempt_provider}/{attempt_model}")
                return

            except Exception as e:
                logger.warning(
                    f"Provider {attempt_provider} streaming failed: {e}, "
                    f"trying next in fallback chain"
                )
                last_error = e
                # Mark provider as unhealthy temporarily
                self._provider_health[attempt_provider] = False
                
                # If streaming already started, we can't fallback cleanly
                # Signal error by raising
                if stream_started:
                    raise RuntimeError(
                        f"Streaming error from {attempt_provider}: {e}. "
                        f"Cannot fallback after streaming has started."
                    )
                continue

        # All providers failed before streaming started
        error_msg = f"All providers failed before streaming started. Last error: {last_error}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)
