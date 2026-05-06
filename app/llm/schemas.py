"""
Pydantic schemas for LLM responses and token usage.
"""
from typing import Optional

from pydantic import BaseModel


class TokenUsage(BaseModel):
    """Token usage information from LLM response."""

    prompt: int = 0
    completion: int = 0
    total: int = 0


class LLMResponse(BaseModel):
    """Response from LLM provider."""

    content: str
    model_used: str
    provider: str
    token_usage: Optional[TokenUsage] = None
    cost_estimate: Optional[float] = None
    latency_ms: int
    cache_hit: bool = False

