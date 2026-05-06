"""
Review Agent: validate coherence of generated content.
Stateless; uses ModelRouter.generate() only.
"""
import json
from typing import Any, Dict

from app.core.logging import get_logger
from app.llm.router import ModelRouter

from app.domains.content_factory.agents._utils import parse_json_from_llm

logger = get_logger(__name__)

REVIEW_SYSTEM = """You are a quality reviewer for educational micro-courses.
Validate coherence: module completeness, concept duplication, length, instructional flow.
Respond with a single JSON object only. Required keys:
review_status (\"approved\" or \"needs_revision\"), issues_found (array), improvement_notes (array)."""


async def run_review_agent(
    router: ModelRouter,
    full_content: Dict[str, Any],
    topic: str,
) -> Dict[str, Any]:
    """Validate coherence of the full generated content."""
    logger.info("Review agent step start topic=%s", topic)
    prompt = (
        "Topic: " + topic + "\n\nFull content:\n" + json.dumps(full_content, indent=2) + "\n\n"
        "Review and respond with JSON: "
        "{\"review_status\": \"approved\" or \"needs_revision\", "
        "\"issues_found\": [...], \"improvement_notes\": [...]}"
    )
    model_config = {
        "temperature": 0.2,
        "max_tokens": 1000,
        "fallback_chain": [{"provider": "anthropic", "model": "claude-3-haiku-20240307"}],
    }
    response = await router.generate(
        system_message=REVIEW_SYSTEM,
        prompt=prompt,
        model_config=model_config,
    )
    logger.info(
        "Review agent step finish provider=%s model=%s tokens=%s",
        response.provider,
        response.model_used,
        response.token_usage.total if response.token_usage else 0,
    )
    out = parse_json_from_llm(response.content)
    if not out:
        out = {
            "review_status": "needs_revision",
            "issues_found": ["Review agent did not return valid JSON"],
            "improvement_notes": [],
        }
    return out
