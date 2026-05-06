"""
File type and content type detection (magic bytes / MIME, PDF digital vs scanned).
No API changes; used at upload save or ingestion start.
"""
import os
from typing import Optional, Tuple, Dict, Any

from app.core.logging import get_logger

logger = get_logger(__name__)

# Magic bytes (first N bytes)
PDF_MAGIC = b"%PDF"
ZIP_MAGIC = b"PK\x03\x04"  # DOCX is ZIP
PNG_MAGIC = b"\x89PNG"
JPEG_MAGIC_START = b"\xff\xd8\xff"
GIF_MAGIC = b"GIF87a"
GIF89_MAGIC = b"GIF89a"


def _read_head(path: str, size: int = 4096) -> bytes:
    with open(path, "rb") as f:
        return f.read(size)


def detect_mime_and_source(
    file_path: Optional[str] = None,
    file_content: Optional[bytes] = None,
    filename: Optional[str] = None,
) -> Tuple[str, str, Optional[str], str]:
    """
    Detect MIME, source type, PDF type (digital/scanned), and extraction strategy.
    Returns: (detected_mime, detected_source_type, pdf_type, extraction_strategy).
    """
    data = None
    if file_path and os.path.exists(file_path):
        data = _read_head(file_path)
    elif file_content:
        data = file_content[:8192]
    ext = (filename or "").lower().split(".")[-1] if filename else ""

    detected_mime = "application/octet-stream"
    detected_source_type = "pdf"
    pdf_type = None
    extraction_strategy = "text"

    if data:
        if data.startswith(PDF_MAGIC):
            detected_mime = "application/pdf"
            detected_source_type = "pdf"
            extraction_strategy = "pdf_text"
            pdf_type = "digital"  # override below if low text density
        elif data.startswith(ZIP_MAGIC) and (ext == "docx" or "word" in (filename or "").lower()):
            detected_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            detected_source_type = "docx"
            extraction_strategy = "docx"
        elif data.startswith(PNG_MAGIC):
            detected_mime = "image/png"
            detected_source_type = "image"
            extraction_strategy = "ocr"
        elif data.startswith(JPEG_MAGIC_START):
            detected_mime = "image/jpeg"
            detected_source_type = "image"
            extraction_strategy = "ocr"
        elif data.startswith(GIF_MAGIC) or data.startswith(GIF89_MAGIC):
            detected_mime = "image/gif"
            detected_source_type = "image"
            extraction_strategy = "ocr"
        else:
            if ext == "pdf":
                detected_mime = "application/pdf"
                detected_source_type = "pdf"
                extraction_strategy = "pdf_text"
            elif ext in ("docx", "doc"):
                detected_source_type = "docx"
                extraction_strategy = "docx"
            elif ext in ("png", "jpg", "jpeg", "tiff"):
                detected_source_type = "image"
                extraction_strategy = "ocr"
    else:
        if ext == "pdf":
            detected_source_type = "pdf"
            extraction_strategy = "pdf_text"
        elif ext in ("docx", "doc"):
            detected_source_type = "docx"
            extraction_strategy = "docx"
        elif ext in ("png", "jpg", "jpeg", "tiff"):
            detected_source_type = "image"
            extraction_strategy = "ocr"

    return detected_mime, detected_source_type, pdf_type, extraction_strategy


def classify_pdf_after_extract(
    pages_char_counts: list,
    threshold_chars: int = 50,
) -> str:
    """
    After text extraction, classify PDF as digital or scanned by text density.
    Returns "digital" or "scanned".
    """
    if not pages_char_counts:
        return "scanned"
    total = sum(pages_char_counts)
    avg = total / len(pages_char_counts) if pages_char_counts else 0
    return "digital" if avg >= threshold_chars else "scanned"
