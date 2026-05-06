"""
Service layer for teacher profile context: persist and resolve.
"""
from uuid import UUID
from typing import Optional, List

from sqlalchemy.orm import Session

from app.domains.auth.models import User, TeacherProfileContext, ContextResolutionStatus
from app.domains.external_context.schemas import TeacherContextUpdate
from app.domains.external_context.context_resolver import resolve_profile_context
from app.core.logging import get_logger

logger = get_logger(__name__)


def _ensure_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


class TeacherContextService:
    """Service for upserting teacher context and running resolution."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_user_id(self, user_id: UUID) -> Optional[TeacherProfileContext]:
        """Get teacher profile context for user if exists."""
        return (
            self.db.query(TeacherProfileContext)
            .filter(TeacherProfileContext.user_id == user_id)
            .first()
        )

    def upsert_context(self, user_id: UUID, data: TeacherContextUpdate) -> TeacherProfileContext:
        """
        Create or update teacher profile context and set context_resolution_status.
        """
        ctx = self.get_by_user_id(user_id)

        subjects = _ensure_list(data.subjects)
        professional_goals = _ensure_list(data.professional_goals) if data.professional_goals else []

        resolution_status = resolve_profile_context(
            country=data.country,
            region=data.region,
            curriculum_framework=data.curriculum_framework,
            grade_band=data.grade_band,
        )

        logger.info(
            "teacher_context_resolution user_id=%s country=%s region=%s resolution_status=%s",
            user_id,
            data.country,
            data.region,
            resolution_status,
        )

        if ctx is None:
            ctx = TeacherProfileContext(
                user_id=user_id,
                country=data.country,
                region=data.region,
                school_type=data.school_type,
                grade_band=data.grade_band,
                subjects=subjects,
                language_preference=data.language_preference,
                school_name=data.school_name,
                city=data.city,
                postal_code=data.postal_code,
                curriculum_framework=data.curriculum_framework,
                years_experience=data.years_experience,
                professional_goals=professional_goals if professional_goals else None,
                context_resolution_status=resolution_status,
            )
            self.db.add(ctx)
        else:
            ctx.country = data.country
            ctx.region = data.region
            ctx.school_type = data.school_type
            ctx.grade_band = data.grade_band
            ctx.subjects = subjects
            ctx.language_preference = data.language_preference
            ctx.school_name = data.school_name
            ctx.city = data.city
            ctx.postal_code = data.postal_code
            ctx.curriculum_framework = data.curriculum_framework
            ctx.years_experience = data.years_experience
            ctx.professional_goals = professional_goals if professional_goals else None
            ctx.context_resolution_status = resolution_status

        self.db.commit()
        self.db.refresh(ctx)

        try:
            from app.domains.video_library.cache import invalidate_recommendations

            invalidate_recommendations(user_id)
        except Exception:  # pragma: no cover - defensive, cache must not break profile save
            logger.warning("video_library cache invalidate failed for user_id=%s", user_id, exc_info=True)

        return ctx

    def get_resolution_status(self, user_id: UUID) -> str:
        """Return context_resolution_status for user, or not_found if no context."""
        ctx = self.get_by_user_id(user_id)
        if ctx and ctx.context_resolution_status:
            return ctx.context_resolution_status
        return ContextResolutionStatus.NOT_FOUND.value
