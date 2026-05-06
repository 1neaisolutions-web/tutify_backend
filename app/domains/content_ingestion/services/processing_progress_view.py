"""
Build API/SSE-facing processing progress from Document + DocumentProcessingRun.

Maps pipeline stages to meaningful completed/total pairs (pages vs chunks vs vectors).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.domains.content_ingestion.enums import DocumentStatus
from app.domains.content_ingestion.models import Document, DocumentProcessingRun


def build_processing_progress(
    document: Document,
    latest_run: Optional[DocumentProcessingRun],
) -> Optional[Dict[str, Any]]:
    """
    Return a progress dict for SSE/REST, or None if there is no processing run.

    Semantics:
    - text_extracting / ocr_running: completed = pages_processed, total = document.total_pages
    - normalizing: all pages known — show total_pages / total_pages when available
    - chunking: while chunks_created is 0, fall back to page counts; once set, use chunks
    - embedding: vectors not partially tracked — 0 / chunks_created
    - indexing: vectors_stored / chunks_created
    - qa_validation: prefer vectors_stored vs chunks as a coarse completion signal
    """
    if not latest_run:
        return None

    status = document.status
    step = latest_run.current_step or status
    pct = latest_run.progress_percentage or 0
    pages_done = int(latest_run.pages_processed or 0)
    total_pages = int(document.total_pages or 0)
    chunks = int(latest_run.chunks_created or 0)
    vecs = int(latest_run.vectors_stored or 0)
    chunk_total = max(chunks, 1)

    if status in (
        DocumentStatus.TEXT_EXTRACTING.value,
        DocumentStatus.OCR_RUNNING.value,
    ):
        completed, total = pages_done, total_pages
    elif status == DocumentStatus.NORMALIZING.value:
        if total_pages > 0:
            completed, total = total_pages, total_pages
        else:
            completed, total = pages_done, max(pages_done, 1)
    elif status == DocumentStatus.CHUNKING.value:
        if chunks > 0:
            completed, total = chunks, chunks
        else:
            completed, total = pages_done, max(total_pages, pages_done, 1)
    elif status == DocumentStatus.EMBEDDING.value:
        completed, total = 0, chunk_total
    elif status == DocumentStatus.INDEXING.value:
        completed, total = vecs, chunk_total
    elif status == DocumentStatus.QA_VALIDATION.value:
        completed, total = (vecs if vecs else chunks), chunk_total
    else:
        completed, total = chunks, chunk_total

    out: Dict[str, Any] = {
        "step": step,
        "completed": completed,
        "total": total,
        "percentage": pct,
    }
    # Redundant fields help SSE change detection when percentage is unchanged between polls.
    out["pages_processed"] = pages_done
    out["total_pages"] = total_pages
    return out
