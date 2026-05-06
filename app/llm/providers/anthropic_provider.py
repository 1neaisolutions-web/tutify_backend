"""
Anthropic provider implementation.
"""
import time
from typing import Optional, Dict, Any, AsyncIterator

import anthropic

from app.core.logging import get_logger
from app.llm.base import BaseProvider
from app.llm.config import llm_settings
from app.llm.schemas import LLMResponse, TokenUsage

logger = get_logger(__name__)


class AnthropicProvider(BaseProvider):
    """Anthropic provider implementation."""

    provider_name = "anthropic"

    def __init__(self):
        """Initialize Anthropic provider with API key from settings."""
        if not llm_settings.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY not set in environment variables")
        
        self.client = anthropic.AsyncAnthropic(api_key=llm_settings.ANTHROPIC_API_KEY)
        self.default_model = "claude-3-haiku-20240307"
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
        Generate a response using Anthropic API.

        Args:
            prompt: The user prompt
            system_message: Optional system message
            model_name: Model to use
            temperature: Temperature setting
            max_tokens: Max tokens
            **kwargs: Additional parameters

        Returns:
            LLMResponse with content, model_used, provider, token_usage, latency_ms
        """
        start_time = time.monotonic()
        
        model_name = model_name or self.default_model
        temp = temperature if temperature is not None else self.default_temperature
        max_toks = max_tokens or self.default_max_tokens
        
        try:
            response = await self.client.messages.create(
                model=model_name,
                max_tokens=max_toks,
                temperature=temp,
                system=system_message or "",
                messages=[
                    {"role": "user", "content": prompt}
                ],
                **kwargs
            )
            
            # Extract response content
            content = ""
            if response.content:
                for block in response.content:
                    if hasattr(block, 'text'):
                        content += block.text
            
            # Extract token usage
            token_usage = TokenUsage(
                prompt=response.usage.input_tokens if response.usage else 0,
                completion=response.usage.output_tokens if response.usage else 0,
                total=(response.usage.input_tokens + response.usage.output_tokens) if response.usage else 0
            )
            
            # Calculate latency
            latency_ms = int((time.monotonic() - start_time) * 1000)
            
            return LLMResponse(
                content=content,
                model_used=model_name,
                provider=self.provider_name,
                token_usage=token_usage,
                cost_estimate=None,  # Set by CostTracker
                latency_ms=latency_ms
            )
            
        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
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
        Stream a response using Anthropic API.

        Yields raw text chunks as they arrive from Anthropic.
        """
        model_name = model_name or self.default_model
        temp = temperature if temperature is not None else self.default_temperature
        max_toks = max_tokens or self.default_max_tokens
        
        try:
            async with self.client.messages.stream(
                model=model_name,
                max_tokens=max_toks,
                temperature=temp,
                system=system_message or "",
                messages=[
                    {"role": "user", "content": prompt}
                ],
                **kwargs
            ) as stream:
                async for text_event in stream.text_stream:
                    if text_event:
                        yield text_event
                        
        except Exception as e:
            logger.error(f"Anthropic streaming error: {e}")
            raise

    def validate_config(self) -> bool:
        """Return True if provider is properly configured."""
        return bool(llm_settings.ANTHROPIC_API_KEY)

    def get_model_info(self, model_name: str) -> Optional[Dict[str, Any]]:
        """Return supported model metadata or None."""
        supported_models = {
            "claude-3-opus-20240229": {"max_tokens": 4096, "context_window": 200000},
            "claude-3-sonnet-20240229": {"max_tokens": 4096, "context_window": 200000},
            "claude-3-haiku-20240307": {"max_tokens": 4096, "context_window": 200000},
        }
        return supported_models.get(model_name)

