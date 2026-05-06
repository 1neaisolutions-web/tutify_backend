"""Education service for teacher academic background."""
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.logging import get_logger
from app.domains.teacher_identity.models import TeacherEducation
from app.domains.teacher_identity.schemas import EducationCreate, EducationUpdate

logger = get_logger(__name__)


class EducationService:
    """Service for managing teacher education records."""

    def __init__(self, db: Session):
        self.db = db

    def list_education(self, user_id: UUID) -> List[TeacherEducation]:
        """List all education records for a user, ordered by end_year descending."""
        return (
            self.db.query(TeacherEducation)
            .filter(TeacherEducation.user_id == user_id)
            .order_by(desc(TeacherEducation.end_year), desc(TeacherEducation.start_year))
            .all()
        )

    def get_education(self, education_id: UUID, user_id: UUID) -> Optional[TeacherEducation]:
        """Get a single education record by id, scoped to user."""
        return (
            self.db.query(TeacherEducation)
            .filter(
                TeacherEducation.id == education_id,
                TeacherEducation.user_id == user_id,
            )
            .first()
        )

    def create_education(self, user_id: UUID, data: EducationCreate) -> TeacherEducation:
        """Create a new education record."""
        education = TeacherEducation(
            user_id=user_id,
            institution_name=data.institution_name,
            degree=data.degree,
            field_of_study=data.field_of_study,
            start_year=data.start_year,
            end_year=data.end_year,
            is_completed=data.is_completed,
            description=data.description,
        )
        self.db.add(education)
        self.db.commit()
        self.db.refresh(education)
        logger.info("Created education id=%s for user_id=%s", education.id, user_id)
        return education

    def update_education(
        self, education_id: UUID, user_id: UUID, data: EducationUpdate
    ) -> Optional[TeacherEducation]:
        """Update an education record."""
        education = self.get_education(education_id, user_id)
        if not education:
            return None
        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if hasattr(education, key):
                setattr(education, key, value)
        self.db.commit()
        self.db.refresh(education)
        logger.info("Updated education id=%s for user_id=%s", education_id, user_id)
        return education

    def delete_education(self, education_id: UUID, user_id: UUID) -> bool:
        """Delete an education record."""
        education = self.get_education(education_id, user_id)
        if not education:
            return False
        self.db.delete(education)
        self.db.commit()
        logger.info("Deleted education id=%s for user_id=%s", education_id, user_id)
        return True
