"""
Assessment Agent: add evaluation components to the micro-course.
Stateless; uses ModelRouter.generate() only.
"""
import json
from typing import Any, Dict

from app.core.logging import get_logger
from app.llm.router import ModelRouter

from app.domains.content_factory.agents._utils import parse_json_from_llm

logger = get_logger(__name__)

ASSESSMENT_SYSTEM = """You are an expert in assessment design for professional learning.
Given a micro-course structure, add evaluation components.
Respond with a single JSON object only. Required keys:
practice_tasks (array of objects), reflection_prompts (array of strings),
mini_quizzes (array of objects), rubrics (array of objects)."""


async def run_assessment_agent(
    router: ModelRouter,
    structure: Dict[str, Any],
    topic: str,
) -> Dict[str, Any]:
    """Add assessment components to the course structure."""
    logger.info("Assessment agent step start topic=%s", topic)
    prompt = (
        "Topic: " + topic + "\n\nStructure:\n" + json.dumps(structure, indent=2) + "\n\n"
        "Produce assessment components as JSON: "
        "{\"practice_tasks\": [...], \"reflection_prompts\": [...], "
        "\"mini_quizzes\": [...], \"rubrics\": [...]}"
    )
    model_config = {
        "temperature": 0.3,
        "max_tokens": 1500,
        "fallback_chain": [{"provider": "anthropic", "model": "claude-3-haiku-20240307"}],
    }
    response = await router.generate(
        system_message=ASSESSMENT_SYSTEM,
        prompt=prompt,
        model_config=model_config,
    )
    logger.info(
        "Assessment agent step finish provider=%s model=%s tokens=%s",
        response.provider,
        response.model_used,
        response.token_usage.total if response.token_usage else 0,
    )
    out = parse_json_from_llm(response.content)
    if not out:
        out = {
            "practice_tasks": [],
            "reflection_prompts": [],
            "mini_quizzes": [],
            "rubrics": [],
        }
    return out
