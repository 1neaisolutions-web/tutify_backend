"""
Document ingestion service - main pipeline orchestrator.
Provider-driven; checkpoints and observability; free mode supported.
"""
import os
import hashlib
import time
import re
from typing import Optional, Dict, Any, List, Tuple
from uuid import UUID
from pathlib import Path

from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError
from sqlalchemy.exc import PendingRollbackError

from app.core.logging import get_logger
from app.core.config import settings
from app.llm.config import llm_settings
from app.domains.content_ingestion.models import (
    Document, PageText, Chunk, DocumentProcessingRun, ContentPack
)
from app.domains.content_ingestion.enums import DocumentStatus
from app.domains.content_ingestion.detection import (
    detect_mime_and_source,
    classify_pdf_after_extract,
)
from app.domains.content_ingestion.providers.ocr_providers import (
    TesseractOCRProvider,
    EasyOCRProvider,
    MathpixOCRProvider,
)
from app.domains.content_ingestion.providers.text_extractors import (
    PDFTextExtractor,
    DOCXTextExtractor,
)
from app.domains.content_ingestion.providers.chunkers import SimpleChunker
from app.domains.content_ingestion.providers.embedding_providers import (
    FakeEmbeddingProvider,
    LocalSentenceTransformersEmbeddingProvider,
    OpenAIEmbeddingProvider,
)
from app.domains.content_ingestion.providers.vector_stores import PgVectorStore
from app.domains.content_ingestion.providers.math_providers import (
    BaselineMathExtractionProvider,
    compute_math_density,
)
from app.domains.content_ingestion.providers.ocr_preflight import OcrPreflight, OcrPreflightError
from app.domains.content_ingestion.text_db import sanitize_pg_text
from app.domains.content_ingestion.topic_label_normalize import normalize_topic_label
from app.domains.content_ingestion.services.role_tagger import (
    assign_chunk_roles,
    compute_role_distribution,
    compute_role_tagging_metrics,
)
from app.domains.content_ingestion.ocr.decision import (
    decide_ocr_required,
    resolve_ocr_engine,
    get_ocr_provider_for_engine,
    page_text_list_to_ocr_result,
)

logger = get_logger(__name__)
MATH_DENSITY_THRESHOLD = 0.5  # per-page threshold for content_type_hint=math

# Statuses where a pipeline job is already running — skip duplicate BackgroundTasks / races
_INGESTION_ACTIVE_STATUSES = frozenset(
    {
        DocumentStatus.TEXT_EXTRACTING.value,
        DocumentStatus.OCR_RUNNING.value,
        DocumentStatus.NORMALIZING.value,
        DocumentStatus.CHUNKING.value,
        DocumentStatus.EMBEDDING.value,
        DocumentStatus.INDEXING.value,
        DocumentStatus.QA_VALIDATION.value,
    }
)


class IngestionService:
    """Service for ingesting documents through the processing pipeline."""
    
    def __init__(self, db: Session):
        """Initialize ingestion service."""
        self.db = db
        self._init_providers()
    
    def _init_providers(self):
        """Initialize providers based on configuration."""
        # OCR provider
        if settings.OCR_ENGINE == "tesseract":
            self.ocr_provider = TesseractOCRProvider()
        elif settings.OCR_ENGINE == "easyocr":
            self.ocr_provider = EasyOCRProvider()
        elif settings.OCR_ENGINE == "mathpix":
            self.ocr_provider = MathpixOCRProvider()
        else:
            self.ocr_provider = TesseractOCRProvider()
        
        # Text extractors
        self.pdf_extractor = PDFTextExtractor()
        self.docx_extractor = DOCXTextExtractor()
        
        # Chunker
        self.chunker = SimpleChunker()
        
        # Embedding provider (config-only)
        emb = (settings.EMBEDDING_PROVIDER or "fake").lower()
        if emb == "openai":
            self.embedding_provider = OpenAIEmbeddingProvider()
        elif emb == "local":
            self.embedding_provider = LocalSentenceTransformersEmbeddingProvider()
        else:
            self.embedding_provider = FakeEmbeddingProvider()
        
        # Vector store
        if settings.VECTOR_STORE == "pgvector":
            self.vector_store = PgVectorStore(db=self.db)
        else:
            self.vector_store = PgVectorStore(db=self.db)
        # Math provider (config: MATH_PROVIDER=baseline|mathpix)
        if getattr(settings, "MATH_PROVIDER", "baseline") == "baseline":
            self.math_provider = BaselineMathExtractionProvider()
        else:
            self.math_provider = BaselineMathExtractionProvider()

    def _select_embedding_provider_for_document(self, document: Document):
        """
        Select embedding provider for this document run.
        If OCR_EMBEDDINGS_ONLY is enabled, OpenAI embeddings are restricted to OCR-processed docs.
        """
        emb = (settings.EMBEDDING_PROVIDER or "fake").lower()
        ocr_used = bool((document.processing_metadata or {}).get("ocr_used"))
        ocr_only = bool(settings.OCR_EMBEDDINGS_ONLY)
        has_openai_key = bool((getattr(llm_settings, "OPENAI_API_KEY", None) or "").strip())

        # Safe default: for OCR-processed documents, prefer real OpenAI embeddings when key is present.
        # This keeps document ingestion high quality without enabling OpenAI for other modules.
        if ocr_used and has_openai_key:
            return OpenAIEmbeddingProvider()

        if emb == "openai" and ocr_only and not ocr_used:
            return FakeEmbeddingProvider()
        if emb == "openai":
            return OpenAIEmbeddingProvider()
        if emb == "local":
            return LocalSentenceTransformersEmbeddingProvider()
        return FakeEmbeddingProvider()

    @staticmethod
    def _slugify_topic_id(value: str) -> str:
        """Build stable ASCII-like IDs for inferred topic labels."""
        s = (value or "").strip().lower()
        s = re.sub(r"[^a-z0-9]+", "-", s)
        s = re.sub(r"-{2,}", "-", s).strip("-")
        return s or "topic"

    @staticmethod
    def _infer_page_topic_labels(pages: List[Any], document: Document) -> Dict[int, str]:
        """
        Infer page-level topic labels from the first meaningful line on each page.

        This is used only when chapter_map / PDF outline metadata is unavailable.
        It keeps the existing page-bin fallback as a safety net for weak headings.
        """
        if not pages:
            return {}

        doc_base = normalize_topic_label((document.title or os.path.splitext(document.filename or "")[0]), max_len=200)
        page_to_topic: Dict[int, str] = {}
        carry_topic: Optional[str] = None

        for p in pages:
            page_no = int(getattr(p, "page_no", 0) or 0)
            text = str(getattr(p, "text", "") or "").replace("\u0000", "")
            if page_no <= 0 or not text.strip():
                continue

            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            candidate = ""
            for ln in lines[:8]:
                clean = normalize_topic_label(ln, max_len=120)
                if len(clean) < 4:
                    continue
                if len(clean) > 90:
                    continue
                # Skip obvious paragraph-like lines; headings are usually short and low punctuation.
                punct = clean.count(".") + clean.count(",") + clean.count(";") + clean.count(":")
                if punct > 1:
                    continue
                candidate = clean
                break

            if not candidate:
                if carry_topic:
                    page_to_topic[page_no] = carry_topic
                continue

            # Ignore generic "Page X" style labels.
            lower = candidate.lower()
            if re.fullmatch(r"page\s+\d+(\s+of\s+\d+)?", lower):
                if carry_topic:
                    page_to_topic[page_no] = carry_topic
                continue

            if doc_base and lower == doc_base.lower():
                if carry_topic:
                    page_to_topic[page_no] = carry_topic
                continue

            carry_topic = candidate
            page_to_topic[page_no] = candidate

        return page_to_topic

    @staticmethod
    def _ensure_chunk_topic_fallback_labels(
        chunks: List[Any],
        document: Document,
        *,
        page_count: int,
        page_topic_map: Optional[Dict[int, str]] = None,
    ) -> Tuple[str, str, int]:
        """
        Label chunks the chapter map did not cover using page windows.

        Produces many quiz/catalog strands (e.g. "Physics 9 · pp. 1–10") instead of one
        book-level chip, while real PDF outline / TOC entries stay authoritative when present.
        """
        raw_title = (document.title or "").strip()
        stem, _ = os.path.splitext(document.filename or "")
        stem = stem.strip()
        base_raw = raw_title if len(raw_title) >= 2 else stem
        base = normalize_topic_label(base_raw, max_len=200) or "Material"

        tp_doc = document.total_pages
        try:
            tp_doc = int(tp_doc) if tp_doc is not None else page_count
        except (TypeError, ValueError):
            tp_doc = page_count
        tp = max(1, int(page_count or 1), int(tp_doc or 1))

        page_bin = max(4, int(getattr(settings, "TOPIC_FALLBACK_PAGE_BIN_PAGES", 10)))

        filled = 0
        for ch in chunks:
            if (getattr(ch, "topic_title", None) or "").strip():
                continue
            ps = int(getattr(ch, "page_start", None) or 1)
            pe = int(getattr(ch, "page_end", None) or ps)

            # Prefer inferred page headings when available and consistent for this chunk span.
            inferred = None
            if page_topic_map:
                span = range(min(ps, pe), max(ps, pe) + 1)
                labels = {page_topic_map.get(pn) for pn in span if page_topic_map.get(pn)}
                if len(labels) == 1:
                    inferred = labels.pop()
                elif len(labels) > 1:
                    # If multiple labels occur in one chunk, use chunk start-page label.
                    inferred = page_topic_map.get(ps)
            if inferred:
                label = normalize_topic_label(inferred, max_len=500)
                ch.topic_title = label
                ch.topic_id = f"scope:topic-{IngestionService._slugify_topic_id(label)}"
                filled += 1
                continue

            mid = max(1, (ps + pe) // 2)
            bin_id = max(0, (mid - 1) // page_bin)
            p_lo = bin_id * page_bin + 1
            p_hi = min((bin_id + 1) * page_bin, tp)
            if p_hi < p_lo:
                p_hi = p_lo
            label = normalize_topic_label(f"{base} · pp. {p_lo}–{p_hi}", max_len=500)
            ch.topic_title = label
            ch.topic_id = f"scope:pages-{p_lo}-{p_hi}"
            filled += 1

        if document.chapter_map:
            mode = "chapter_map_plus_page_bins" if filled else "chapter_map"
        else:
            meta = document.processing_metadata or {}
            if meta.get("toc_source") == "pdf_outline_auto":
                mode = "pdf_outline_plus_page_bins" if filled else "pdf_outline_only"
            elif page_topic_map:
                mode = "inferred_page_headings_plus_page_bins" if filled else "page_bins_only"
            else:
                mode = "page_bins_only"

        return mode, base, filled

    async def ingest_document(self, document_id: UUID) -> Document:
        """
        Main ingestion pipeline for a document.
        
        State machine:
        UPLOADED -> TEXT_EXTRACTING -> OCR_RUNNING (conditional) 
        -> NORMALIZING -> CHUNKING -> EMBEDDING -> INDEXING 
        -> QA_VALIDATION -> PUBLISHED
        """
        document = self.db.query(Document).filter(
            Document.id == document_id
        ).first()
        
        if not document:
            raise ValueError(f"Document {document_id} not found")
        if not os.path.exists(document.file_path):
            raise FileNotFoundError(f"Document file not found: {document.file_path}")

        # Duplicate job guard: second BackgroundTasks enqueue must not double-run pipeline
        if document.status in _INGESTION_ACTIVE_STATUSES:
            logger.warning(
                "ingestion_skipped_already_active",
                extra={"document_id": str(document_id), "status": document.status},
            )
            return document

        if document.status == DocumentStatus.PUBLISHED.value:
            logger.info(
                "ingestion_skipped_already_published",
                extra={"document_id": str(document_id)},
            )
            return document

        # File type / MIME detection at ingestion start
        detected_mime, detected_source_type, pdf_type_initial, extraction_strategy = detect_mime_and_source(
            file_path=document.file_path,
            filename=document.filename,
        )
        meta = dict(document.processing_metadata or {})
        meta["detected_mime"] = detected_mime
        meta["detected_source_type"] = detected_source_type
        meta["extraction_strategy"] = extraction_strategy
        if pdf_type_initial:
            meta["pdf_type"] = pdf_type_initial
        document.processing_metadata = meta
        self.db.commit()
        logger.info(
            "ingestion_start",
            extra={
                "document_id": str(document_id),
                "detected_mime": detected_mime,
                "detected_source_type": detected_source_type,
                "extraction_strategy": extraction_strategy,
            },
        )

        # Single-flight claim after MIME checks so we do not leave status=text_extracting if MIME fails
        claimed = False
        if document.status == DocumentStatus.UPLOADED.value:
            rows = (
                self.db.query(Document)
                .filter(
                    Document.id == document_id,
                    Document.status == DocumentStatus.UPLOADED.value,
                )
                .update({"status": DocumentStatus.TEXT_EXTRACTING.value}, synchronize_session=False)
            )
            self.db.commit()
            claimed = rows == 1
        elif document.status == DocumentStatus.FAILED.value:
            rows = (
                self.db.query(Document)
                .filter(
                    Document.id == document_id,
                    Document.status == DocumentStatus.FAILED.value,
                )
                .update({"status": DocumentStatus.TEXT_EXTRACTING.value}, synchronize_session=False)
            )
            self.db.commit()
            claimed = rows == 1
            if claimed:
                # Purge any partial artifacts from the failed run so retry starts clean
                # (prevents duplicate chunks / vectors on re-processing)
                self.db.query(Chunk).filter(Chunk.document_id == document_id).delete(synchronize_session=False)
                self.db.query(PageText).filter(PageText.document_id == document_id).delete(synchronize_session=False)
                self.db.commit()
                logger.info(
                    "ingestion_retry_purge",
                    extra={"document_id": str(document_id), "action": "purged chunks+pages for clean retry"},
                )
        else:
            raise ValueError(
                f"Cannot ingest document {document_id} from status '{document.status}' "
                "(expected uploaded or failed)."
            )

        if not claimed:
            document = self.db.query(Document).filter(Document.id == document_id).first()
            logger.warning(
                "ingestion_claim_lost_duplicate_job",
                extra={
                    "document_id": str(document_id),
                    "current_status": getattr(document, "status", None),
                },
            )
            return document

        document = self.db.query(Document).filter(Document.id == document_id).first()
        source_type = (document.source_type or "") if document else ""

        logger.info(f"Starting ingestion pipeline for document {document_id}")
        
        # Create processing run
        processing_run = DocumentProcessingRun(
            document_id=document_id,
            status=DocumentStatus.TEXT_EXTRACTING.value,
            current_step="text_extracting"
        )
        self.db.add(processing_run)
        self.db.commit()
        
        try:
            # Step 1: Text Extraction
            t0 = time.perf_counter()
            await self._update_status(document_id, DocumentStatus.TEXT_EXTRACTING.value, processing_run)
            pages = await self._extract_text(document, processing_run)
            duration_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(
                "step_complete",
                extra={"document_id": str(document_id), "step": "text_extracting", "duration_ms": duration_ms, "pages": len(pages) if pages else 0},
            )
            if not pages:
                raise ValueError("No text extracted from document")
            
            # PDF: classify digital vs scanned after extract (before OCR decision)
            if source_type == "pdf" and pages:
                pdf_type = classify_pdf_after_extract(
                    [p.char_count for p in pages],
                    threshold_chars=getattr(settings, "SCANNED_THRESHOLD_CHARS", 50),
                )
                meta = dict(document.processing_metadata or {})
                meta["pdf_type"] = pdf_type
                meta["extraction_strategy"] = "ocr" if pdf_type == "scanned" else "pdf_text"
                document.processing_metadata = meta
                self.db.commit()
            
            # Store initial page texts (may be updated by OCR)
            for page in pages:
                safe_text = sanitize_pg_text(page.text)
                safe_chars = len(safe_text.strip())
                page_text = PageText(
                    document_id=document_id,
                    page_no=page.page_no,
                    text=safe_text,
                    char_count=safe_chars,
                    ocr_confidence=page.ocr_confidence,
                    ocr_engine=page.ocr_engine
                )
                self.db.add(page_text)
            
            self.db.commit()
            
            # Update document total pages
            document.total_pages = len(pages)
            self.db.commit()
            
            processing_run.pages_processed = len(pages)
            self.db.commit()
            
            # Step 2: OCR (if needed) — central policy-driven decision
            total_chars = sum(p.char_count for p in pages)
            force_ocr = (document.processing_metadata or {}).get("force_ocr", False)
            skip_ocr = (document.processing_metadata or {}).get("skip_ocr", False)
            needs_ocr, ocr_decision_reason = decide_ocr_required(
                force_ocr=force_ocr,
                skip_ocr=skip_ocr,
                pages=pages,
                source_type=source_type or "pdf",
            )
            ocr_engine_used = None
            ocr_mode_used = None
            ocr_warnings = []
            
            # Run preflight checks if OCR is needed
            preflight_result = None
            if needs_ocr:
                try:
                    preflight_result = OcrPreflight.check()
                    # Store preflight results in metadata
                    meta = dict(document.processing_metadata or {})
                    meta["ocr_preflight"] = {
                        "tesseract_found": preflight_result["tesseract_found"],
                        "tesseract_path": preflight_result["tesseract_path"],
                        "poppler_found": preflight_result["poppler_found"],
                        "poppler_path": preflight_result["poppler_path"],
                    }
                    document.processing_metadata = meta
                    self.db.commit()
                    
                    # QA logging: Log when chars=0 triggers OCR (after preflight)
                    if total_chars == 0:
                        logger.info(
                            "ocr_triggered_zero_chars",
                            extra={
                                "document_id": str(document_id),
                                "total_chars": 0,
                                "needs_ocr": needs_ocr,
                                "force_ocr": force_ocr,
                                "pdf_type": (document.processing_metadata or {}).get("pdf_type", "unknown"),
                                "preflight_result": {
                                    "tesseract_found": preflight_result["tesseract_found"],
                                    "poppler_found": preflight_result["poppler_found"],
                                },
                            },
                        )
                    
                    # Keep preflight errors as warnings first; hard-fail decision is made
                    # after engine resolution (API engines may proceed without local binaries).
                    if needs_ocr and preflight_result["errors"]:
                        ocr_warnings.extend(preflight_result["errors"])
                except OcrPreflightError:
                    raise  # Re-raise preflight errors as-is
                except Exception as e:
                    logger.warning(f"Preflight check failed: {e}, continuing with provider validation")
            
            # Resolve engine from pack policy + config (central decision)
            pack = self.db.query(ContentPack).filter(ContentPack.id == document.pack_id).first()
            pack_ocr_policy = getattr(pack, "ocr_policy", None) if pack else None
            ocr_engine_override = (document.processing_metadata or {}).get("ocr_engine_override")
            ocr_decision = (
                resolve_ocr_engine(pack_ocr_policy=pack_ocr_policy, ocr_engine_override=ocr_engine_override)
                if needs_ocr
                else None
            )
            if ocr_decision and ocr_decision.warning:
                ocr_warnings.append(ocr_decision.warning)
            if ocr_decision:
                ocr_engine_used = ocr_decision.engine_resolved
                ocr_mode_used = ocr_decision.ocr_mode
            strict_google_only = bool(getattr(settings, "OCR_STRICT_GOOGLE_ONLY", False))
            ocr_provider = get_ocr_provider_for_engine(ocr_engine_used or getattr(settings, "OCR_ENGINE_DEFAULT", "tesseract")) if needs_ocr else self.ocr_provider
            ocr_provider_ok = ocr_provider.validate_config() if needs_ocr else False
            selected_engine = getattr(ocr_provider, "provider_name", "").lower()
            if needs_ocr and strict_google_only and selected_engine != "google_document_ai":
                raise RuntimeError(
                    "Strict OCR mode is enabled (OCR_STRICT_GOOGLE_ONLY=true): "
                    f"resolved OCR engine is '{selected_engine or 'unknown'}', expected 'google_document_ai'. "
                    "Set content pack ocr_policy=auto|math (not non_math) and configure Google Document AI credentials."
                )
            if needs_ocr and not ocr_provider_ok:
                if strict_google_only:
                    raise RuntimeError(
                        "Strict OCR mode is enabled (OCR_STRICT_GOOGLE_ONLY=true) but Google Document AI is not configured. "
                        "Set GOOGLE_APPLICATION_CREDENTIALS, DOCUMENT_AI_PROJECT_ID, and DOCUMENT_AI_PROCESSOR_ID."
                    )
                if selected_engine in ("google_document_ai", "mathpix"):
                    fallback_provider = get_ocr_provider_for_engine(getattr(settings, "OCR_FALLBACK_ENGINE", "tesseract"))
                    if fallback_provider.validate_config():
                        ocr_provider = fallback_provider
                        ocr_provider_ok = True
                        ocr_warnings.append(f"fallback_used:{selected_engine}->{getattr(fallback_provider, 'provider_name', 'tesseract')}")
                        ocr_warnings.append("fallback_reason:selected_api_provider_not_configured")
                        ocr_engine_used = getattr(fallback_provider, "provider_name", ocr_engine_used)
                    else:
                        raise RuntimeError(
                            f"OCR required for document {document_id}, selected API OCR provider '{selected_engine}' is not configured and fallback provider is unavailable."
                        )
                else:
                    raise RuntimeError(
                        f"OCR required for document {document_id} (scanned/low-text PDF or image) but OCR provider is not available. "
                        "Install Tesseract and Poppler: Windows https://github.com/UB-Mannheim/tesseract/wiki, "
                        "Linux: sudo apt-get install tesseract-ocr poppler-utils. "
                        "Do not silently continue with empty or low-quality text."
                    )
            ocr_attempted = False
            total_chars_before_ocr = total_chars  # Store before OCR
            if needs_ocr and ocr_provider_ok:
                ocr_attempted = True
                t0 = time.perf_counter()
                await self._update_status(document_id, DocumentStatus.OCR_RUNNING.value, processing_run)
                try:
                    batch_size = int(os.getenv("OCR_BATCH_SIZE") or 10)
                    dpi = int(os.getenv("OCR_DPI") or 300)
                    thread_count = os.getenv("OCR_THREAD_COUNT")
                    total_pages = len(pages) if pages else (document.total_pages or 0)
                    # Large PDFs: use smaller page windows to keep Google API payloads and latency bounded.
                    if total_pages and total_pages >= 120:
                        large_batch = int(os.getenv("OCR_BATCH_SIZE_LARGE", "5"))
                        batch_size = max(1, min(batch_size, large_batch))
                    if total_pages <= 0:
                        pages = await ocr_provider.run_ocr(document.file_path, language="eng")
                        total_pages = len(pages)
                    else:
                        # Google Document AI async batch mode should process the full PDF in one operation.
                        # Splitting into many small windows triggers many independent batch jobs and is slower
                        # and less reliable for large textbooks.
                        if selected_engine == "google_document_ai":
                            pages = await ocr_provider.run_ocr(
                                document.file_path,
                                language="eng",
                                dpi=dpi,
                                thread_count=thread_count,
                            )
                            total_pages = len(pages)
                        else:
                            ocr_pages: List[Any] = []
                            for start_page in range(1, total_pages + 1, batch_size):
                                end_page = min(total_pages, start_page + batch_size - 1)
                                logger.info(
                                    "ocr_batch_start",
                                    extra={
                                        "document_id": str(document_id),
                                        "start_page": start_page,
                                        "end_page": end_page,
                                        "dpi": dpi,
                                        "batch_size": batch_size,
                                        "engine": getattr(ocr_provider, "provider_name", "unknown"),
                                    },
                                )
                                batch = await ocr_provider.run_ocr(
                                    document.file_path,
                                    language="eng",
                                    first_page=start_page,
                                    last_page=end_page,
                                    dpi=dpi,
                                    thread_count=thread_count,
                                )
                                for page in batch:
                                    page_text = self.db.query(PageText).filter(
                                        PageText.document_id == document_id,
                                        PageText.page_no == page.page_no
                                    ).first()
                                    if page_text:
                                        st = sanitize_pg_text(page.text)
                                        page_text.text = st
                                        page_text.char_count = len(st.strip())
                                        page_text.ocr_confidence = getattr(page, "ocr_confidence", None)
                                        page_text.ocr_engine = getattr(page, "ocr_engine", None) or getattr(ocr_provider, "provider_name", None)
                                ocr_pages.extend(batch)
                                processing_run.pages_processed = min(end_page, total_pages)
                                self.db.commit()
                                logger.info(
                                    "ocr_batch_complete",
                                    extra={
                                        "document_id": str(document_id),
                                        "start_page": start_page,
                                        "end_page": end_page,
                                        "pages_processed": processing_run.pages_processed,
                                        "total_pages": total_pages,
                                    },
                                )
                            pages = ocr_pages
                    duration_ms = int((time.perf_counter() - t0) * 1000)
                    ocr_engine_used = getattr(ocr_provider, "provider_name", ocr_engine_used)
                    ocr_mode_used = ocr_mode_used or getattr(settings, "OCR_MODE", "local")
                    logger.info(
                        "step_complete",
                        extra={"document_id": str(document_id), "step": "ocr_running", "duration_ms": duration_ms, "pages": len(pages), "provider": ocr_engine_used},
                    )
                    total_chars = sum(p.char_count for p in pages)
                    logger.info(
                        "ocr_complete",
                        extra={
                            "document_id": str(document_id),
                            "total_chars_before_ocr": total_chars_before_ocr,
                            "total_chars_after_ocr": total_chars,
                            "ocr_engine_used": ocr_engine_used,
                            "ocr_decision_reason": ocr_decision_reason,
                        },
                    )
                    # Store OCR decision metadata in document (explainable, deterministic)
                    meta = dict(document.processing_metadata or {})
                    meta["ocr_used"] = True
                    meta["ocr_engine_used"] = ocr_engine_used
                    meta["ocr_mode"] = ocr_mode_used
                    meta["ocr_decision_reason"] = ocr_decision_reason
                    if ocr_warnings:
                        meta["ocr_warnings"] = ocr_warnings
                    document.processing_metadata = meta
                    self.db.commit()
                except Exception as ocr_error:
                    logger.error(f"OCR failed for document {document_id}: {ocr_error}", exc_info=True)
                    # API engines: graceful fallback to local tesseract when provider fails
                    if selected_engine in ("google_document_ai", "mathpix"):
                        if strict_google_only:
                            raise RuntimeError(
                                "Strict OCR mode is enabled (OCR_STRICT_GOOGLE_ONLY=true): "
                                f"Google OCR failed and local fallback is disabled. Root error: {ocr_error}"
                            ) from ocr_error
                        try:
                            fallback_provider = get_ocr_provider_for_engine(getattr(settings, "OCR_FALLBACK_ENGINE", "tesseract"))
                            if not fallback_provider.validate_config():
                                raise RuntimeError("Fallback OCR provider is not configured")
                            ocr_warnings.append(f"fallback_used:{selected_engine}->" + getattr(fallback_provider, "provider_name", "tesseract"))
                            ocr_warnings.append(f"fallback_reason:{type(ocr_error).__name__}:{ocr_error}")
                            pages = await fallback_provider.run_ocr(document.file_path, language="eng")
                            ocr_engine_used = getattr(fallback_provider, "provider_name", "tesseract")
                            ocr_mode_used = ocr_mode_used or getattr(settings, "OCR_MODE", "local")
                            total_chars = sum(p.char_count for p in pages)
                            meta = dict(document.processing_metadata or {})
                            meta["ocr_used"] = True
                            meta["ocr_engine_used"] = ocr_engine_used
                            meta["ocr_mode"] = ocr_mode_used
                            meta["ocr_decision_reason"] = ocr_decision_reason
                            meta["ocr_fallback_used"] = True
                            meta["ocr_fallback_from_engine"] = selected_engine
                            meta["ocr_fallback_to_engine"] = ocr_engine_used
                            if ocr_warnings:
                                meta["ocr_warnings"] = ocr_warnings
                            document.processing_metadata = meta
                            self.db.commit()
                            logger.warning(
                                "ocr_fallback_success",
                                extra={
                                    "document_id": str(document_id),
                                    "from_engine": selected_engine,
                                    "to_engine": ocr_engine_used,
                                    "total_chars_after_fallback": total_chars,
                                },
                            )
                        except Exception as fallback_error:
                            raise RuntimeError(
                                f"OCR failed on engine '{selected_engine}' and fallback also failed: {fallback_error}"
                            ) from fallback_error
                    else:
                        raise RuntimeError(
                            f"OCR failed: {ocr_error}. Install Tesseract and Poppler (pdf2image). "
                            "Fail loudly; do not continue with empty pages."
                        ) from ocr_error
            else:
                # No OCR used — store decision metadata
                meta = dict(document.processing_metadata or {})
                meta["ocr_used"] = False
                meta["ocr_decision_reason"] = ocr_decision_reason
                if ocr_engine_used:
                    meta["ocr_engine_used"] = ocr_engine_used
                if ocr_mode_used:
                    meta["ocr_mode"] = ocr_mode_used
                if ocr_warnings:
                    meta["ocr_warnings"] = ocr_warnings
                document.processing_metadata = meta
                self.db.commit()
            
            # MIN_CHARS_EXTRACT checkpoint: Run AFTER OCR attempt
            # This ensures OCR has a chance to extract text before we fail
            total_chars = sum(p.char_count for p in pages)
            min_chars = getattr(settings, "MIN_CHARS_EXTRACT", 1)
            if total_chars < min_chars:
                meta = dict(document.processing_metadata or {})
                pdf_type = meta.get("pdf_type", "unknown")
                raise ValueError(
                    f"Extraction checkpoint failed: total chars {total_chars} < MIN_CHARS_EXTRACT ({min_chars}). "
                    f"extractor used, pdf_type={pdf_type}, OCR attempted={'yes' if ocr_attempted else 'no'}"
                )
            
            # Step 3: Normalize
            await self._update_status(document_id, DocumentStatus.NORMALIZING.value, processing_run)
            normalized_pages = self._normalize_text(pages)
            # Math: density + extraction + markers
            math_density_per_page = [compute_math_density(p.text) for p in normalized_pages]
            math_density_doc = sum(math_density_per_page) / len(math_density_per_page) if normalized_pages else 0.0
            meta = dict(document.processing_metadata or {})
            meta["math_density"] = math_density_doc
            meta["content_type_hint"] = "math" if math_density_doc >= MATH_DENSITY_THRESHOLD else None
            document.processing_metadata = meta
            self.db.commit()
            if self.math_provider.validate_config():
                math_blocks = self.math_provider.extract_math(str(document_id), normalized_pages)
                from app.domains.content_ingestion.models import MathBlock as MathBlockModel
                for mb in math_blocks:
                    self.db.add(MathBlockModel(
                        document_id=document_id,
                        page_no=mb.page_no,
                        block_type=mb.block_type,
                        raw_text=sanitize_pg_text(mb.raw_text),
                        normalized_text=sanitize_pg_text(mb.normalized_text),
                        bbox_json=mb.bbox_json,
                        confidence=float(mb.confidence) if mb.confidence is not None else None,
                        provider_name=mb.provider_name,
                    ))
                self.db.commit()
                normalized_pages = [BaselineMathExtractionProvider.inject_markers_into_text(p) for p in normalized_pages]

            # Synthetic TOC from PDF bookmarks when upload omitted chapter_map (any board / publisher)
            page_count_for_toc = len(normalized_pages)
            if document.source_type == "pdf" and (not document.chapter_map or len(document.chapter_map) == 0):
                from app.domains.content_ingestion.pdf_outline_chapter_map import (
                    build_chapter_map_from_pdf_outline,
                )

                try:
                    auto_map = build_chapter_map_from_pdf_outline(
                        document.file_path,
                        page_count_for_toc,
                        max_entries=int(getattr(settings, "PDF_OUTLINE_TOC_MAX_ENTRIES", 150)),
                        min_entries=int(getattr(settings, "PDF_OUTLINE_TOC_MIN_ENTRIES", 2)),
                    )
                except Exception as toc_exc:
                    logger.warning(
                        "pdf_outline_toc_skipped",
                        extra={"document_id": str(document_id), "error": str(toc_exc)},
                    )
                    auto_map = None
                if auto_map:
                    document.chapter_map = auto_map
                    meta_toc = dict(document.processing_metadata or {})
                    meta_toc["toc_source"] = "pdf_outline_auto"
                    meta_toc["toc_entry_count"] = len(auto_map)
                    document.processing_metadata = meta_toc
                    self.db.commit()
                    logger.info(
                        "pdf_outline_toc_applied",
                        extra={"document_id": str(document_id), "entries": len(auto_map)},
                    )
            
            # Step 4: Chunking (adaptive profiles for OCR vs digital)
            t0 = time.perf_counter()
            await self._update_status(document_id, DocumentStatus.CHUNKING.value, processing_run)
            meta_for_chunk = dict(document.processing_metadata or {})
            ocr_used_flag = bool(meta_for_chunk.get("ocr_used"))
            chunk_profile = "ocr_profile" if ocr_used_flag else "digital_profile"
            base_chunk_size = settings.CHUNK_SIZE_TOKENS_OCR if ocr_used_flag else settings.CHUNK_SIZE_TOKENS_DIGITAL
            base_overlap = settings.CHUNK_OVERLAP_TOKENS_OCR if ocr_used_flag else settings.CHUNK_OVERLAP_TOKENS_DIGITAL
            # Adaptive threshold: small docs use lower min-chunks
            pages_count = len(normalized_pages)
            min_pages_for_threshold = getattr(settings, "OCR_MIN_PAGES_FOR_TH RESHOLD", 30)
            if ocr_used_flag and pages_count < min_pages_for_threshold:
                min_chunks_threshold = getattr(settings, "OCR_MIN_CHUNKS_THRESHOLD_SMALL", 10)
                effective_threshold_used = min_chunks_threshold
            else:
                min_chunks_threshold = getattr(settings, "OCR_MIN_CHUNKS_THRESHOLD", 0)
                effective_threshold_used = min_chunks_threshold

            # Primary chunking pass
            chunks = self.chunker.chunk(
                normalized_pages,
                chunk_size_tokens=base_chunk_size,
                overlap_tokens=base_overlap,
                chapter_map=document.chapter_map,
            )
            total_chunks = len(chunks) if chunks else 0

            # Minimum chunk guarantee for OCR/scanned documents: rechunk with deterministic size if needed
            rechunk_attempted = False
            if ocr_used_flag and min_chunks_threshold and total_chunks < min_chunks_threshold:
                rechunk_attempted = True
                chunk_profile = "ocr_profile_rechunk"
                rechunk_size = getattr(settings, "OCR_RECHUNK_SIZE_TOKENS", 200)
                chunks = self.chunker.chunk(
                    normalized_pages,
                    chunk_size_tokens=rechunk_size,
                    overlap_tokens=base_overlap,
                    chapter_map=document.chapter_map,
                )
                total_chunks = len(chunks) if chunks else 0
                base_chunk_size = rechunk_size

            duration_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(
                "step_complete",
                extra={
                    "document_id": str(document_id),
                    "step": "chunking",
                    "duration_ms": duration_ms,
                    "chunks": total_chunks,
                    "pages": len(normalized_pages),
                    "chunk_profile_used": chunk_profile,
                    "chunk_size_tokens": base_chunk_size,
                    "chunk_overlap_tokens": base_overlap,
                    "rechunk_attempted": rechunk_attempted,
                    "effective_threshold_used": effective_threshold_used if ocr_used_flag else None,
                },
            )
            if not chunks:
                non_empty = sum(1 for p in normalized_pages if (p.text or "").strip())
                sample = (normalized_pages[0].text[:200] if normalized_pages and normalized_pages[0].text else "")
                raise ValueError(
                    f"Chunking checkpoint failed: chunks=0. pages={len(normalized_pages)}, non_empty_pages={non_empty}, sample_snippet={sample!r}"
                )
            page_topic_map = None
            if not document.chapter_map:
                meta_now = dict(document.processing_metadata or {})
                if meta_now.get("toc_source") != "pdf_outline_auto":
                    page_topic_map = self._infer_page_topic_labels(normalized_pages, document)
            topic_scope_mode, primary_topic_label, topic_fallback_fill_count = (
                self._ensure_chunk_topic_fallback_labels(
                    chunks,
                    document,
                    page_count=len(normalized_pages),
                    page_topic_map=page_topic_map,
                )
            )
            # Role tagging: assign chunk.metadata from structure_map or auto-heuristics
            min_chars_q = getattr(settings, "ROLE_MIN_CHARS_FOR_QUESTION_BLOCK", 200)
            assign_chunk_roles(
                chunks,
                getattr(document, "structure_map", None),
                min_chars_for_question_block=min_chars_q,
            )
            # Role distribution + QA metrics
            role_dist = compute_role_distribution(chunks)
            total_chunks = len(chunks)
            role_metrics = compute_role_tagging_metrics(role_dist, total_chunks)
            meta = dict(document.processing_metadata or {})
            meta["role_distribution"] = role_dist
            meta["role_tagging_metrics"] = role_metrics
            meta["chunking_summary"] = {
                "chunks_total": total_chunks,
                "chunk_size_tokens": base_chunk_size,
                "chunk_overlap_tokens": base_overlap,
                "chunk_profile": chunk_profile,
                "topic_scope_mode": topic_scope_mode,
                "primary_topic_label": primary_topic_label,
                "chunks_topic_fallback_filled": topic_fallback_fill_count,
                "catalog_toc_source": meta.get("toc_source"),
            }
            document.processing_metadata = meta
            logger.info(
                "role_tagging",
                extra={
                    "document_id": str(document_id),
                    "role_distribution": role_dist,
                    "role_tagging_metrics": role_metrics,
                },
            )
            processing_run.chunks_created = total_chunks
            self.db.commit()

            # Before embedding: filter empty chunks
            chunks = [c for c in chunks if (c.text or "").strip()]
            removed = processing_run.chunks_created - len(chunks)
            if removed:
                logger.warning(f"Filtered {removed} empty chunks", extra={"document_id": str(document_id)})
            if not chunks:
                raise ValueError("All chunks were empty after filtering; cannot embed.")
            
            # Step 5: Embedding
            t0 = time.perf_counter()
            await self._update_status(document_id, DocumentStatus.EMBEDDING.value, processing_run)
            self.embedding_provider = self._select_embedding_provider_for_document(document)
            strict_openai_embeddings = bool(getattr(settings, "OCR_STRICT_OPENAI_EMBEDDINGS", False))
            ocr_used_for_doc = bool((document.processing_metadata or {}).get("ocr_used"))
            if strict_openai_embeddings and ocr_used_for_doc and getattr(self.embedding_provider, "provider_name", "") != "openai":
                raise RuntimeError(
                    "Strict embedding mode is enabled (OCR_STRICT_OPENAI_EMBEDDINGS=true): "
                    f"OCR document resolved embedding provider '{getattr(self.embedding_provider, 'provider_name', 'unknown')}', expected 'openai'. "
                    "Set EMBEDDING_PROVIDER=openai and configure OPENAI_API_KEY."
                )
            chunk_texts = [chunk.text for chunk in chunks]
            try:
                embeddings = await self.embedding_provider.embed(chunk_texts)
            except RuntimeError as embed_err:
                low = str(embed_err).lower()
                if (
                    "429" not in low
                    and "quota" not in low
                    and "insufficient_quota" not in low
                    and "billing" not in low
                ):
                    raise
                if strict_openai_embeddings and ocr_used_for_doc:
                    raise RuntimeError(
                        "Strict embedding mode is enabled (OCR_STRICT_OPENAI_EMBEDDINGS=true): "
                        f"OpenAI embedding failed and fake fallback is disabled. Root error: {embed_err}"
                    ) from embed_err
                logger.warning(
                    "embedding_provider_quota_fallback_fake",
                    extra={"document_id": str(document_id), "error": str(embed_err)},
                )
                self.embedding_provider = FakeEmbeddingProvider()
                meta_fb = dict(document.processing_metadata or {})
                meta_fb["embedding_fallback"] = "fake_after_openai_quota"
                document.processing_metadata = meta_fb
                self.db.commit()
                embeddings = await self.embedding_provider.embed(chunk_texts)
            duration_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(
                "step_complete",
                extra={"document_id": str(document_id), "step": "embedding", "duration_ms": duration_ms, "count": len(embeddings), "provider": self.embedding_provider.provider_name},
            )
            
            if len(embeddings) != len(chunks):
                raise ValueError(f"Embedding count mismatch: {len(embeddings)} != {len(chunks)}")
            
            # Step 6: Indexing (store in vector DB)
            await self._update_status(document_id, DocumentStatus.INDEXING.value, processing_run)
            stored_count = await self.vector_store.upsert(
                chunks=chunks,
                vectors=embeddings,
                document_id=str(document_id),
                pack_id=str(document.pack_id),
                embedding_model=getattr(self.embedding_provider, "embedding_model", None) or self.embedding_provider.provider_name,
                embedding_dim=self.embedding_provider.get_embedding_dimension(),
                embedding_provider=self.embedding_provider.provider_name,
            )
            
            processing_run.vectors_stored = stored_count
            processing_run.progress_percentage = 90
            self.db.commit()
            
            # Step 7: QA Validation
            await self._update_status(document_id, DocumentStatus.QA_VALIDATION.value, processing_run)
            from app.domains.content_ingestion.services.qa_service import QAService
            qa_service = QAService(self.db)
            qa_validation = qa_service.run_qa_validation(document_id)
            
            # Step 8: Verify chunks and embeddings were saved.
            # Primary store is embedding_v for all active providers in this pipeline.
            # Keep legacy embedding as fallback for backward compatibility.
            active_provider = self.embedding_provider.provider_name
            chunks_with_embeddings = self.db.query(Chunk).filter(
                Chunk.document_id == document_id,
                (
                    Chunk.embedding_v.isnot(None)
                    | Chunk.embedding.isnot(None)
                )
            ).count()
            
            if chunks_with_embeddings == 0:
                error_msg = f"No chunks with embeddings found. Expected chunks but found 0. Document cannot be published."
                logger.error(f"Document {document_id} processing failed: {error_msg}")
                await self._update_status(
                    document_id,
                    DocumentStatus.FAILED.value,
                    processing_run,
                    error_code="NO_CHUNKS_SAVED",
                    error_message=error_msg,
                    remediation_hint="Document processing completed but no chunks were saved. Check embedding provider configuration and retry."
                )
                raise ValueError(error_msg)
            
            logger.info(f"Document {document_id} has {chunks_with_embeddings} chunks with embeddings saved")
            
            # Step 9: QA Validation
            await self._update_status(document_id, DocumentStatus.QA_VALIDATION.value, processing_run)
            from app.domains.content_ingestion.services.qa_service import QAService
            qa_service = QAService(self.db)
            qa_validation = qa_service.run_qa_validation(document_id)
            
            # Step 10: Publish (only if chunks and embeddings are saved)
            if qa_validation.qa_status == "passed":
                logger.info(f"Document {document_id} passed QA validation")
            else:
                logger.warning(f"Document {document_id} did not pass QA validation, but publishing anyway")
                logger.warning(f"QA checks: page_coverage={qa_validation.page_coverage_check}, "
                             f"text_density={qa_validation.text_density_check}, "
                             f"embedding_completeness={qa_validation.embedding_completeness_check}, "
                             f"vector_retrieval={qa_validation.vector_retrieval_check}")
            
            # Verify again before publishing (embedding_v primary, legacy embedding fallback)
            final_chunk_count = self.db.query(Chunk).filter(
                Chunk.document_id == document_id,
                (
                    Chunk.embedding_v.isnot(None)
                    | Chunk.embedding.isnot(None)
                )
            ).count()
            
            if final_chunk_count == 0:
                error_msg = f"Chunks verification failed before publishing. Found 0 chunks with embeddings."
                logger.error(f"Document {document_id} cannot be published: {error_msg}")
                await self._update_status(
                    document_id,
                    DocumentStatus.FAILED.value,
                    processing_run,
                    error_code="CHUNKS_VERIFICATION_FAILED",
                    error_message=error_msg,
                    remediation_hint="Chunks were not properly saved. Check vector store configuration and retry."
                )
                raise ValueError(error_msg)
            
            # Publish only if chunks are verified
            await self._update_status(document_id, DocumentStatus.PUBLISHED.value, processing_run)
            document.processed_at = processing_run.completed_at
            processing_run.status = DocumentStatus.PUBLISHED.value
            processing_run.progress_percentage = 100
            logger.info(f"Document {document_id} published successfully with {final_chunk_count} chunks (QA status: {qa_validation.qa_status})")
            
            from datetime import datetime, timezone
            processing_run.completed_at = datetime.now(timezone.utc)
            self.db.commit()
            
            return document
            
        except Exception as e:
            logger.error(f"Ingestion failed for document {document_id}: {e}", exc_info=True)
            # Reset failed transaction state before any additional DB access in this handler.
            try:
                self.db.rollback()
            except Exception:
                pass
            
            # Provide more detailed error messages based on error type
            error_str = str(e)
            error_code = "INGESTION_ERROR"
            remediation_hint = "Check logs and retry document processing"
            # Persist failure context (additive, no API changes)
            try:
                document = self.db.query(Document).filter(Document.id == document_id).first()
                if document:
                    meta = dict(document.processing_metadata or {})
                    meta["failed_step"] = processing_run.current_step
                    meta["error_code"] = error_code
                    meta["provider_context"] = {
                        "ocr": getattr(self.ocr_provider, "provider_name", None),
                        "embedding": getattr(self.embedding_provider, "provider_name", None),
                        "vector_store": getattr(self.vector_store, "provider_name", None),
                        "chunker": getattr(self.chunker, "provider_name", None),
                    }
                    document.processing_metadata = meta
                    self.db.commit()
            except Exception:
                pass
            
            if isinstance(e, OcrPreflightError):
                error_code = "OCR_ERROR"
                remediation_hint = error_str  # Preflight error already contains actionable instructions
            elif "OPENAI_API_KEY" in error_str or "api key" in error_str.lower() or "authentication" in error_str.lower():
                error_code = "MISSING_API_KEY"
                remediation_hint = "Set OPENAI_API_KEY in your .env file and restart the backend."
            elif "tesseract" in error_str.lower() or "ocr" in error_str.lower() or "TesseractNotFoundError" in error_str:
                error_code = "OCR_ERROR"
                remediation_hint = "Install Tesseract OCR: https://github.com/UB-Mannheim/tesseract/wiki (Windows) or 'sudo apt-get install tesseract-ocr' (Linux)"
            elif "google document ai" in error_str.lower() and ("timeout" in error_str.lower() or "deadline" in error_str.lower()):
                error_code = "OCR_TIMEOUT"
                remediation_hint = (
                    "Google OCR timed out. The backend will retry with exponential backoff. "
                    "If it still fails, increase OCR_API_TIMEOUT_SECONDS and verify Document AI quota/region health."
                )
            elif "large pdf requires async batch ocr" in error_str.lower():
                error_code = "OCR_CONFIG_ERROR"
                remediation_hint = (
                    "Large PDF requires async batch OCR, but Cloud Storage is not configured. "
                    "Set DOCUMENT_AI_GCS_BUCKET (and optional DOCUMENT_AI_GCS_PREFIX), then retry."
                )
            elif "file not found" in error_str.lower() or "FileNotFoundError" in error_str:
                error_code = "FILE_NOT_FOUND"
                remediation_hint = "The uploaded file may have been deleted or moved. Try re-uploading the document."
            elif "embedding" in error_str.lower() or "Embedding" in error_str:
                error_code = "EMBEDDING_ERROR"
                remediation_hint = "Check OPENAI_API_KEY, network connectivity, and OpenAI service status."
            elif "vector" in error_str.lower() or "pgvector" in error_str.lower() or "database" in error_str.lower():
                error_code = "VECTOR_STORE_ERROR"
                remediation_hint = "Check database connection, ensure pgvector extension is enabled, and verify database permissions."
            elif "timed out" in error_str.lower() and "extraction" in error_str.lower():
                error_code = "EXTRACTION_TIMEOUT"
                remediation_hint = (
                    "Text extraction timed out. The PDF may be very large, corrupted, or password-protected. "
                    "Try splitting the document, enabling force_ocr, or increasing EXTRACTION_TIMEOUT_SECONDS."
                )
            elif "No text extracted" in error_str or "empty" in error_str.lower():
                error_code = "TEXT_EXTRACTION_ERROR"
                remediation_hint = "The document may be corrupted, password-protected, or in an unsupported format. Try a different document or enable OCR."
            
            await self._update_status(
                document_id,
                DocumentStatus.FAILED.value,
                processing_run,
                error_code=error_code,
                error_message=error_str,
                remediation_hint=remediation_hint
            )
            raise

    async def reprocess_document(self, document_id: UUID, start_step: str = "text_extracting") -> Document:
        """
        Internal reprocessing entrypoint (no endpoint changes).
        Currently re-runs full pipeline; start_step is stored for audit/future resuming.
        """
        document = self.db.query(Document).filter(Document.id == document_id).first()
        if not document:
            raise ValueError(f"Document {document_id} not found")
        if document.status in _INGESTION_ACTIVE_STATUSES:
            raise ValueError(
                f"Cannot reprocess document {document_id} while ingestion is in progress ({document.status})"
            )
        meta = dict(document.processing_metadata or {})
        meta["reprocess_from_step"] = start_step
        meta["reprocess_embedding_provider"] = getattr(self.embedding_provider, "provider_name", None)
        meta["reprocess_ocr_provider"] = getattr(self.ocr_provider, "provider_name", None)
        document.processing_metadata = meta
        # Re-run from published requires moving out of terminal state (ingest skips published)
        if document.status == DocumentStatus.PUBLISHED.value:
            document.status = DocumentStatus.UPLOADED.value
            document.error_code = None
            document.error_message = None
            if hasattr(document, "remediation_hint"):
                document.remediation_hint = None
        self.db.commit()
        return await self.ingest_document(document_id)

    @staticmethod
    def _quick_pdf_page_count(file_path: str) -> Optional[int]:
        """
        Cheap page-count using pypdf xref walk. Often much faster than pdfplumber.open
        for huge textbooks, so SSE/UI can show total_pages before extraction starts.
        """
        try:
            from pypdf import PdfReader

            reader = PdfReader(file_path)
            return len(reader.pages)
        except Exception as e:
            logger.warning(
                "quick_pdf_page_count_failed",
                extra={"file_path": file_path, "error": str(e)},
            )
            return None

    async def _extract_text(
        self,
        document: Document,
        processing_run: "DocumentProcessingRun",
    ) -> List:
        """
        Extract text from document with live per-page progress reporting.

        For PDFs, progress is committed to the DB every
        EXTRACTION_PROGRESS_BATCH_SIZE pages so the SSE stream (and UI) can
        display "page X of Y" rather than a frozen 10% for minutes.

        document.total_pages is written as soon as the page count is known
        (before any page is fully extracted) so the UI shows the denominator
        early.
        """
        file_path = document.file_path
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Document file not found: {file_path}")

        if document.source_type == "pdf":
            batch = int(getattr(settings, "EXTRACTION_PROGRESS_BATCH_SIZE", 10))
            timeout = float(getattr(settings, "EXTRACTION_TIMEOUT_SECONDS", 3600.0))
            try:
                size_bytes = os.path.getsize(file_path)
            except OSError:
                size_bytes = 0
            large_mb = float(getattr(settings, "EXTRACTION_LARGE_FILE_MB", 12.0))
            large_batch = int(getattr(settings, "EXTRACTION_PROGRESS_BATCH_SIZE_LARGE", 3))
            if size_bytes >= int(large_mb * 1024 * 1024):
                batch = min(batch, large_batch)
                logger.info(
                    "extraction_progress_batch_reduced",
                    extra={
                        "document_id": str(document.id),
                        "file_bytes": size_bytes,
                        "large_threshold_mb": large_mb,
                        "effective_batch": batch,
                    },
                )

            # Fast xref-based page count (pypdf) — pdfplumber.open can stall minutes on huge PDFs
            # before the first queue event; committing total_pages early fixes empty UI / N/A pages.
            quick_pages = self._quick_pdf_page_count(file_path)
            if quick_pages is not None and quick_pages >= 0:
                document.total_pages = quick_pages
                processing_run.pages_processed = 0
                processing_run.progress_percentage = 1
                try:
                    self.db.commit()
                    logger.info(
                        "extraction_quick_page_count",
                        extra={
                            "document_id": str(document.id),
                            "total_pages_estimate": quick_pages,
                        },
                    )
                except Exception as db_exc:
                    logger.warning(f"Quick page count commit failed (non-fatal): {db_exc}")

            async def _on_page_progress(current_page: int, total_pages: int) -> None:
                """Called every `batch` pages from the extractor thread."""
                if current_page == 0:
                    # First event: total_pages is now known — write it immediately
                    document.total_pages = total_pages
                    processing_run.progress_percentage = 1
                    logger.info(
                        "extraction_total_pages_known",
                        extra={
                            "document_id": str(document.id),
                            "total_pages": total_pages,
                        },
                    )
                else:
                    processing_run.pages_processed = current_page
                    # Scale 1–10%: text_extracting owns the first 10 percentage points
                    if total_pages > 0:
                        pct = max(1, min(10, int(current_page / total_pages * 10)))
                        processing_run.progress_percentage = pct
                    logger.debug(
                        "extraction_progress",
                        extra={
                            "document_id": str(document.id),
                            "pages_processed": current_page,
                            "total_pages": total_pages,
                        },
                    )
                try:
                    self.db.commit()
                except Exception as db_exc:
                    # Non-fatal: progress update failed, pipeline continues
                    logger.warning(f"Progress DB commit failed (non-fatal): {db_exc}")

            first_prog = float(
                getattr(settings, "EXTRACTION_FIRST_PROGRESS_TIMEOUT_SECONDS", 300.0)
            )
            try:
                return await self.pdf_extractor.extract_text(
                    file_path,
                    on_progress=_on_page_progress,
                    timeout_seconds=timeout,
                    progress_batch=batch,
                    known_total_pages=quick_pages,
                    first_progress_timeout_seconds=first_prog,
                )
            except RuntimeError as exc:
                # Timeout or corrupt-file errors from the extractor are re-raised
                # with a specific error_code so the failure handler maps them correctly
                if "timed out" in str(exc).lower():
                    raise RuntimeError(
                        f"Text extraction failed: {exc}"
                    ) from exc
                raise

        elif document.source_type == "docx":
            if not document.chapter_map or len(document.chapter_map) == 0:
                from app.domains.content_ingestion.docx_structure import try_extract_docx_structured

                structured = try_extract_docx_structured(file_path)
                if structured:
                    pages, auto_map = structured
                    document.chapter_map = auto_map
                    meta = dict(document.processing_metadata or {})
                    meta["toc_source"] = "docx_headings_auto"
                    meta["toc_entry_count"] = len(auto_map)
                    document.processing_metadata = meta
                    self.db.commit()
                    logger.info(
                        "docx_structured_applied",
                        extra={"document_id": str(document.id), "sections": len(pages)},
                    )
                    return pages
            return await self.docx_extractor.extract_text(file_path)
        else:
            raise ValueError(f"Unsupported source type: {document.source_type}")
    
    def _needs_ocr(self, pages: List, source_type: str) -> bool:
        """Determine if OCR is needed based on text density."""
        if source_type != "pdf":
            return False
        
        if not pages:
            return True
        
        # Check total chars first - if 0, OCR is required regardless of pdf_type heuristic
        total_chars = sum(p.char_count for p in pages)
        if total_chars == 0:
            return True
        
        # Check average chars per page - if below threshold, needs OCR
        avg_chars = total_chars / len(pages) if pages else 0
        if avg_chars < settings.SCANNED_THRESHOLD_CHARS:
            return True
        
        return False
    
    async def _run_ocr(self, document: Document, pages: List) -> List:
        """Run OCR on document."""
        if not self.ocr_provider.validate_config():
            raise RuntimeError(f"OCR provider {settings.OCR_ENGINE} not properly configured")
        
        return await self.ocr_provider.run_ocr(document.file_path)
    
    def _normalize_text(self, pages: List) -> List:
        """Normalize extracted text."""
        # Simple normalization: clean whitespace, remove extra newlines
        from app.domains.content_ingestion.providers.base import PageText as PageTextBase
        normalized = []
        for page in pages:
            # Clean text (PostgreSQL rejects NUL in strings)
            text = sanitize_pg_text(page.text)
            # Remove excessive whitespace
            lines = [line.strip() for line in text.split("\n") if line.strip()]
            normalized_text = "\n".join(lines)
            
            # Create new PageText with normalized text
            normalized.append(PageTextBase(
                page_no=page.page_no,
                text=normalized_text,
                char_count=len(normalized_text),
                ocr_confidence=page.ocr_confidence,
                ocr_engine=page.ocr_engine
            ))
        
        return normalized
    
    async def _update_status(
        self,
        document_id: UUID,
        status: str,
        processing_run: DocumentProcessingRun,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        remediation_hint: Optional[str] = None
    ):
        """Update document and processing run status."""
        try:
            document = self.db.query(Document).filter(Document.id == document_id).first()
        except PendingRollbackError:
            self.db.rollback()
            document = self.db.query(Document).filter(Document.id == document_id).first()
        if document:
            document.status = status
            if error_code:
                document.error_code = error_code
            if error_message:
                document.error_message = error_message
            if remediation_hint:
                document.remediation_hint = remediation_hint
        
        processing_run.status = status
        processing_run.current_step = status
        if error_code:
            processing_run.error_code = error_code
        if error_message:
            processing_run.error_message = error_message
        if remediation_hint:
            processing_run.remediation_hint = remediation_hint
        
        # Update progress percentage based on status (overall pipeline coarse milestones).
        # Use a low value for text_extracting — granular 1–10% comes from per-page commits in _extract_text.
        status_progress = {
            DocumentStatus.TEXT_EXTRACTING.value: 1,
            DocumentStatus.OCR_RUNNING.value: 20,
            DocumentStatus.NORMALIZING.value: 30,
            DocumentStatus.CHUNKING.value: 40,
            DocumentStatus.EMBEDDING.value: 60,
            DocumentStatus.INDEXING.value: 80,
            DocumentStatus.QA_VALIDATION.value: 90,
            DocumentStatus.PUBLISHED.value: 100,
            DocumentStatus.FAILED.value: 0,
        }
        processing_run.progress_percentage = status_progress.get(status, 0)
        
        try:
            self.db.commit()
        except PendingRollbackError:
            # Recover from invalid transaction state and retry status update once.
            self.db.rollback()
            fresh_document = self.db.query(Document).filter(Document.id == document_id).first()
            if fresh_document:
                fresh_document.status = status
                if error_code:
                    fresh_document.error_code = error_code
                if error_message:
                    fresh_document.error_message = error_message
                if remediation_hint:
                    fresh_document.remediation_hint = remediation_hint

            fresh_run = self.db.query(DocumentProcessingRun).filter(
                DocumentProcessingRun.id == processing_run.id
            ).first()
            if fresh_run:
                fresh_run.status = status
                fresh_run.current_step = status
                fresh_run.progress_percentage = status_progress.get(status, 0)
                if error_code:
                    fresh_run.error_code = error_code
                if error_message:
                    fresh_run.error_message = error_message
                if remediation_hint:
                    fresh_run.remediation_hint = remediation_hint
            self.db.commit()
        except StaleDataError:
            # Can happen if a retry/reset removed processing rows while an old worker is still running.
            self.db.rollback()
            fresh_document = self.db.query(Document).filter(Document.id == document_id).first()
            if fresh_document:
                fresh_document.status = status
                if error_code:
                    fresh_document.error_code = error_code
                if error_message:
                    fresh_document.error_message = error_message
                if remediation_hint:
                    fresh_document.remediation_hint = remediation_hint

            fresh_run = self.db.query(DocumentProcessingRun).filter(
                DocumentProcessingRun.id == processing_run.id
            ).first()
            if fresh_run:
                fresh_run.status = status
                fresh_run.current_step = status
                fresh_run.progress_percentage = status_progress.get(status, 0)
                if error_code:
                    fresh_run.error_code = error_code
                if error_message:
                    fresh_run.error_message = error_message
                if remediation_hint:
                    fresh_run.remediation_hint = remediation_hint
            self.db.commit()
            logger.warning(
                "status_update_recovered_after_stale_data",
                extra={"document_id": str(document_id), "status": status},
            )
        logger.info(f"Updated document {document_id} status to {status}")

    def apply_structure_map_to_chunks(self, document_id: UUID) -> int:
        """
        Reapply structure_map to existing chunks. Updates role in metadata_json.
        Does NOT re-run OCR or chunking. Returns count of chunks updated.
        """
        from app.domains.content_ingestion.services.role_tagger import (
            get_role_from_structure_map,
            compute_role_distribution,
            compute_role_tagging_metrics,
            CHUNK_ROLES,
        )
        document = self.db.query(Document).filter(Document.id == document_id).first()
        if not document:
            raise ValueError(f"Document {document_id} not found")
        structure_map = document.structure_map
        if not structure_map or not isinstance(structure_map, list):
            logger.info(f"No structure_map for document {document_id}; nothing to apply")
            return 0
        chunks = self.db.query(Chunk).filter(Chunk.document_id == document_id).all()
        updated = 0
        for ch in chunks:
            override = get_role_from_structure_map(
                ch.page_start_pdf,
                ch.page_end_pdf,
                structure_map,
            )
            if not override or override not in CHUNK_ROLES:
                continue
            meta = dict(ch.metadata_json or {})
            old_role = meta.get("role", "unknown")
            meta["role"] = override
            meta["role_source"] = "manual"
            if "auto_role" not in meta:
                meta["auto_role"] = old_role
            if "auto_confidence" not in meta:
                meta["auto_confidence"] = 0.0
            ch.metadata_json = meta
            updated += 1
        if updated:
            role_dist = compute_role_distribution([
                type("_", (), {"metadata": ch.metadata_json})() for ch in chunks
            ])
            role_metrics = compute_role_tagging_metrics(role_dist, len(chunks))
            proc = dict(document.processing_metadata or {})
            proc["role_distribution"] = role_dist
            proc["role_tagging_metrics"] = role_metrics
            document.processing_metadata = proc
        self.db.commit()
        logger.info(f"apply_structure_map_to_chunks: document_id={document_id}, updated={updated}")
        return updated
