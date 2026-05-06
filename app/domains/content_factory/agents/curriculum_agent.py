"""
Curriculum Agent: topic → structured curriculum plan.
Stateless; uses ModelRouter.generate() only.
"""
from typing import Any, Dict, Optional

from app.core.logging import get_logger
from app.llm.router import ModelRouter

from app.domains.content_factory.agents._utils import parse_json_from_llm

logger = get_logger(__name__)

CURRICULUM_SYSTEM = """You are an expert curriculum designer for K-12 professional learning.
Given a topic and optional context (subject, grade_band, difficulty), produce a structured curriculum plan.
Respond with a single JSON object only. No markdown or explanation outside the JSON.
Required keys: learning_objectives (array of strings), key_concepts (array of strings),
prerequisites (array of strings), target_skills (array of strings)."""


async def run_curriculum_agent(
    router: ModelRouter,
    topic: str,
    subject: Optional[str] = None,
    grade_band: Optional[str] = None,
    difficulty: Optional[str] = None,
    locale: str = "en",
) -> Dict[str, Any]:
    """
    Convert topic and context into a structured curriculum plan.
    Returns dict with learning_objectives, key_concepts, prerequisites, target_skills.
    """
    logger.info("Curriculum agent step start topic=%s", topic)
    context_parts = [f"Topic: {topic}"]
    if subject:
        context_parts.append(f"Subject: {subject}")
    if grade_band:
        context_parts.append(f"Grade band: {grade_band}")
    if difficulty:
        context_parts.append(f"Difficulty: {difficulty}")
    context_parts.append(f"Locale: {locale}")
    prompt = (
        "Create a curriculum plan for the following.\n\n"
        + "\n".join(context_parts)
        + "\n\nRespond with JSON only: {\"learning_objectives\": [...], \"key_concepts\": [...], "
        "\"prerequisites\": [...], \"target_skills\": [...]}"
    )
    model_config = {
        "temperature": 0.3,
        "max_tokens": 1200,
        "fallback_chain": [{"provider": "anthropic", "model": "claude-3-haiku-20240307"}],
    }
    response = await router.generate(
        system_message=CURRICULUM_SYSTEM,
        prompt=prompt,
        model_config=model_config,
    )
    logger.info(
        "Curriculum agent step finish provider=%s model=%s tokens=%s",
        response.provider,
        response.model_used,
        response.token_usage.total if response.token_usage else 0,
    )
    out = parse_json_from_llm(response.content)
    if not out:
        out = {
            "learning_objectives": [],
            "key_concepts": [],
            "prerequisites": [],
            "target_skills": [],
        }
    return out
