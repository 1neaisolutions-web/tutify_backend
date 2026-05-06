"""
OCR decision and policy layer.
Central, deterministic, policy-driven OCR for international multi-board scaling.
"""
from app.domains.content_ingestion.ocr.decision import (
    decide_ocr_required,
    resolve_ocr_engine,
    get_ocr_provider_for_engine,
)

__all__ = [
    "decide_ocr_required",
    "resolve_ocr_engine",
    "get_ocr_provider_for_engine",
]
