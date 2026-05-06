"""
Structure Agent: pedagogy plan → micro-course structure (modules, lessons, steps, activities).
Stateless; uses ModelRouter.generate() only.
"""
from typing import Any, Dict

from app.core.logging import get_logger
from app.llm.router import ModelRouter

from app.domains.content_factory.agents._utils import parse_json_from_llm

logger = get_logger(__name__)

STRUCTURE_SYSTEM = """You are an expert in designing micro-course structure for teacher professional development.
Given a curriculum and pedagogy plan, produce a concrete micro-course structure.
Respond with a single JSON object only. No markdown or explanation outside the JSON.
Required keys: modules (array of objects with title, summary, order),
lessons (array of objects with module_id or order, title, duration_min),
steps (array of objects for lesson steps: lesson_id, title, type, content_summary),
activities (array of objects: step_id, type, description). Use consistent ids or order for linking."""


async def run_structure_agent(
    router: ModelRouter,
    curriculum: Dict[str, Any],
    pedagogy: Dict[str, Any],
    topic: str,
) -> Dict[str, Any]:
    """
    Convert curriculum + pedagogy into micro-course structure.
    Returns dict with modules, lessons, steps, activities.
    """
    logger.info("Structure agent step start topic=%s", topic)
    import json
    prompt = (
        f"Topic: {topic}\n\nCurriculum:\n{json.dumps(curriculum, indent=2)}\n\n"
        f"Pedagogy:\n{json.dumps(pedagogy, indent=2)}\n\n"
        "Produce micro-course structure as JSON: "
        "{\"modules\": [...], \"lessons\": [...], \"steps\": [...], \"activities\": [...]}"
    )
    model_config = {
        "temperature": 0.3,
        "max_tokens": 2000,
        "fallback_chain": [{"provider": "anthropic", "model": "claude-3-haiku-20240307"}],
    }
    response = await router.generate(
        system_message=STRUCTURE_SYSTEM,
        prompt=prompt,
        model_config=model_config,
    )
    logger.info(
        "Structure agent step finish provider=%s model=%s tokens=%s",
        response.provider,
        response.model_used,
        response.token_usage.total if response.token_usage else 0,
    )
    out = parse_json_from_llm(response.content)
    if not out:
        out = {"modules": [], "lessons": [], "steps": [], "activities": []}
    return out
