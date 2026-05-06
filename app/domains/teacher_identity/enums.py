"""
Teacher Identity domain enumerations.
"""
import enum


class CareerDocumentType(str, enum.Enum):
    """Type of career-related document."""

    RESUME = "resume"
    CV = "cv"
    PORTFOLIO = "portfolio"
    CERTIFICATION = "certification"
    RESEARCH = "research"
    OTHER = "other"


class CareerDocumentStatus(str, enum.Enum):
    """Processing status for career documents."""

    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class EmploymentType(str, enum.Enum):
    """Type of employment."""

    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERNSHIP = "internship"
    VOLUNTEER = "volunteer"
