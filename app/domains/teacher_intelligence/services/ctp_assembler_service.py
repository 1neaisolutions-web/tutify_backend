"""
CTP Assembler: builds Comprehensive Teacher Profile from users, teacher_profile_context, teacher_identity.
Read-only aggregation; does not modify any source domain.
"""
from typing import Any, Dict
from uuid import UUID

from sqlalchemy.orm import Session

from app.domains.auth.models import User, TeacherProfileContext
from app.domains.teacher_identity.models import (
    TeacherExperience,
    TeacherEducation,
    TeacherCertification,
    TeacherAchievement,
    TeacherCareerDocument,
)
from app.core.logging import get_logger

logger = get_logger(__name__)

PROFILE_VERSION = "ctp_v1"


class CTPAssemblerService:
    """Builds a canonical Comprehensive Teacher Profile (CTP) from multiple domains."""

    def __init__(self, db: Session):
        self.db = db

    def assemble(self, teacher_id: UUID) -> Dict[str, Any]:
        """
        Build CTP dict from users, teacher_profile_context, teacher_identity.
        Returns a structured dict suitable for feature snapshot and ML.
        """
        user = self.db.query(User).filter(User.id == teacher_id).first()
        if not user:
            logger.warning("CTP assemble: user not found teacher_id=%s", teacher_id)
            return self._empty_ctp(teacher_id)

        ctx = (
            self.db.query(TeacherProfileContext)
            .filter(TeacherProfileContext.user_id == teacher_id)
            .first()
        )

        experiences = (
            self.db.query(TeacherExperience)
            .filter(TeacherExperience.user_id == teacher_id)
            .order_by(TeacherExperience.start_date.desc())
            .all()
        )
        education = (
            self.db.query(TeacherEducation).filter(TeacherEducation.user_id == teacher_id).all()
        )
        certifications = (
            self.db.query(TeacherCertification)
            .filter(TeacherCertification.user_id == teacher_id)
            .all()
        )
        achievements = (
            self.db.query(TeacherAchievement)
            .filter(TeacherAchievement.user_id == teacher_id)
            .all()
        )
        documents = (
            self.db.query(TeacherCareerDocument)
            .filter(TeacherCareerDocument.user_id == teacher_id)
            .all()
        )

        current_role = None
        for exp in experiences:
            if getattr(exp, "is_current", False):
                current_role = exp.role_title
                break

        if ctx is None:
            identity = {
                "country": "",
                "region": "",
                "subjects": [],
                "grade_band": "",
                "language_preference": "",
            }
            environment = {
                "school_type": "",
                "curriculum_framework": None,
                "years_experience": None,
                "school_name": None,
            }
            goals = []
        else:
            subjects = ctx.subjects if isinstance(ctx.subjects, list) else []
            identity = {
                "country": ctx.country or "",
                "region": ctx.region or "",
                "subjects": subjects,
                "grade_band": ctx.grade_band or "",
                "language_preference": ctx.language_preference or "",
            }
            environment = {
                "school_type": ctx.school_type or "",
                "curriculum_framework": getattr(ctx, "curriculum_framework", None) or None,
                "years_experience": getattr(ctx, "years_experience", None) or None,
                "school_name": getattr(ctx, "school_name", None) or None,
            }
            goals = (
                list(ctx.professional_goals)
                if getattr(ctx, "professional_goals", None) and isinstance(ctx.professional_goals, list)
                else []
            )

        document_types = [getattr(d, "document_type", "") for d in documents]
        highest_degree = None
        if education:
            def _deg_level(deg):
                d = (deg or "").lower()
                if "phd" in d or "doctoral" in d or "doctorate" in d: return 4
                if "master" in d or "ms " in d or "ma " in d or "m.ed" in d or "mba" in d: return 3
                if "bachelor" in d or "ba " in d or "bs " in d or "b.ed" in d: return 2
                if "associate" in d: return 1
                return 0
            best = max(education, key=lambda e: _deg_level(getattr(e, "degree", None)))
            highest_degree = getattr(best, "degree", None)
        career = {
            "experience_records": len(experiences),
            "current_role": current_role,
            "certifications_count": len(certifications),
            "education_count": len(education),
            "achievements_count": len(achievements),
            "documents_count": len(documents),
            "document_types": document_types,
            "highest_degree": highest_degree,
        }

        ctp = {
            "teacher_id": str(teacher_id),
            "profile_version": PROFILE_VERSION,
            "identity": identity,
            "environment": environment,
            "career": career,
            "goals": goals,
        }
        logger.debug("CTP assembled for teacher_id=%s", teacher_id)
        return ctp

    def _empty_ctp(self, teacher_id: UUID) -> Dict[str, Any]:
        """Return minimal CTP when user not found (caller may still 404)."""
        return {
            "teacher_id": str(teacher_id),
            "profile_version": PROFILE_VERSION,
            "identity": {
                "country": "",
                "region": "",
                "subjects": [],
                "grade_band": "",
                "language_preference": "",
            },
            "environment": {
                "school_type": "",
                "curriculum_framework": None,
                "years_experience": None,
                "school_name": None,
            },
            "career": {
                "experience_records": 0,
                "current_role": None,
                "certifications_count": 0,
                "education_count": 0,
                "achievements_count": 0,
                "documents_count": 0,
                "document_types": [],
                "highest_degree": None,
            },
            "goals": [],
        }
