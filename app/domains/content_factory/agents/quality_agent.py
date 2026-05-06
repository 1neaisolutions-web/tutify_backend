"""
Quality Agent: score generated content (clarity, pedagogical_depth, teacher_usefulness, structure).
Stateless; uses ModelRouter.generate() only.
"""
from typing import Any, Dict

from app.core.logging import get_logger
from app.llm.router import ModelRouter

from app.domains.content_factory.agents._utils import parse_json_from_llm

logger = get_logger(__name__)

QUALITY_SYSTEM = """You are a quality scorer for teacher professional learning content.
Score the content from 0.0 to 1.0 on: clarity, pedagogical_depth, teacher_usefulness, structure_quality.
Also provide an overall quality_score (0.0 to 1.0) and short quality_feedback.
Respond with a single JSON object only. No markdown or explanation outside the JSON.
Required keys: quality_score (number), quality_feedback (string),
clarity (number), pedagogical_depth (number), teacher_usefulness (number), structure_quality (number)."""


async def run_quality_agent(
    router: ModelRouter,
    full_content: Dict[str, Any],
    topic: str,
) -> Dict[str, Any]:
    """
    Score the generated content.
    Returns dict with quality_score, quality_feedback, clarity, pedagogical_depth, teacher_usefulness, structure_quality.
    """
    logger.info("Quality agent step start topic=%s", topic)
    import json
    prompt = (
        f"Topic: {topic}\n\nFull content:\n{json.dumps(full_content, indent=2)}\n\n"
        "Score and respond with JSON: "
        "{\"quality_score\": 0.0-1.0, \"quality_feedback\": \"...\", "
        "\"clarity\": 0.0-1.0, \"pedagogical_depth\": 0.0-1.0, "
        "\"teacher_usefulness\": 0.0-1.0, \"structure_quality\": 0.0-1.0}"
    )
    model_config = {
        "temperature": 0.2,
        "max_tokens": 800,
        "fallback_chain": [{"provider": "anthropic", "model": "claude-3-haiku-20240307"}],
    }
    response = await router.generate(
        system_message=QUALITY_SYSTEM,
        prompt=prompt,
        model_config=model_config,
    )
    logger.info(
        "Quality agent step finish provider=%s model=%s tokens=%s",
        response.provider,
        response.model_used,
        response.token_usage.total if response.token_usage else 0,
    )
    out = parse_json_from_llm(response.content)
    if not out:
        out = {
            "quality_score": 0.0,
            "quality_feedback": "Quality agent did not return valid JSON",
            "clarity": 0.0,
            "pedagogical_depth": 0.0,
            "teacher_usefulness": 0.0,
            "structure_quality": 0.0,
        }
    # Normalize score to 0-1
    score = out.get("quality_score")
    if isinstance(score, (int, float)):
        out["quality_score"] = max(0.0, min(1.0, float(score)))
    return out
