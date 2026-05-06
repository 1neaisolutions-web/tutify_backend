"""Career document upload and management service."""
from pathlib import Path
from typing import List, Optional
from uuid import UUID, uuid4
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.domains.teacher_identity.models import TeacherCareerDocument
from app.domains.teacher_identity.enums import CareerDocumentType, CareerDocumentStatus

logger = get_logger(__name__)


class CareerDocumentServiceError(Exception):
    """Raised when document validation or storage fails."""
    pass


class CareerDocumentService:
    """Service for managing teacher career document uploads and metadata."""

    def __init__(self, db: Session):
        self.db = db

    def _user_documents_dir(self, user_id: UUID) -> Path:
        """Return the directory path for a user's career documents."""
        base = Path(settings.CAREER_DOCUMENTS_DIR)
        return base / str(user_id)

    def _validate_extension(self, file_name: str) -> None:
        """Validate file extension against allowed list. Raises CareerDocumentServiceError if invalid."""
        suffix = Path(file_name).suffix.lower()
        allowed = [ext.lower() for ext in settings.CAREER_ALLOWED_EXTENSIONS]
        if suffix not in allowed:
            raise CareerDocumentServiceError(
                f"File type not allowed. Allowed: {', '.join(allowed)}"
            )

    def _validate_size(self, file_size: int) -> None:
        """Validate file size. Raises CareerDocumentServiceError if too large."""
        max_bytes = settings.CAREER_MAX_FILE_SIZE_MB * 1024 * 1024
        if file_size > max_bytes:
            raise CareerDocumentServiceError(
                f"File size exceeds maximum ({settings.CAREER_MAX_FILE_SIZE_MB}MB)"
            )

    def upload_document(
        self,
        user_id: UUID,
        file_content: bytes,
        file_name: str,
        mime_type: str,
        document_type: CareerDocumentType,
        title: Optional[str] = None,
    ) -> TeacherCareerDocument:
        """
        Validate file, write to disk under uploads/career_documents/{user_id}/{uuid_filename},
        create DB record with status UPLOADED, return document.
        """
        self._validate_extension(file_name)
        file_size = len(file_content)
        self._validate_size(file_size)

        user_dir = self._user_documents_dir(user_id)
        user_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(file_name).suffix.lower()
        unique_filename = f"{uuid4()}{suffix}"
        file_path = user_dir / unique_filename

        file_path.write_bytes(file_content)
        # Store path as string; use forward slashes for portability
        file_path_str = str(file_path).replace("\\", "/")

        document = TeacherCareerDocument(
            user_id=user_id,
            document_type=document_type.value,
            title=title,
            file_name=file_name,
            file_path=file_path_str,
            mime_type=mime_type or "application/octet-stream",
            file_size=file_size,
            status=CareerDocumentStatus.UPLOADED.value,
        )
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)
        logger.info(
            "Uploaded career document id=%s for user_id=%s type=%s",
            document.id,
            user_id,
            document_type.value,
        )
        return document

    def list_documents(self, user_id: UUID) -> List[TeacherCareerDocument]:
        """List all career documents for a user."""
        return (
            self.db.query(TeacherCareerDocument)
            .filter(TeacherCareerDocument.user_id == user_id)
            .order_by(TeacherCareerDocument.uploaded_at.desc())
            .all()
        )

    def get_document(
        self, document_id: UUID, user_id: UUID
    ) -> Optional[TeacherCareerDocument]:
        """Get a single document by id, scoped to user."""
        return (
            self.db.query(TeacherCareerDocument)
            .filter(
                TeacherCareerDocument.id == document_id,
                TeacherCareerDocument.user_id == user_id,
            )
            .first()
        )

    def delete_document(self, document_id: UUID, user_id: UUID) -> bool:
        """Delete document record and remove file from disk."""
        document = self.get_document(document_id, user_id)
        if not document:
            return False
        path = Path(document.file_path)
        if path.exists():
            try:
                path.unlink()
            except OSError as e:
                logger.warning("Could not delete file %s: %s", path, e)
        self.db.delete(document)
        self.db.commit()
        logger.info("Deleted career document id=%s for user_id=%s", document_id, user_id)
        return True

    def update_status(
        self, document_id: UUID, status: CareerDocumentStatus
    ) -> Optional[TeacherCareerDocument]:
        """Update document status (e.g. processing, ready, failed). Optionally scoped by user_id for safety."""
        document = (
            self.db.query(TeacherCareerDocument)
            .filter(TeacherCareerDocument.id == document_id)
            .first()
        )
        if not document:
            return None
        document.status = status.value
        self.db.commit()
        self.db.refresh(document)
        logger.info("Updated career document id=%s status=%s", document_id, status.value)
        return document
