"""
Tests for LLM providers with mocks.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.llm.providers.fallback_provider import FallbackProvider
from app.llm.schemas import LLMResponse


@pytest.mark.asyncio
async def test_fallback_provider_generate():
    """Test FallbackProvider generates deterministic response."""
    provider = FallbackProvider()
    
    response = await provider.generate(
        prompt="Test prompt",
        system_message="System message",
    )
    
    assert response.provider == "fallback"
    assert response.model_used == "fallback"
    assert "fallback response" in response.content.lower()
    assert response.cost_estimate == 0.0


@pytest.mark.asyncio
async def test_fallback_provider_stream():
    """Test FallbackProvider streams response."""
    provider = FallbackProvider()
    
    chunks = []
    async for chunk in provider.stream(
        prompt="Test prompt",
        system_message="System message",
    ):
        chunks.append(chunk)
    
    assert len(chunks) > 0
    assert "".join(chunks) == "This is a fallback response for testing."


def test_fallback_provider_validate_config():
    """Test FallbackProvider always validates successfully."""
    provider = FallbackProvider()
    assert provider.validate_config() is True


@pytest.mark.asyncio
async def test_openai_provider_with_mock():
    """Test OpenAIProvider with mocked client."""
    with patch("app.llm.providers.openai_provider.AsyncOpenAI") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # Mock the response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Mocked OpenAI response"
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 20
        mock_response.usage.total_tokens = 30
        
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        
        from app.llm.providers.openai_provider import OpenAIProvider
        
        # This will fail without API key, but we can test the structure
        # In a real test, you'd mock the settings too
        with patch("app.llm.providers.openai_provider.llm_settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = "test-key"
            mock_settings.DEFAULT_MODEL = "gpt-4o-mini"
            mock_settings.DEFAULT_TEMPERATURE = 0.7
            mock_settings.DEFAULT_MAX_TOKENS = 2000
            
            provider = OpenAIProvider()
            response = await provider.generate(
                prompt="Test",
                system_message="System",
            )
            
            assert response.content == "Mocked OpenAI response"
            assert response.provider == "openai"

