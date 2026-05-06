"""
Base provider abstract class for LLM providers.
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, AsyncIterator

from app.llm.schemas import LLMResponse


class BaseProvider(ABC):
    """Abstract base class for LLM providers."""

    provider_name: str  # e.g. "openai", "anthropic", "google", "fallback"

    @abstractmethod
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
        Generate a response from the LLM.

        Args:
            prompt: The user prompt
            system_message: Optional system message
            model_name: Model to use
            temperature: Temperature setting
            max_tokens: Maximum tokens
            **kwargs: Additional provider-specific parameters

        Returns:
            LLMResponse with content, model_used, provider, token_usage, etc.
        """
        pass

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
        Stream a response from the LLM, yielding raw text chunks.

        Args:
            prompt: The user prompt
            system_message: Optional system message
            model_name: Model to use
            temperature: Temperature setting
            max_tokens: Maximum tokens
            **kwargs: Additional provider-specific parameters

        Yields:
            Raw text chunks (plain strings) as they arrive from the LLM
        """
        # Default implementation: call generate and yield full content as one chunk
        # Providers should override this for true streaming
        response = await self.generate(
            prompt=prompt,
            system_message=system_message,
            model_name=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
        yield response.content

    @abstractmethod
    def validate_config(self) -> bool:
        """Return True if provider is properly configured (API key present, etc.)."""
        pass

    @abstractmethod
    def get_model_info(self, model_name: str) -> Optional[Dict[str, Any]]:
        """Optional: return supported model metadata or None."""
        pass

