"""
Teacher Identity domain models.
"""
import uuid
from datetime import datetime, timezone, date

from sqlalchemy import (
    Column,
    String,
    Text,
    Boolean,
    Integer,
    DateTime,
    Date,
    ForeignKey,
    Index,
    Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base_class import Base
from app.domains.teacher_identity.enums import (
    CareerDocumentType,
    CareerDocumentStatus,
    EmploymentType,
)


class TeacherExperience(Base):
    """Employment history for a teacher."""

    __tablename__ = "teacher_experiences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    institution_name = Column(String(200), nullable=False)
    role_title = Column(String(200), nullable=False)
    subject_area = Column(String(100), nullable=True)
    grade_band = Column(String(50), nullable=True)
    employment_type = Column(
        String(50), nullable=False, index=True
    )  # EmploymentType value
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    is_current = Column(Boolean, default=False, nullable=False)
    description = Column(Text, nullable=True)
    location_city = Column(String(100), nullable=True)
    location_country = Column(String(100), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (Index("idx_teacher_experience_user_dates", "user_id", "start_date"),)

    def __repr__(self) -> str:
        return f"<TeacherExperience(id={self.id}, user_id={self.user_id}, role_title={self.role_title})>"


class TeacherEducation(Base):
    """Academic background for a teacher."""

    __tablename__ = "teacher_education"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    institution_name = Column(String(200), nullable=False)
    degree = Column(String(200), nullable=False)
    field_of_study = Column(String(200), nullable=False)
    start_year = Column(Integer, nullable=True)
    end_year = Column(Integer, nullable=True)
    is_completed = Column(Boolean, default=True, nullable=False)
    description = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (Index("idx_teacher_education_user", "user_id", "end_year"),)

    def __repr__(self) -> str:
        return f"<TeacherEducation(id={self.id}, user_id={self.user_id}, degree={self.degree})>"


class TeacherCareerDocument(Base):
    """Uploaded career-related document (CV, resume, portfolio, etc.)."""

    __tablename__ = "teacher_career_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    document_type = Column(String(50), nullable=False, index=True)  # CareerDocumentType value
    title = Column(String(500), nullable=True)
    file_name = Column(String(500), nullable=False)
    file_path = Column(String(1000), nullable=False)
    mime_type = Column(String(100), nullable=False)
    file_size = Column(Integer, nullable=False)
    status = Column(String(50), nullable=False, default=CareerDocumentStatus.UPLOADED.value, index=True)
    error_message = Column(Text, nullable=True)
    uploaded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", foreign_keys=[user_id])
    certifications = relationship("TeacherCertification", back_populates="document", foreign_keys="TeacherCertification.document_id")

    __table_args__ = (Index("idx_teacher_career_doc_user_type", "user_id", "document_type"),)

    def __repr__(self) -> str:
        return f"<TeacherCareerDocument(id={self.id}, user_id={self.user_id}, document_type={self.document_type})>"


class TeacherCertification(Base):
    """Professional certification or teaching license."""

    __tablename__ = "teacher_certifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    name = Column(String(200), nullable=False)
    issuer = Column(String(200), nullable=False)
    license_number = Column(String(100), nullable=True)
    issue_date = Column(Date, nullable=True)
    expiry_date = Column(Date, nullable=True)
    credential_url = Column(String(500), nullable=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("teacher_career_documents.id", ondelete="SET NULL"), nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", foreign_keys=[user_id])
    document = relationship("TeacherCareerDocument", back_populates="certifications", foreign_keys=[document_id])

    __table_args__ = (Index("idx_teacher_cert_user", "user_id"),)

    def __repr__(self) -> str:
        return f"<TeacherCertification(id={self.id}, user_id={self.user_id}, name={self.name})>"


class TeacherAchievement(Base):
    """Award, recognition, or teaching achievement."""

    __tablename__ = "teacher_achievements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    title = Column(String(300), nullable=False)
    organization = Column(String(200), nullable=True)
    date = Column(Date, nullable=True)
    description = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (Index("idx_teacher_achievement_user", "user_id"),)

    def __repr__(self) -> str:
        return f"<TeacherAchievement(id={self.id}, user_id={self.user_id}, title={self.title})>"
