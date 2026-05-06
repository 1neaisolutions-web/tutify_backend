"""
Cost tracker for LLM API calls.
"""
from decimal import Decimal
from typing import Dict, Any, Optional

from app.core.logging import get_logger
from app.llm.config import llm_settings
from app.llm.schemas import TokenUsage

logger = get_logger(__name__)


class CostTracker:
    """Tracks and estimates costs for LLM API calls."""

    def __init__(self, pricing: Optional[Dict[str, Any]] = None):
        """
        Initialize cost tracker.

        Args:
            pricing: Pricing dictionary (defaults to MODEL_PRICING_DEFAULTS)
        """
        self.pricing = pricing or llm_settings.get_model_pricing()

    def estimate_cost(
        self,
        provider: str,
        model_name: str,
        token_usage: TokenUsage,
    ) -> Decimal:
        """
        Estimate cost based on token usage and pricing.

        Args:
            provider: Provider name
            model_name: Model name
            token_usage: Token usage information

        Returns:
            Estimated cost in USD (as Decimal)
        """
        # Get pricing for provider
        provider_pricing = self.pricing.get(provider)
        if not provider_pricing:
            logger.warning(f"No pricing found for provider: {provider}")
            return Decimal("0")
        
        # Get pricing for model
        model_pricing = provider_pricing.get(model_name)
        if not model_pricing:
            logger.warning(f"No pricing found for model {model_name} in provider {provider}")
            return Decimal("0")
        
        # Calculate cost: (prompt_tokens / 1000 * input_price) + (completion_tokens / 1000 * output_price)
        input_price = Decimal(str(model_pricing.get("input", 0)))
        output_price = Decimal(str(model_pricing.get("output", 0)))
        
        prompt_cost = (Decimal(token_usage.prompt) / Decimal("1000")) * input_price
        completion_cost = (Decimal(token_usage.completion) / Decimal("1000")) * output_price
        
        total_cost = prompt_cost + completion_cost
        
        return total_cost

