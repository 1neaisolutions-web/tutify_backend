"""
Google provider implementation.
"""
import time
from typing import Optional, Dict, Any, AsyncIterator

import google.generativeai as genai

from app.core.logging import get_logger
from app.llm.base import BaseProvider
from app.llm.config import llm_settings
from app.llm.schemas import LLMResponse, TokenUsage

logger = get_logger(__name__)


class GoogleProvider(BaseProvider):
    """Google provider implementation."""

    provider_name = "google"

    def __init__(self):
        """Initialize Google provider with API key from settings."""
        if not llm_settings.GOOGLE_API_KEY:
            raise ValueError("GOOGLE_API_KEY not set in environment variables")
        
        genai.configure(api_key=llm_settings.GOOGLE_API_KEY)
        self.default_model = "gemini-pro"
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
        Generate a response using Google Gemini API.

        Args:
            prompt: The user prompt
            system_message: Optional system message (combined with prompt for Gemini)
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
            model = genai.GenerativeModel(model_name)
            
            # Combine system message and prompt for Gemini
            full_prompt = prompt
            if system_message:
                full_prompt = f"{system_message}\n\n{prompt}"
            
            generation_config = genai.types.GenerationConfig(
                temperature=temp,
                max_output_tokens=max_toks,
            )
            
            response = await model.generate_content_async(
                full_prompt,
                generation_config=generation_config,
                **kwargs
            )
            
            # Extract response content
            content = response.text if response.text else ""
            
            # Extract token usage (if available)
            prompt_tokens = 0
            completion_tokens = 0
            if hasattr(response, 'usage_metadata'):
                usage = response.usage_metadata
                prompt_tokens = usage.prompt_token_count if usage else 0
                completion_tokens = usage.candidates_token_count if usage else 0
            
            token_usage = TokenUsage(
                prompt=prompt_tokens,
                completion=completion_tokens,
                total=prompt_tokens + completion_tokens
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
            logger.error(f"Google API error: {e}")
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
        Stream a response using Google Gemini API.

        NOTE: Currently simulates streaming by calling generate and yielding full content.
        This is a temporary behavior until proper streaming API is available.
        """
        # TODO: Implement proper streaming when Google Gemini streaming API is available
        # For now, simulate streaming by yielding the full response as one chunk
        response = await self.generate(
            prompt=prompt,
            system_message=system_message,
            model_name=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
        yield response.content

    def validate_config(self) -> bool:
        """Return True if provider is properly configured."""
        return bool(llm_settings.GOOGLE_API_KEY)

    def get_model_info(self, model_name: str) -> Optional[Dict[str, Any]]:
        """Return supported model metadata or None."""
        supported_models = {
            "gemini-pro": {"max_tokens": 8192, "context_window": 32768},
            "gemini-1.5-pro": {"max_tokens": 8192, "context_window": 1000000},
        }
        return supported_models.get(model_name)

