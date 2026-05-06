"""
Central OCR decision flow: deterministic, policy-driven, no crashes on missing keys.
Used by IngestionService to decide if OCR is needed and which engine to use.
"""
from typing import List, Optional, Tuple, Any
from dataclasses import dataclass

from app.core.logging import get_logger
from app.core.config import settings
from app.domains.content_ingestion.providers.base import PageText, OCRResult, OCRPageResult

logger = get_logger(__name__)

# Threshold below which we consider content "scanned" and require OCR
def _scanned_threshold_chars() -> int:
    return getattr(settings, "SCANNED_THRESHOLD_CHARS", 50)


@dataclass
class OCRDecisionResult:
    """Result of central OCR decision."""
    ocr_required: bool
    reason: str
    engine_resolved: Optional[str] = None
    ocr_mode: Optional[str] = None
    fallback_used: bool = False
    warning: Optional[str] = None


def decide_ocr_required(
    *,
    force_ocr: bool = False,
    skip_ocr: bool = False,
    pages: Optional[List[PageText]] = None,
    source_type: str = "pdf",
) -> Tuple[bool, str]:
    """
    Step 1: Determine if OCR is needed.
    Returns (ocr_required, reason_string).
    """
    if force_ocr:
        return True, "force_ocr=True"
    if skip_ocr:
        return False, "skip_ocr=True"

    if source_type != "pdf":
        return False, "source_type is not pdf"

    if not pages:
        return True, "no_pages_extracted"

    total_chars = sum(getattr(p, "char_count", 0) for p in pages)
    if total_chars == 0:
        return True, "extracted_text_empty"

    avg_chars = total_chars / len(pages)
    threshold = _scanned_threshold_chars()
    if avg_chars < threshold:
        return True, f"avg_chars_per_page_{avg_chars:.0f}_below_threshold_{threshold}"

    return False, "text_sufficient_no_ocr"


def resolve_ocr_engine(
    *,
    ocr_engine_override: Optional[str] = None,
    pack_ocr_policy: Optional[str] = None,
) -> OCRDecisionResult:
    """
    Step 2 & 3: Resolve engine (override -> pack policy -> default).
    Apply OCR_MODE: if local, never use API engines; if api, allow only if keys present.
    Returns OCRDecisionResult with engine_resolved, ocr_mode, fallback_used, warning.
    """
    ocr_mode = getattr(settings, "OCR_MODE", "local").lower()
    strict_google_only = bool(getattr(settings, "OCR_STRICT_GOOGLE_ONLY", False))
    default_engine = getattr(settings, "OCR_ENGINE_DEFAULT", None) or getattr(settings, "OCR_ENGINE", "tesseract")
    fallback_engine = getattr(settings, "OCR_FALLBACK_ENGINE", "tesseract")

    pack_policy = (pack_ocr_policy or "").lower().strip() or None

    # Priority:
    # - request override (explicit engine name)
    # - pack policy (auto|non_math => default engine; math => special handling below)
    # - OCR_ENGINE_DEFAULT
    if ocr_engine_override:
        candidate = ocr_engine_override
    elif pack_policy in (None, "", "auto", "non_math", "math"):
        candidate = default_engine
    else:
        # Backward-compat: allow pack_ocr_policy to be an explicit engine name
        candidate = pack_ocr_policy
    if not candidate:
        candidate = default_engine
    engine_lower = (candidate or "").lower().strip()

    # Hard override for strict mode: OCR-required flows must resolve to Google Document AI.
    # IngestionService enforces fail-fast if Google is not configured/reachable.
    if strict_google_only and not ocr_engine_override:
        return OCRDecisionResult(
            ocr_required=True,
            reason="engine_resolved",
            engine_resolved="google_document_ai",
            ocr_mode=ocr_mode,
            warning=(
                "OCR_STRICT_GOOGLE_ONLY=true; forcing engine to google_document_ai "
                "and bypassing pack/local fallback rules"
            ),
        )

    # Map policy to engine: "math" -> prefer mathpix/google if api mode; "non_math" -> tesseract/easyocr; "auto" -> default
    if pack_policy == "math" and not ocr_engine_override:
        if ocr_mode == "api":
            for api_engine in ("mathpix", "google_document_ai"):
                if _engine_available(api_engine):
                    return OCRDecisionResult(
                        ocr_required=True,
                        reason="engine_resolved",
                        engine_resolved=api_engine,
                        ocr_mode=ocr_mode,
                    )
            logger.warning("OCR_MODE=api and pack_ocr_policy=math but no API engine available; falling back to local")
            engine_lower = fallback_engine.lower()
            return OCRDecisionResult(
                ocr_required=True,
                reason="engine_resolved",
                engine_resolved=engine_lower,
                ocr_mode=ocr_mode,
                fallback_used=True,
                warning="API keys missing for math policy; using fallback engine",
            )
        else:
            engine_lower = fallback_engine.lower()
    elif pack_policy == "non_math" and not ocr_engine_override:
        # Non-math policy: prefer local/general OCR engines.
        if engine_lower in ("mathpix", "google_document_ai"):
            engine_lower = fallback_engine.lower()
    # "auto" or None: use candidate as-is subject to OCR_MODE

    # OCR_MODE: local -> never use API engines
    if ocr_mode == "local":
        if engine_lower in ("mathpix", "google_document_ai"):
            engine_lower = fallback_engine.lower()
            return OCRDecisionResult(
                ocr_required=True,
                reason="engine_resolved",
                engine_resolved=engine_lower,
                ocr_mode=ocr_mode,
                fallback_used=True,
                warning="OCR_MODE=local; API engine not allowed, using fallback",
            )

    # API mode: if engine is API but keys missing, fallback and log
    if ocr_mode == "api" and engine_lower in ("mathpix", "google_document_ai"):
        if not _engine_available(engine_lower):
            engine_lower = fallback_engine.lower()
            return OCRDecisionResult(
                ocr_required=True,
                reason="engine_resolved",
                engine_resolved=engine_lower,
                ocr_mode=ocr_mode,
                fallback_used=True,
                warning="API keys missing for selected engine; using fallback",
            )

    return OCRDecisionResult(
        ocr_required=True,
        reason="engine_resolved",
        engine_resolved=engine_lower or default_engine,
        ocr_mode=ocr_mode,
    )


def _engine_available(engine: str) -> bool:
    """Check if an API engine has required keys (no crash)."""
    if engine == "mathpix":
        import os
        return bool(os.getenv("MATHPIX_APP_ID") and os.getenv("MATHPIX_APP_KEY"))
    if engine == "google_document_ai":
        import os
        cred_path = getattr(settings, "GOOGLE_APPLICATION_CREDENTIALS", None) or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        processor_id = getattr(settings, "DOCUMENT_AI_PROCESSOR_ID", None) or os.getenv("DOCUMENT_AI_PROCESSOR_ID")
        api_key = getattr(settings, "DOCUMENT_AI_API_KEY", None) or os.getenv("DOCUMENT_AI_API_KEY")
        # Service-account + processor is the primary production path.
        if cred_path and processor_id and os.path.exists(cred_path):
            return True
        # Keep backward-compat flag for older setups, but do not claim full readiness.
        return bool(api_key)
    return True


def get_ocr_provider_for_engine(engine: str):
    """
    Return OCR provider instance for the given engine name.
    Never crashes; returns fallback if engine unknown or unavailable.
    """
    from app.domains.content_ingestion.providers.ocr_providers import (
        TesseractOCRProvider,
        EasyOCRProvider,
        MathpixOCRProvider,
        GoogleDocumentAIOCRProvider,
    )
    fallback = getattr(settings, "OCR_FALLBACK_ENGINE", "tesseract")
    engine = (engine or "").lower().strip()
    registry = {
        "tesseract": TesseractOCRProvider,
        "easyocr": EasyOCRProvider,
        "mathpix": MathpixOCRProvider,
        "google_document_ai": GoogleDocumentAIOCRProvider,
    }
    provider_cls = registry.get(engine)
    if not provider_cls:
        logger.warning(f"Unknown OCR engine '{engine}', using fallback '{fallback}'")
        provider_cls = registry.get(fallback, TesseractOCRProvider)
    provider = provider_cls()
    if not provider.validate_config():
        logger.warning(f"OCR provider '{engine}' not configured, using fallback '{fallback}'")
        provider = registry.get(fallback, TesseractOCRProvider)()
    return provider


def page_text_list_to_ocr_result(
    pages: List[PageText],
    provider_name: str,
    duration_ms: Optional[float] = None,
    warnings: Optional[List[str]] = None,
) -> OCRResult:
    """Convert legacy List[PageText] to unified OCRResult (for storage/decision metadata)."""
    ocr_pages = [
        OCRPageResult(page_no=p.page_no, text=p.text or "")
        for p in pages
    ]
    meta = {
        "provider": provider_name,
        "duration_ms": duration_ms,
        "warnings": warnings or [],
    }
    return OCRResult(pages=ocr_pages, meta=meta)
