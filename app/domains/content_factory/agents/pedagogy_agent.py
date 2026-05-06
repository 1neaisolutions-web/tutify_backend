"""
Pedagogy Agent: curriculum plan to teaching approach.
Stateless; uses ModelRouter.generate() only.
"""
import json
from typing import Any, Dict, Optional

from app.core.logging import get_logger
from app.llm.router import ModelRouter

from app.domains.content_factory.agents._utils import parse_json_from_llm

logger = get_logger(__name__)

PEDAGOGY_SYSTEM = """You are an expert in pedagogy and instructional design for teachers.
Given a curriculum plan (objectives, concepts, prerequisites, skills), produce a teaching approach.
Respond with a single JSON object only. No markdown or explanation outside the JSON.
Required keys: instructional_flow (array of strings), examples (array of strings),
teaching_strategies (array of strings), teacher_reflections (array of strings)."""


async def run_pedagogy_agent(
    router: ModelRouter,
    curriculum: Dict[str, Any],
    topic: str,
    grade_band: Optional[str] = None,
) -> Dict[str, Any]:
    """Transform curriculum into teaching approach."""
    logger.info("Pedagogy agent step start topic=%s", topic)
    curriculum_str = json.dumps(curriculum, indent=2)
    prompt = (
        "Curriculum plan for topic \"" + topic + "\":\n" + curriculum_str + "\n\n"
        "Grade band: " + (grade_band or "not specified") + "\n\n"
        "Produce teaching approach as JSON: "
        "{\"instructional_flow\": [...], \"examples\": [...], "
        "\"teaching_strategies\": [...], \"teacher_reflections\": [...]}"
    )
    model_config = {
        "temperature": 0.3,
        "max_tokens": 1500,
        "fallback_chain": [{"provider": "anthropic", "model": "claude-3-haiku-20240307"}],
    }
    response = await router.generate(
        system_message=PEDAGOGY_SYSTEM,
        prompt=prompt,
        model_config=model_config,
    )
    logger.info(
        "Pedagogy agent step finish provider=%s model=%s tokens=%s",
        response.provider,
        response.model_used,
        response.token_usage.total if response.token_usage else 0,
    )
    out = parse_json_from_llm(response.content)
    if not out:
        out = {
            "instructional_flow": [],
            "examples": [],
            "teaching_strategies": [],
            "teacher_reflections": [],
        }
    return out
