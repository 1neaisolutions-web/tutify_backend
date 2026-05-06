"""
OpenAI provider implementation.
"""
import time
from typing import Optional, Dict, Any, AsyncIterator

from openai import OpenAI, AsyncOpenAI

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore

from app.core.logging import get_logger
from app.llm.base import BaseProvider
from app.llm.config import llm_settings
from app.llm.schemas import LLMResponse, TokenUsage

logger = get_logger(__name__)


class OpenAIProvider(BaseProvider):
    """OpenAI provider implementation."""

    provider_name = "openai"

    def __init__(self):
        """Initialize OpenAI provider with API key from settings."""
        if getattr(llm_settings, "OPENAI_EMBEDDINGS_ONLY_MODE", False):
            raise ValueError(
                "OpenAI non-embedding usage is disabled (OPENAI_EMBEDDINGS_ONLY_MODE=true)."
            )
        if not llm_settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY not set in environment variables")
        
        # Support custom base URL if provided (correct common typo opeanai -> openai without changing .env)
        client_kwargs = {"api_key": llm_settings.OPENAI_API_KEY}
        if hasattr(llm_settings, "OPENAI_BASE_URL") and llm_settings.OPENAI_BASE_URL:
            base_url = llm_settings.OPENAI_BASE_URL.strip()
            if "opeanai" in base_url.lower():
                base_url = base_url.replace("opeanai", "openai").replace("OPEANAI", "openai")
            client_kwargs["base_url"] = base_url
        # Connect and read timeouts so we never hang
        connect_timeout = getattr(llm_settings, "OPENAI_CONNECT_TIMEOUT", 10.0)
        read_timeout = getattr(llm_settings, "OPENAI_READ_TIMEOUT", 60.0)
        if httpx is not None:
            client_kwargs["timeout"] = httpx.Timeout(connect_timeout, read=read_timeout)
        else:
            client_kwargs["timeout"] = read_timeout

        self.client = AsyncOpenAI(**client_kwargs)
        self.default_model = llm_settings.DEFAULT_MODEL
        self.default_temperature = llm_settings.DEFAULT_TEMPERATURE
        self.default_max_tokens = llm_settings.DEFAULT_MAX_TOKENS

    async def generate(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        model_name: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> LLMResponse:
        """
        Generate a response using OpenAI API.

        Args:
            prompt: The user prompt
            system_message: Optional system message
            model_name: Model to use (defaults to configured default)
            temperature: Temperature setting (defaults to configured default)
            max_tokens: Max tokens (defaults to configured default)
            **kwargs: Additional parameters passed to OpenAI API

        Returns:
            LLMResponse with content, model_used, provider, token_usage, latency_ms
        """
        start_time = time.monotonic()
        
        # Build messages
        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": prompt})
        
        # Use provided parameters or defaults
        model_name = model_name or self.default_model
        temp = temperature if temperature is not None else self.default_temperature
        max_toks = max_tokens or self.default_max_tokens
        
        try:
            response = await self.client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=temp,
                max_tokens=max_toks,
                **kwargs
            )
            
            # Extract response content
            content = response.choices[0].message.content or ""
            
            # Extract token usage
            usage = response.usage
            token_usage = TokenUsage(
                prompt=usage.prompt_tokens if usage else 0,
                completion=usage.completion_tokens if usage else 0,
                total=usage.total_tokens if usage else 0
            )
            
            # Calculate latency
            latency_ms = int((time.monotonic() - start_time) * 1000)
            
            # Cost estimate will be set by CostTracker
            cost_estimate = None
            
            return LLMResponse(
                content=content,
                model_used=model_name,
                provider=self.provider_name,
                token_usage=token_usage,
                cost_estimate=cost_estimate,
                latency_ms=latency_ms
            )
            
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise

    async def stream(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        model_name: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        """
        Stream a response using OpenAI API.

        Yields raw text chunks as they arrive from OpenAI.
        """
        # Build messages
        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": prompt})
        
        # Use provided parameters or defaults
        model_name = model_name or self.default_model
        temp = temperature if temperature is not None else self.default_temperature
        max_toks = max_tokens or self.default_max_tokens
        
        try:
            stream = await self.client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=temp,
                max_tokens=max_toks,
                stream=True,  # Enable streaming
                **kwargs
            )
            
            # CRITICAL: Yield every chunk immediately - no filtering, no buffering
            # Activity does this exactly - yield delta.content as-is
            async for chunk in stream:
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    # CRITICAL: Check delta exists and has content (Activity does this)
                    if delta and delta.content:
                        # Yield immediately - don't modify, don't filter
                        # Activity yields delta.content directly (line 287 in llm_client.py)
                        yield delta.content
                        
        except Exception as e:
            logger.error(f"OpenAI streaming error: {e}")
            raise

    def validate_config(self) -> bool:
        """Return True if provider is properly configured."""
        return bool(llm_settings.OPENAI_API_KEY)

    def get_model_info(self, model_name: str) -> Optional[Dict[str, Any]]:
        """Return supported model metadata or None."""
        supported_models = {
            "gpt-4o": {"max_tokens": 128000, "context_window": 128000},
            "gpt-4o-mini": {"max_tokens": 128000, "context_window": 128000},
            "gpt-4": {"max_tokens": 8192, "context_window": 8192},
            "gpt-3.5-turbo": {"max_tokens": 16385, "context_window": 16385},
        }
        return supported_models.get(model_name)
