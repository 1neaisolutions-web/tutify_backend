"""
Tests for ModelRouter with mocked providers.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.llm.router import ModelRouter
from app.llm.config import llm_settings
from app.llm.schemas import LLMResponse, TokenUsage


@pytest.fixture
def mock_openai_provider():
    """Create a mocked OpenAI provider."""
    provider = MagicMock()
    provider.provider_name = "openai"
    provider.validate_config = MagicMock(return_value=True)
    provider.get_model_info = MagicMock(return_value=None)
    
    # Mock generate method
    async def mock_generate(*args, **kwargs):
        return LLMResponse(
            content="Test response",
            model_used="gpt-4o-mini",
            provider="openai",
            token_usage=TokenUsage(prompt=10, completion=20, total=30),
            cost_estimate=None,
            latency_ms=100,
            cache_hit=False,
        )
    provider.generate = AsyncMock(side_effect=mock_generate)
    
    # Mock stream method
    async def mock_stream(*args, **kwargs):
        chunks = ["Test ", "response ", "content"]
        for chunk in chunks:
            yield chunk
    provider.stream = AsyncMock(side_effect=mock_stream)
    
    return provider


@pytest.fixture
def mock_router(mock_openai_provider):
    """Create a ModelRouter with mocked providers."""
    router = ModelRouter(config=llm_settings)
    router._providers = {"openai": mock_openai_provider}
    router._provider_health = {"openai": True}
    return router


@pytest.mark.asyncio
async def test_router_generate_calls_provider(mock_router, mock_openai_provider):
    """Test that router.generate calls the provider's generate method."""
    response = await mock_router.generate(
        system_message="You are a helpful assistant.",
        prompt="Test prompt",
        model_config={"provider": "openai", "model": "gpt-4o-mini"},
    )
    
    assert response is not None
    assert response.content == "Test response"
    assert response.provider == "openai"
    mock_openai_provider.generate.assert_called_once()


@pytest.mark.asyncio
async def test_router_stream_yields_chunks(mock_router, mock_openai_provider):
    """Test that router.stream yields chunks from provider."""
    chunks = []
    async for chunk in mock_router.stream(
        system_message="System message",
        prompt="Test prompt",
        model_config={"provider": "openai", "model": "gpt-4o-mini"},
    ):
        chunks.append(chunk)
    
    assert len(chunks) == 3
    assert chunks == ["Test ", "response ", "content"]
    mock_openai_provider.stream.assert_called_once()


@pytest.mark.asyncio
async def test_router_fallback_on_provider_failure(mock_router, mock_openai_provider):
    """Test that router falls back to next provider when primary fails."""
    # Make primary provider fail
    mock_openai_provider.generate.side_effect = Exception("Provider error")
    mock_openai_provider.validate_config.return_value = False
    mock_router._provider_health["openai"] = False
    
    # Add fallback provider
    mock_fallback = MagicMock()
    mock_fallback.provider_name = "fallback"
    mock_fallback.validate_config = MagicMock(return_value=True)
    mock_fallback.get_model_info = MagicMock(return_value=None)
    
    async def fallback_generate(*args, **kwargs):
        return LLMResponse(
            content="Fallback response",
            model_used="fallback",
            provider="fallback",
            token_usage=TokenUsage(prompt=0, completion=0, total=0),
            latency_ms=10,
            cache_hit=False,
        )
    mock_fallback.generate = AsyncMock(side_effect=fallback_generate)
    
    mock_router._providers["fallback"] = mock_fallback
    mock_router._provider_health["fallback"] = True
    
    # Should use fallback
    response = await mock_router.generate(
        system_message="Test",
        prompt="Test",
        model_config={"provider": "openai", "model": "gpt-4o-mini", "fallback_chain": [{"provider": "fallback", "model": "fallback"}]},
    )
    
    assert response.provider == "fallback"
    assert response.content == "Fallback response"

