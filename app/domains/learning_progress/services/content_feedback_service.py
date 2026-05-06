"""Service for managing content feedback."""
from typing import List
from uuid import UUID

from sqlalchemy.orm import Session

from app.domains.learning_progress.models import ContentFeedback
from app.domains.learning_progress.schemas import ContentFeedbackCreate


class ContentFeedbackService:
    def __init__(self, db: Session):
        self.db = db

    def create_feedback(
        self,
        teacher_id: UUID,
        data: ContentFeedbackCreate,
    ) -> ContentFeedback:
        feedback = ContentFeedback(
            teacher_id=teacher_id,
            content_id=data.content_id,
            rating=data.rating,
            difficulty_feedback=data.difficulty_feedback,
            usefulness_feedback=data.usefulness_feedback,
            comment=data.comment,
            feedback_metadata=data.feedback_metadata or {},
        )
        self.db.add(feedback)
        self.db.commit()
        self.db.refresh(feedback)
        return feedback

    def list_feedback_for_content(
        self,
        content_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> List[ContentFeedback]:
        return (
            self.db.query(ContentFeedback)
            .filter(ContentFeedback.content_id == content_id)
            .order_by(ContentFeedback.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def list_feedback_for_teacher(
        self,
        teacher_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> List[ContentFeedback]:
        return (
            self.db.query(ContentFeedback)
            .filter(ContentFeedback.teacher_id == teacher_id)
            .order_by(ContentFeedback.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

