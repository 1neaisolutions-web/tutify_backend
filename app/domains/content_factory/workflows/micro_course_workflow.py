"""
Micro-course generation pipeline: topic -> curriculum -> pedagogy -> structure -> assessment -> review -> quality.
Returns full_content and quality output; does not write to DB or publish.
"""
from typing import Any, Dict, Optional, Tuple

from app.core.logging import get_logger
from app.llm.router import ModelRouter

from app.domains.content_factory.agents import (
    run_assessment_agent,
    run_curriculum_agent,
    run_pedagogy_agent,
    run_quality_agent,
    run_review_agent,
    run_structure_agent,
)

logger = get_logger(__name__)


async def run_micro_course_pipeline(
    router: ModelRouter,
    topic: str,
    subject: Optional[str] = None,
    grade_band: Optional[str] = None,
    difficulty: Optional[str] = None,
    locale: str = "en",
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Run the full agent pipeline. Returns (full_content, quality_output).
    full_content has keys: curriculum, pedagogy, structure, assessment, review, quality.
    """
    logger.info("Micro-course pipeline start topic=%s", topic)
    curriculum = await run_curriculum_agent(
        router, topic=topic, subject=subject, grade_band=grade_band, difficulty=difficulty, locale=locale
    )
    pedagogy = await run_pedagogy_agent(
        router, curriculum=curriculum, topic=topic, grade_band=grade_band
    )
    structure = await run_structure_agent(
        router, curriculum=curriculum, pedagogy=pedagogy, topic=topic
    )
    assessment = await run_assessment_agent(
        router, structure=structure, topic=topic
    )
    full_content = {
        "curriculum": curriculum,
        "pedagogy": pedagogy,
        "structure": structure,
        "assessment": assessment,
    }
    review = await run_review_agent(router, full_content=full_content, topic=topic)
    full_content["review"] = review
    quality = await run_quality_agent(router, full_content=full_content, topic=topic)
    full_content["quality"] = quality
    logger.info("Micro-course pipeline finish topic=%s quality_score=%s", topic, quality.get("quality_score"))
    return full_content, quality
