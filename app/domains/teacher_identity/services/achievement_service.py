"""Achievement service for teacher awards and recognitions."""
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.logging import get_logger
from app.domains.teacher_identity.models import TeacherAchievement
from app.domains.teacher_identity.schemas import AchievementCreate, AchievementUpdate

logger = get_logger(__name__)


class AchievementService:
    """Service for managing teacher achievement records."""

    def __init__(self, db: Session):
        self.db = db

    def list_achievements(self, user_id: UUID) -> List[TeacherAchievement]:
        """List all achievement records for a user, ordered by date descending."""
        return (
            self.db.query(TeacherAchievement)
            .filter(TeacherAchievement.user_id == user_id)
            .order_by(desc(TeacherAchievement.date), desc(TeacherAchievement.created_at))
            .all()
        )

    def get_achievement(
        self, achievement_id: UUID, user_id: UUID
    ) -> Optional[TeacherAchievement]:
        """Get a single achievement record by id, scoped to user."""
        return (
            self.db.query(TeacherAchievement)
            .filter(
                TeacherAchievement.id == achievement_id,
                TeacherAchievement.user_id == user_id,
            )
            .first()
        )

    def create_achievement(
        self, user_id: UUID, data: AchievementCreate
    ) -> TeacherAchievement:
        """Create a new achievement record."""
        achievement = TeacherAchievement(
            user_id=user_id,
            title=data.title,
            organization=data.organization,
            date=data.date,
            description=data.description,
        )
        self.db.add(achievement)
        self.db.commit()
        self.db.refresh(achievement)
        logger.info("Created achievement id=%s for user_id=%s", achievement.id, user_id)
        return achievement

    def update_achievement(
        self, achievement_id: UUID, user_id: UUID, data: AchievementUpdate
    ) -> Optional[TeacherAchievement]:
        """Update an achievement record."""
        achievement = self.get_achievement(achievement_id, user_id)
        if not achievement:
            return None
        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if hasattr(achievement, key):
                setattr(achievement, key, value)
        self.db.commit()
        self.db.refresh(achievement)
        logger.info(
            "Updated achievement id=%s for user_id=%s", achievement_id, user_id
        )
        return achievement

    def delete_achievement(self, achievement_id: UUID, user_id: UUID) -> bool:
        """Delete an achievement record."""
        achievement = self.get_achievement(achievement_id, user_id)
        if not achievement:
            return False
        self.db.delete(achievement)
        self.db.commit()
        logger.info(
            "Deleted achievement id=%s for user_id=%s", achievement_id, user_id
        )
        return True
