"""Certification service for teacher certifications and licenses."""
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domains.teacher_identity.models import TeacherCertification
from app.domains.teacher_identity.schemas import CertificationCreate, CertificationUpdate

logger = get_logger(__name__)


class CertificationService:
    """Service for managing teacher certification records."""

    def __init__(self, db: Session):
        self.db = db

    def list_certifications(self, user_id: UUID) -> List[TeacherCertification]:
        """List all certification records for a user."""
        return (
            self.db.query(TeacherCertification)
            .filter(TeacherCertification.user_id == user_id)
            .order_by(TeacherCertification.created_at.desc())
            .all()
        )

    def get_certification(
        self, certification_id: UUID, user_id: UUID
    ) -> Optional[TeacherCertification]:
        """Get a single certification record by id, scoped to user."""
        return (
            self.db.query(TeacherCertification)
            .filter(
                TeacherCertification.id == certification_id,
                TeacherCertification.user_id == user_id,
            )
            .first()
        )

    def create_certification(
        self, user_id: UUID, data: CertificationCreate
    ) -> TeacherCertification:
        """Create a new certification record."""
        certification = TeacherCertification(
            user_id=user_id,
            name=data.name,
            issuer=data.issuer,
            license_number=data.license_number,
            issue_date=data.issue_date,
            expiry_date=data.expiry_date,
            credential_url=data.credential_url,
            document_id=data.document_id,
        )
        self.db.add(certification)
        self.db.commit()
        self.db.refresh(certification)
        logger.info("Created certification id=%s for user_id=%s", certification.id, user_id)
        return certification

    def update_certification(
        self, certification_id: UUID, user_id: UUID, data: CertificationUpdate
    ) -> Optional[TeacherCertification]:
        """Update a certification record."""
        certification = self.get_certification(certification_id, user_id)
        if not certification:
            return None
        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if hasattr(certification, key):
                setattr(certification, key, value)
        self.db.commit()
        self.db.refresh(certification)
        logger.info("Updated certification id=%s for user_id=%s", certification_id, user_id)
        return certification

    def delete_certification(self, certification_id: UUID, user_id: UUID) -> bool:
        """Delete a certification record."""
        certification = self.get_certification(certification_id, user_id)
        if not certification:
            return False
        self.db.delete(certification)
        self.db.commit()
        logger.info("Deleted certification id=%s for user_id=%s", certification_id, user_id)
        return True
