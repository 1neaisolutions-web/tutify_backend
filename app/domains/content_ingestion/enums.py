"""
Content Ingestion domain enums.
"""
import enum


class DocumentStatus(str, enum.Enum):
    """Document processing status enumeration."""
    UPLOADED = "uploaded"
    TEXT_EXTRACTING = "text_extracting"
    OCR_RUNNING = "ocr_running"
    NORMALIZING = "normalizing"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    INDEXING = "indexing"
    QA_VALIDATION = "qa_validation"
    PUBLISHED = "published"
    FAILED = "failed"


class QAStatus(str, enum.Enum):
    """QA validation status enumeration."""
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"


class SourceType(str, enum.Enum):
    """Document source type enumeration."""
    PDF = "pdf"
    DOCX = "docx"
    IMAGE = "image"
    TEXT = "text"
