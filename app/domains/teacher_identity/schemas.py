"""
Pydantic schemas for Teacher Identity domain.
"""
from datetime import datetime, date
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict

from app.domains.personalization.schemas import PersonalizationSyncReceipt
from app.domains.teacher_identity.enums import (
    CareerDocumentType,
    CareerDocumentStatus,
    EmploymentType,
)


# ---------- Experience ----------
class ExperienceCreate(BaseModel):
    """Create experience request."""

    institution_name: str = Field(..., min_length=1, max_length=200)
    role_title: str = Field(..., min_length=1, max_length=200)
    subject_area: Optional[str] = Field(None, max_length=100)
    grade_band: Optional[str] = Field(None, max_length=50)
    employment_type: EmploymentType
    start_date: date
    end_date: Optional[date] = None
    is_current: bool = False
    description: Optional[str] = None
    location_city: Optional[str] = Field(None, max_length=100)
    location_country: Optional[str] = Field(None, max_length=100)


class ExperienceUpdate(BaseModel):
    """Update experience request."""

    institution_name: Optional[str] = Field(None, min_length=1, max_length=200)
    role_title: Optional[str] = Field(None, min_length=1, max_length=200)
    subject_area: Optional[str] = Field(None, max_length=100)
    grade_band: Optional[str] = Field(None, max_length=50)
    employment_type: Optional[EmploymentType] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    is_current: Optional[bool] = None
    description: Optional[str] = None
    location_city: Optional[str] = Field(None, max_length=100)
    location_country: Optional[str] = Field(None, max_length=100)


class ExperienceResponse(BaseModel):
    """Experience response."""

    id: UUID
    user_id: UUID
    institution_name: str
    role_title: str
    subject_area: Optional[str] = None
    grade_band: Optional[str] = None
    employment_type: str
    start_date: date
    end_date: Optional[date] = None
    is_current: bool
    description: Optional[str] = None
    location_city: Optional[str] = None
    location_country: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    personalization_sync: Optional[PersonalizationSyncReceipt] = None

    model_config = ConfigDict(from_attributes=True)


# ---------- Education ----------
class EducationCreate(BaseModel):
    """Create education request."""

    institution_name: str = Field(..., min_length=1, max_length=200)
    degree: str = Field(..., min_length=1, max_length=200)
    field_of_study: str = Field(..., min_length=1, max_length=200)
    start_year: Optional[int] = Field(None, ge=1900, le=2100)
    end_year: Optional[int] = Field(None, ge=1900, le=2100)
    is_completed: bool = True
    description: Optional[str] = None


class EducationUpdate(BaseModel):
    """Update education request."""

    institution_name: Optional[str] = Field(None, min_length=1, max_length=200)
    degree: Optional[str] = Field(None, min_length=1, max_length=200)
    field_of_study: Optional[str] = Field(None, min_length=1, max_length=200)
    start_year: Optional[int] = Field(None, ge=1900, le=2100)
    end_year: Optional[int] = Field(None, ge=1900, le=2100)
    is_completed: Optional[bool] = None
    description: Optional[str] = None


class EducationResponse(BaseModel):
    """Education response."""

    id: UUID
    user_id: UUID
    institution_name: str
    degree: str
    field_of_study: str
    start_year: Optional[int] = None
    end_year: Optional[int] = None
    is_completed: bool
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    personalization_sync: Optional[PersonalizationSyncReceipt] = None

    model_config = ConfigDict(from_attributes=True)


# ---------- Certification ----------
class CertificationCreate(BaseModel):
    """Create certification request."""

    name: str = Field(..., min_length=1, max_length=200)
    issuer: str = Field(..., min_length=1, max_length=200)
    license_number: Optional[str] = Field(None, max_length=100)
    issue_date: Optional[date] = None
    expiry_date: Optional[date] = None
    credential_url: Optional[str] = Field(None, max_length=500)
    document_id: Optional[UUID] = None


class CertificationUpdate(BaseModel):
    """Update certification request."""

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    issuer: Optional[str] = Field(None, min_length=1, max_length=200)
    license_number: Optional[str] = Field(None, max_length=100)
    issue_date: Optional[date] = None
    expiry_date: Optional[date] = None
    credential_url: Optional[str] = Field(None, max_length=500)
    document_id: Optional[UUID] = None


class CertificationResponse(BaseModel):
    """Certification response."""

    id: UUID
    user_id: UUID
    name: str
    issuer: str
    license_number: Optional[str] = None
    issue_date: Optional[date] = None
    expiry_date: Optional[date] = None
    credential_url: Optional[str] = None
    document_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    personalization_sync: Optional[PersonalizationSyncReceipt] = None

    model_config = ConfigDict(from_attributes=True)


# ---------- Achievement ----------
class AchievementCreate(BaseModel):
    """Create achievement request."""

    title: str = Field(..., min_length=1, max_length=300)
    organization: Optional[str] = Field(None, max_length=200)
    date: Optional[date] = None
    description: Optional[str] = None


class AchievementUpdate(BaseModel):
    """Update achievement request."""

    title: Optional[str] = Field(None, min_length=1, max_length=300)
    organization: Optional[str] = Field(None, max_length=200)
    date: Optional[date] = None
    description: Optional[str] = None


class AchievementResponse(BaseModel):
    """Achievement response."""

    id: UUID
    user_id: UUID
    title: str
    organization: Optional[str] = None
    date: Optional[date] = None
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    personalization_sync: Optional[PersonalizationSyncReceipt] = None

    model_config = ConfigDict(from_attributes=True)


# ---------- Career Document ----------
class CareerDocumentResponse(BaseModel):
    """Career document response."""

    id: UUID
    user_id: UUID
    document_type: str
    title: Optional[str] = None
    file_name: str
    file_path: str
    mime_type: str
    file_size: int
    status: str
    error_message: Optional[str] = None
    uploaded_at: datetime
    created_at: datetime
    updated_at: datetime
    personalization_sync: Optional[PersonalizationSyncReceipt] = None

    model_config = ConfigDict(from_attributes=True)


class CareerDocumentListItem(BaseModel):
    """Career document list item."""

    id: UUID
    user_id: UUID
    document_type: str
    title: Optional[str] = None
    file_name: str
    file_size: int
    status: str
    uploaded_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
