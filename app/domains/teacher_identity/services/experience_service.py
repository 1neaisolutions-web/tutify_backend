"""Experience service for teacher employment history."""
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.logging import get_logger
from app.domains.teacher_identity.models import TeacherExperience
from app.domains.teacher_identity.schemas import ExperienceCreate, ExperienceUpdate

logger = get_logger(__name__)


class ExperienceService:
    """Service for managing teacher experience records."""

    def __init__(self, db: Session):
        self.db = db

    def list_experience(self, user_id: UUID) -> List[TeacherExperience]:
        """List all experience records for a user, ordered by start_date descending."""
        return (
            self.db.query(TeacherExperience)
            .filter(TeacherExperience.user_id == user_id)
            .order_by(desc(TeacherExperience.start_date))
            .all()
        )

    def get_experience(self, experience_id: UUID, user_id: UUID) -> Optional[TeacherExperience]:
        """Get a single experience record by id, scoped to user."""
        return (
            self.db.query(TeacherExperience)
            .filter(
                TeacherExperience.id == experience_id,
                TeacherExperience.user_id == user_id,
            )
            .first()
        )

    def create_experience(self, user_id: UUID, data: ExperienceCreate) -> TeacherExperience:
        """Create a new experience record."""
        experience = TeacherExperience(
            user_id=user_id,
            institution_name=data.institution_name,
            role_title=data.role_title,
            subject_area=data.subject_area,
            grade_band=data.grade_band,
            employment_type=data.employment_type.value,
            start_date=data.start_date,
            end_date=data.end_date,
            is_current=data.is_current,
            description=data.description,
            location_city=data.location_city,
            location_country=data.location_country,
        )
        self.db.add(experience)
        self.db.commit()
        self.db.refresh(experience)
        logger.info("Created experience id=%s for user_id=%s", experience.id, user_id)
        return experience

    def update_experience(
        self, experience_id: UUID, user_id: UUID, data: ExperienceUpdate
    ) -> Optional[TeacherExperience]:
        """Update an experience record."""
        experience = self.get_experience(experience_id, user_id)
        if not experience:
            return None
        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if hasattr(experience, key):
                if hasattr(value, "value"):
                    setattr(experience, key, value.value)
                else:
                    setattr(experience, key, value)
        self.db.commit()
        self.db.refresh(experience)
        logger.info("Updated experience id=%s for user_id=%s", experience_id, user_id)
        return experience

    def delete_experience(self, experience_id: UUID, user_id: UUID) -> bool:
        """Delete an experience record."""
        experience = self.get_experience(experience_id, user_id)
        if not experience:
            return False
        self.db.delete(experience)
        self.db.commit()
        logger.info("Deleted experience id=%s for user_id=%s", experience_id, user_id)
        return True
