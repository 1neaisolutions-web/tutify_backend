"""
OCR provider implementations.
"""
import os
import shutil
import platform
import asyncio
import json
import time
from io import BytesIO
from typing import List, Optional
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4

from app.core.logging import get_logger
from app.core.config import settings
from app.domains.content_ingestion.providers.base import OCRProvider, PageText
from app.domains.content_ingestion.providers.ocr_preflight import OcrPreflight

logger = get_logger(__name__)


class TesseractOCRProvider(OCRProvider):
    """Tesseract OCR provider (free, MVP)."""
    
    provider_name = "tesseract"
    
    def __init__(self):
        """Initialize Tesseract OCR provider with binary discovery."""
        try:
            import pytesseract
            from pdf2image import convert_from_path
            self.pytesseract = pytesseract
            self.convert_from_path = convert_from_path
            
            # Discover Tesseract binary
            self._setup_tesseract_binary()
            
            # Discover Poppler path
            self.poppler_path = self._find_poppler_path()
        except ImportError as e:
            logger.warning(f"Tesseract dependencies not installed: {e}")
            self.pytesseract = None
            self.convert_from_path = None
            self.poppler_path = None
    
    def _setup_tesseract_binary(self):
        """Setup Tesseract binary path using discovery logic."""
        if self.pytesseract is None:
            return
        
        # Check explicit env var first
        tesseract_cmd = os.getenv("TESSERACT_CMD")
        if tesseract_cmd and os.path.exists(tesseract_cmd):
            self.pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
            logger.info(f"Using Tesseract from TESSERACT_CMD: {tesseract_cmd}")
            return
        
        # Check PATH
        tesseract_path = shutil.which("tesseract")
        if tesseract_path:
            self.pytesseract.pytesseract.tesseract_cmd = tesseract_path
            logger.info(f"Using Tesseract from PATH: {tesseract_path}")
            return
        
        # Windows-specific default locations
        if platform.system() == "Windows":
            default_paths = [
                r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            ]
            for path in default_paths:
                if os.path.exists(path):
                    self.pytesseract.pytesseract.tesseract_cmd = path
                    logger.info(f"Using Tesseract from default Windows location: {path}")
                    return
        
        # If not found, pytesseract will try default behavior
        logger.warning("Tesseract binary not found via discovery, pytesseract will use default")
    
    def _find_poppler_path(self) -> Optional[str]:
        """Find Poppler directory path."""
        # Check explicit env var first
        poppler_path = os.getenv("POPPLER_PATH")
        if poppler_path:
            poppler_dir = Path(poppler_path)
            if poppler_dir.is_dir():
                pdftoppm = poppler_dir / ("pdftoppm.exe" if platform.system() == "Windows" else "pdftoppm")
                if pdftoppm.exists():
                    logger.info(f"Using Poppler from POPPLER_PATH: {poppler_path}")
                    return str(poppler_dir)
        
        # Check PATH
        pdftoppm_path = shutil.which("pdftoppm")
        if pdftoppm_path:
            poppler_dir = str(Path(pdftoppm_path).parent)
            logger.info(f"Using Poppler from PATH: {poppler_dir}")
            return poppler_dir
        
        return None
    
    def validate_config(self) -> bool:
        """Check if Tesseract is available using preflight checks."""
        if self.pytesseract is None:
            return False
        
        try:
            # Use preflight check for robust validation
            preflight_result = OcrPreflight.check()
            if not preflight_result["tesseract_found"]:
                return False
            
            # Also verify pytesseract can access it
            self.pytesseract.get_tesseract_version()
            return True
        except Exception as e:
            logger.warning(f"Tesseract validation failed: {e}")
            return False
    
    async def run_ocr(
        self,
        pdf_path: str,
        language: str = "eng",
        **kwargs
    ) -> List[PageText]:
        """
        Run OCR on PDF using Tesseract.
        
        Args:
            pdf_path: Path to PDF file
            language: Language code (default: "eng")
            
        Returns:
            List of PageText objects
        """
        if not self.validate_config():
            raise RuntimeError("Tesseract OCR not properly configured")
        
        # Ensure PDF path is absolute
        pdf_path_abs = str(Path(pdf_path).resolve())
        if not os.path.exists(pdf_path_abs):
            raise FileNotFoundError(f"PDF file not found: {pdf_path_abs}")
        
        first_page = kwargs.get("first_page")
        last_page = kwargs.get("last_page")
        dpi = int(kwargs.get("dpi") or 300)
        thread_count = kwargs.get("thread_count")

        range_msg = ""
        if first_page is not None or last_page is not None:
            range_msg = f" pages={first_page or '?'}..{last_page or '?'}"

        logger.info(f"Running Tesseract OCR on {pdf_path_abs}{range_msg} (language: {language}, dpi: {dpi})")
        
        pages_text = []
        
        try:
            # Convert PDF to images (use poppler_path if available)
            convert_kwargs = {"dpi": dpi}
            # Support converting only a page range to reduce memory usage
            if first_page is not None:
                convert_kwargs["first_page"] = int(first_page)
            if last_page is not None:
                convert_kwargs["last_page"] = int(last_page)
            # Allow pdf2image to use multiple threads when supported
            if thread_count is not None:
                try:
                    convert_kwargs["thread_count"] = int(thread_count)
                except Exception:
                    pass
            if self.poppler_path:
                # Ensure poppler_path is absolute
                poppler_path_abs = str(Path(self.poppler_path).resolve())
                convert_kwargs["poppler_path"] = poppler_path_abs
                logger.info(f"Using Poppler path: {poppler_path_abs}")
                # Prepend Poppler bin directory to PATH for DLL resolution on Windows
                # Prepend (not append) ensures DLLs are found before system paths
                if platform.system() == "Windows":
                    current_path = os.environ.get("PATH", "")
                    if poppler_path_abs not in current_path:
                        os.environ["PATH"] = f"{poppler_path_abs};{current_path}"
                        logger.debug(f"Prepended Poppler to PATH: {poppler_path_abs}")
            images = self.convert_from_path(pdf_path_abs, **convert_kwargs)
            
            # If we converted a specific range, page numbers should match the PDF page numbers
            base_page_no = int(first_page) if first_page is not None else 1
            for idx, image in enumerate(images, start=0):
                page_num = base_page_no + idx
                try:
                    # Run OCR on image
                    text = self.pytesseract.image_to_string(image, lang=language)
                    char_count = len(text.strip())
                    
                    # Get confidence (average)
                    try:
                        data = self.pytesseract.image_to_data(image, lang=language, output_type=self.pytesseract.Output.DICT)
                        confidences = [int(conf) for conf in data['conf'] if int(conf) > 0]
                        avg_confidence = sum(confidences) / len(confidences) / 100.0 if confidences else None
                    except Exception:
                        avg_confidence = None
                    
                    pages_text.append(PageText(
                        page_no=page_num,
                        text=text,
                        char_count=char_count,
                        ocr_confidence=avg_confidence,
                        ocr_engine="tesseract"
                    ))
                    
                    logger.debug(f"OCR completed for page {page_num}: {char_count} chars")
                    
                except Exception as e:
                    logger.error(f"Error processing page {page_num}: {e}")
                    # Add empty page on error
                    pages_text.append(PageText(
                        page_no=page_num,
                        text="",
                        char_count=0,
                        ocr_engine="tesseract"
                    ))
            
            logger.info(f"OCR completed: {len(pages_text)} pages processed")
            return pages_text
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Tesseract OCR failed: {error_msg}")
            # Provide more context for pdf2image errors
            if "pdf2image" in error_msg.lower() or "pdfinfo" in error_msg.lower() or "page count" in error_msg.lower():
                if self.poppler_path:
                    poppler_path_abs = str(Path(self.poppler_path).resolve())
                    pdfinfo_exe = Path(poppler_path_abs) / ("pdfinfo.exe" if platform.system() == "Windows" else "pdfinfo")
                    if pdfinfo_exe.exists():
                        error_msg += f" (Poppler found at {poppler_path_abs}, pdfinfo.exe exists but may have DLL dependency issues)"
                    else:
                        error_msg += f" (Poppler path {poppler_path_abs} exists but pdfinfo.exe not found)"
                else:
                    error_msg += " (Poppler path not configured)"
            raise RuntimeError(f"OCR processing failed: {error_msg}")


class EasyOCRProvider(OCRProvider):
    """EasyOCR provider (free, no binary installation needed)."""
    
    provider_name = "easyocr"
    
    def __init__(self):
        """Initialize EasyOCR provider."""
        try:
            import easyocr
            from pdf2image import convert_from_path
            self.easyocr_reader = None  # Lazy initialization
            self.convert_from_path = convert_from_path
            self._initialized = False
            self._import_error = None
        except (ImportError, OSError) as e:
            logger.warning(f"EasyOCR dependencies not available: {e}")
            logger.warning("Install with: pip install easyocr pdf2image")
            logger.warning("On Windows, also install: Microsoft Visual C++ Redistributable")
            self.easyocr_reader = None
            self.convert_from_path = None
            self._initialized = False
            self._import_error = str(e)
    
    def _init_reader(self, languages: List[str] = None):
        """Initialize EasyOCR reader (lazy loading)."""
        if self._initialized:
            return
        
        if self.easyocr_reader is None:
            try:
                import easyocr
                # EasyOCR supports 80+ languages, default to English
                lang_list = languages or ['en']
                logger.info(f"Initializing EasyOCR reader with languages: {lang_list}")
                self.easyocr_reader = easyocr.Reader(lang_list, gpu=False)  # Use CPU for compatibility
                self._initialized = True
                logger.info("EasyOCR reader initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize EasyOCR reader: {e}")
                raise RuntimeError(f"EasyOCR initialization failed: {str(e)}")
    
    def validate_config(self) -> bool:
        """Check if EasyOCR is available."""
        if hasattr(self, '_import_error') and self._import_error:
            return False
        if self.easyocr_reader is None:
            try:
                import easyocr
                from pdf2image import convert_from_path
                return True
            except (ImportError, OSError):
                return False
        return self._initialized
    
    async def run_ocr(
        self,
        pdf_path: str,
        language: str = "eng",
        **kwargs
    ) -> List[PageText]:
        """
        Run OCR on PDF using EasyOCR.
        
        Args:
            pdf_path: Path to PDF file
            language: Language code (default: "eng" -> "en" for EasyOCR)
            
        Returns:
            List of PageText objects
        """
        if not self.validate_config():
            raise RuntimeError("EasyOCR not properly configured. Install with: pip install easyocr pdf2image")
        
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        
        # Map language codes: eng -> en, etc.
        lang_map = {"eng": "en", "en": "en", "ur": "ur", "ar": "ar"}
        easyocr_lang = lang_map.get(language.lower(), "en")
        
        logger.info(f"Running EasyOCR on {pdf_path} (language: {easyocr_lang})")
        
        # Initialize reader if not already done
        self._init_reader([easyocr_lang])
        
        pages_text = []
        
        try:
            # Convert PDF to images
            images = self.convert_from_path(pdf_path, dpi=300)
            
            for page_num, image in enumerate(images, start=1):
                try:
                    # Run OCR on image
                    results = self.easyocr_reader.readtext(image)
                    
                    # Combine all detected text
                    text_lines = [result[1] for result in results]  # result[1] is the text
                    text = "\n".join(text_lines)
                    char_count = len(text.strip())
                    
                    # Calculate average confidence
                    confidences = [result[2] for result in results]  # result[2] is confidence
                    avg_confidence = sum(confidences) / len(confidences) if confidences else None
                    
                    pages_text.append(PageText(
                        page_no=page_num,
                        text=text,
                        char_count=char_count,
                        ocr_confidence=avg_confidence,
                        ocr_engine="easyocr"
                    ))
                    
                    logger.debug(f"EasyOCR completed for page {page_num}: {char_count} chars")
                    
                except Exception as e:
                    logger.error(f"Error processing page {page_num} with EasyOCR: {e}")
                    # Add empty page on error
                    pages_text.append(PageText(
                        page_no=page_num,
                        text="",
                        char_count=0,
                        ocr_engine="easyocr"
                    ))
            
            logger.info(f"EasyOCR completed: {len(pages_text)} pages processed")
            return pages_text
            
        except Exception as e:
            logger.error(f"EasyOCR failed: {e}")
            raise RuntimeError(f"OCR processing failed: {str(e)}")


class MathpixOCRProvider(OCRProvider):
    """Mathpix OCR provider (paid, future-ready stub)."""
    
    provider_name = "mathpix"
    
    def __init__(self):
        """Initialize Mathpix OCR provider (stub for MVP)."""
        self.app_id = os.getenv("MATHPIX_APP_ID")
        self.app_key = os.getenv("MATHPIX_APP_KEY")
    
    def validate_config(self) -> bool:
        """Check if Mathpix is configured (stub - always False for MVP)."""
        # In MVP, Mathpix is not used
        return False
    
    async def run_ocr(
        self,
        pdf_path: str,
        language: str = "eng",
        **kwargs
    ) -> List[PageText]:
        """
        Run OCR on PDF using Mathpix (stub - not implemented in MVP).
        
        This is a placeholder for future Mathpix integration.
        """
        raise NotImplementedError(
            "Mathpix OCR is not implemented in MVP. "
            "Set OCR_ENGINE=tesseract for free OCR, or implement Mathpix integration."
        )


class GoogleDocumentAIOCRProvider(OCRProvider):
    """Google Document AI OCR provider (API, optional). Never crashes if keys missing."""
    
    provider_name = "google_document_ai"
    
    def __init__(self):
        self._credentials = getattr(settings, "GOOGLE_APPLICATION_CREDENTIALS", None) or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        self._api_key = getattr(settings, "DOCUMENT_AI_API_KEY", None) or os.getenv("DOCUMENT_AI_API_KEY")
        self._project_id = getattr(settings, "DOCUMENT_AI_PROJECT_ID", None) or os.getenv("DOCUMENT_AI_PROJECT_ID")
        self._location = getattr(settings, "DOCUMENT_AI_LOCATION", "us") or os.getenv("DOCUMENT_AI_LOCATION", "us")
        self._processor_id = getattr(settings, "DOCUMENT_AI_PROCESSOR_ID", None) or os.getenv("DOCUMENT_AI_PROCESSOR_ID")
    
    def validate_config(self) -> bool:
        # We currently support service-account flow for Document AI.
        # API key-only mode is not enough for processor invocation.
        if not self._credentials:
            return False
        if not os.path.exists(self._credentials):
            return False
        if not self._project_id:
            try:
                with open(self._credentials, "r", encoding="utf-8") as f:
                    self._project_id = json.load(f).get("project_id")
            except Exception:
                self._project_id = None
        if not self._project_id:
            return False
        if not self._location:
            return False
        return bool(self._processor_id)

    def validate_strict_config(self) -> tuple[bool, Optional[str]]:
        if not self._credentials:
            return False, "GOOGLE_APPLICATION_CREDENTIALS is not set."
        if not os.path.exists(self._credentials):
            return False, f"GOOGLE_APPLICATION_CREDENTIALS not found at '{self._credentials}'."
        if not self._processor_id:
            return False, "DOCUMENT_AI_PROCESSOR_ID is not set."
        if not self._location:
            return False, "DOCUMENT_AI_LOCATION is not set."
        if not self._project_id:
            try:
                with open(self._credentials, "r", encoding="utf-8") as f:
                    self._project_id = json.load(f).get("project_id")
            except Exception:
                self._project_id = None
        if not self._project_id:
            return False, "DOCUMENT_AI_PROJECT_ID is missing and could not be read from service account JSON."
        return True, None

    @staticmethod
    def _parse_retry_delays(raw: str) -> List[int]:
        vals: List[int] = []
        for p in (raw or "").split(","):
            p = p.strip()
            if not p:
                continue
            try:
                vals.append(max(1, int(p)))
            except Exception:
                continue
        return vals or [5, 15, 30, 60]

    @staticmethod
    def _build_pdf_window_bytes(
        pdf_path: str,
        first_page: Optional[int],
        last_page: Optional[int],
    ) -> bytes:
        """Return compact page-window bytes for large PDFs to reduce payload size."""
        with open(pdf_path, "rb") as f:
            full_bytes = f.read()
        if first_page is None and last_page is None:
            return full_bytes
        try:
            from pypdf import PdfReader, PdfWriter
            reader = PdfReader(BytesIO(full_bytes))
            total = len(reader.pages)
            p0 = max(1, int(first_page or 1))
            p1 = min(total, int(last_page or p0))
            if p0 <= 1 and p1 >= total:
                return full_bytes
            writer = PdfWriter()
            for idx in range(p0 - 1, p1):
                writer.add_page(reader.pages[idx])
            out = BytesIO()
            writer.write(out)
            return out.getvalue()
        except Exception:
            # Safe fallback: use full file bytes if page-window extraction fails.
            return full_bytes

    @staticmethod
    def _is_large_request(
        *,
        pdf_path: str,
        first_page: Optional[int],
        last_page: Optional[int],
    ) -> bool:
        size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
        if size_mb >= int(getattr(settings, "OCR_ASYNC_BATCH_MIN_FILE_MB", 10)):
            return True
        if first_page is not None and last_page is not None:
            pages = max(1, int(last_page) - int(first_page) + 1)
            if pages >= int(getattr(settings, "OCR_ASYNC_BATCH_MIN_PAGES", 20)):
                return True
        return False

    @staticmethod
    def _gcs_uri(bucket: str, object_name: str) -> str:
        return f"gs://{bucket}/{object_name.lstrip('/')}"

    async def _run_ocr_batch(
        self,
        *,
        pdf_bytes: bytes,
        timeout_s: int,
        fmt_error,
    ) -> List[PageText]:
        try:
            from google.cloud import documentai
            from google.cloud import storage
        except Exception as e:
            raise RuntimeError(
                f"google-cloud-storage/documentai not installed/importable for async batch OCR: {e}"
            ) from e

        bucket = (getattr(settings, "DOCUMENT_AI_GCS_BUCKET", None) or "").strip()
        prefix = (getattr(settings, "DOCUMENT_AI_GCS_PREFIX", "documentai") or "documentai").strip("/")
        if not bucket:
            raise RuntimeError(
                "Large PDF requires async batch OCR, but Cloud Storage is not configured. "
                "Set DOCUMENT_AI_GCS_BUCKET and retry."
            )

        project_id = self._project_id
        max_retries = int(getattr(settings, "OCR_API_MAX_RETRIES", 4) or 4)
        retry_delays = self._parse_retry_delays(
            str(getattr(settings, "OCR_API_RETRY_BACKOFF_SECONDS", "5,15,30,60") or "5,15,30,60")
        )
        transfer_timeout_s = max(180, min(int(timeout_s or 300), 1200))

        async def _retry_io(op_name: str, fn, *args, **kwargs):
            last_error = None
            max_attempts = max(1, max_retries + 1)
            for attempt in range(1, max_attempts + 1):
                try:
                    return await asyncio.wait_for(
                        asyncio.to_thread(fn, *args, **kwargs),
                        timeout=transfer_timeout_s,
                    )
                except Exception as e:
                    last_error = e
                    if attempt >= max_attempts:
                        break
                    delay_idx = min(attempt - 1, len(retry_delays) - 1)
                    delay_s = retry_delays[delay_idx]
                    logger.warning(
                        "google_document_ai_batch_io_retry",
                        extra={
                            "operation": op_name,
                            "attempt": attempt,
                            "max_attempts": max_attempts,
                            "delay_s": delay_s,
                            "error": fmt_error(e),
                        },
                    )
                    await asyncio.sleep(delay_s)
            raise RuntimeError(f"{op_name} failed after retries: {fmt_error(last_error)}") from last_error

        endpoint = f"{self._location}-documentai.googleapis.com"
        processor_client = documentai.DocumentProcessorServiceClient(
            client_options={"api_endpoint": endpoint}
        )
        name = processor_client.processor_path(project_id, self._location, self._processor_id)
        storage_client = storage.Client(project=project_id)
        run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}"
        input_object = f"{prefix}/input/{run_id}.pdf"
        output_prefix = f"{prefix}/output/{run_id}/"
        input_uri = self._gcs_uri(bucket, input_object)
        output_uri = self._gcs_uri(bucket, output_prefix)

        def _sa_email() -> str | None:
            cred_path = getattr(self, "_credentials", None)
            if not cred_path:
                return None
            try:
                with open(cred_path, "r", encoding="utf-8") as f:
                    return (json.load(f) or {}).get("client_email")
            except Exception:
                return None

        blob = storage_client.bucket(bucket).blob(input_object)
        try:
            await _retry_io(
                "GCS upload_from_string",
                blob.upload_from_string,
                pdf_bytes,
                content_type="application/pdf",
                timeout=transfer_timeout_s,
            )
        except Exception as e:
            msg = str(e)
            if "403" in msg or "forbidden" in msg.lower() or "permission" in msg.lower():
                sa = _sa_email()
                raise RuntimeError(
                    f"Permission denied on GCS bucket '{bucket}' while uploading batch OCR input. "
                    f"Ensure the Document AI service account{(' '+sa) if sa else ''} has "
                    "roles/storage.objectAdmin (or Storage Object Admin) on the bucket."
                ) from e
            raise

        batch_req = documentai.BatchProcessRequest(
            name=name,
            input_documents=documentai.BatchDocumentsInputConfig(
                gcs_documents=documentai.GcsDocuments(
                    documents=[
                        documentai.GcsDocument(
                            gcs_uri=input_uri,
                            mime_type="application/pdf",
                        )
                    ]
                )
            ),
            document_output_config=documentai.DocumentOutputConfig(
                gcs_output_config=documentai.DocumentOutputConfig.GcsOutputConfig(
                    gcs_uri=output_uri
                )
            ),
        )
        operation = await asyncio.to_thread(processor_client.batch_process_documents, request=batch_req)

        poll_s = max(2, int(getattr(settings, "OCR_ASYNC_BATCH_POLL_SECONDS", 5)))
        deadline = time.time() + max(timeout_s, int(getattr(settings, "OCR_ASYNC_BATCH_TIMEOUT_SECONDS", 900)))
        while not operation.done():
            if time.time() >= deadline:
                raise RuntimeError(
                    "Batch OCR timed out after 15 minutes - try splitting the PDF into smaller parts "
                    "or increase OCR_ASYNC_BATCH_TIMEOUT_SECONDS."
                )
            await asyncio.sleep(poll_s)
        try:
            await asyncio.to_thread(operation.result, timeout=1)
        except Exception as op_err:
            raise RuntimeError(f"Batch OCR operation failed: {fmt_error(op_err)}") from op_err

        try:
            blobs = list(
                await _retry_io(
                    "GCS list_blobs",
                    storage_client.list_blobs,
                    bucket,
                    prefix=output_prefix,
                    timeout=transfer_timeout_s,
                )
            )
        except Exception as e:
            msg = str(e)
            if "403" in msg or "forbidden" in msg.lower() or "permission" in msg.lower():
                sa = _sa_email()
                raise RuntimeError(
                    f"Permission denied on GCS bucket '{bucket}' while listing batch OCR outputs. "
                    f"Output prefix: '{output_prefix}'. "
                    f"Ensure the Document AI service account{(' '+sa) if sa else ''} has "
                    "roles/storage.objectAdmin on the bucket."
                ) from e
            raise
        json_blobs = [b for b in blobs if b.name.endswith(".json")]
        if not json_blobs:
            raise RuntimeError(
                "Batch OCR completed but no JSON outputs were found in GCS. "
                f"Output URI: {output_uri}. "
                "Check Document AI processor region, GCS permissions, and whether the PDF is valid."
            )

        pages: List[PageText] = []
        for jb in sorted(json_blobs, key=lambda b: b.name):
            try:
                try:
                    raw = await _retry_io(
                        "GCS download_as_bytes",
                        jb.download_as_bytes,
                        timeout=transfer_timeout_s,
                    )
                except Exception as e:
                    msg = str(e)
                    if "403" in msg or "forbidden" in msg.lower() or "permission" in msg.lower():
                        sa = _sa_email()
                        raise RuntimeError(
                            f"Permission denied downloading batch OCR output '{jb.name}' from bucket '{bucket}'. "
                            f"Ensure the Document AI service account{(' '+sa) if sa else ''} has "
                            "roles/storage.objectAdmin on the bucket."
                        ) from e
                    raise
                raw_str = raw.decode("utf-8")
                blob_pages: List[PageText] = []

                # Batch output is serialized as top-level Document JSON (not always nested under "document").
                try:
                    proto_doc = documentai.Document.from_json(raw_str)
                    full_text = proto_doc.text or ""
                    for page in proto_doc.pages or []:
                        page_text = self._extract_text_from_layout(page.layout, full_text)
                        if not page_text.strip() and full_text.strip():
                            page_text = full_text.strip()
                        blob_pages.append(
                            PageText(
                                page_no=len(blob_pages) + 1,
                                text=page_text,
                                char_count=len(page_text.strip()),
                                ocr_engine=self.provider_name,
                            )
                        )
                except Exception:
                    pass

                if not blob_pages:
                    payload = json.loads(raw_str)
                    if isinstance(payload, dict):
                        nested = payload.get("document")
                        if isinstance(nested, dict) and (nested.get("pages") or nested.get("text") is not None):
                            doc = nested
                        else:
                            doc = payload
                    else:
                        doc = {}
                    full_text = doc.get("text") or ""
                    for page in doc.get("pages") or []:
                        layout = page.get("layout") or {}
                        text = ""
                        anchor = layout.get("textAnchor") or {}
                        for seg in anchor.get("textSegments") or []:
                            s = int(seg.get("startIndex", 0) or 0)
                            e = int(seg.get("endIndex", 0) or 0)
                            if e > s:
                                text += full_text[s:e]
                        text = text.strip() or full_text.strip()
                        blob_pages.append(
                            PageText(
                                page_no=len(blob_pages) + 1,
                                text=text,
                                char_count=len(text.strip()),
                                ocr_engine=self.provider_name,
                            )
                        )

                if not blob_pages:
                    raise RuntimeError(
                        f"Batch OCR JSON produced no pages for output {jb.name!r} "
                        "(expected Document AI document JSON)."
                    )

                for bp in blob_pages:
                    pages.append(
                        PageText(
                            page_no=len(pages) + 1,
                            text=bp.text,
                            char_count=bp.char_count,
                            ocr_engine=bp.ocr_engine,
                        )
                    )
            except Exception as parse_err:
                raise RuntimeError(f"Failed to parse batch OCR output JSON: {fmt_error(parse_err)}") from parse_err

        if not pages:
            raise RuntimeError(
                "Batch OCR produced zero pages. "
                f"Output URI: {output_uri}. "
                "Check that the PDF is not empty/corrupted, the processor region matches your configuration, "
                "and the service account has Storage Object Admin on the bucket."
            )
        return pages

    @staticmethod
    def _extract_text_from_layout(layout, full_text: str) -> str:
        text_segments = []
        text_anchor = getattr(layout, "text_anchor", None)
        if not text_anchor:
            return ""
        for seg in getattr(text_anchor, "text_segments", []) or []:
            start = int(getattr(seg, "start_index", 0) or 0)
            end = int(getattr(seg, "end_index", 0) or 0)
            if end > start:
                text_segments.append(full_text[start:end])
        return "".join(text_segments).strip()
    
    async def run_ocr(
        self,
        pdf_path: str,
        language: str = "eng",
        **kwargs
    ) -> List[PageText]:
        """Run OCR via Google Document AI processor."""
        ok, reason = self.validate_strict_config()
        if not ok:
            raise RuntimeError(
                "Google Document AI OCR not configured. "
                f"{reason}"
            )
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        try:
            from google.cloud import documentai
        except Exception as e:
            raise RuntimeError(
                f"google-cloud-documentai not installed/importable: {e}"
            ) from e

        # Resolve project id (env override, else from credential JSON)
        project_id = self._project_id
        if not project_id:
            try:
                with open(self._credentials, "r", encoding="utf-8") as f:
                    project_id = json.load(f).get("project_id")
            except Exception:
                project_id = None
        if not project_id:
            raise RuntimeError("DOCUMENT_AI_PROJECT_ID is required (or project_id in service account JSON)")

        first_page = kwargs.get("first_page")
        last_page = kwargs.get("last_page")
        timeout_s = max(300, int(kwargs.get("timeout_seconds") or os.getenv("OCR_API_TIMEOUT_SECONDS", "300")))
        max_retries = int(kwargs.get("max_retries") or os.getenv("OCR_API_MAX_RETRIES", "2"))
        retry_delays = self._parse_retry_delays(
            str(getattr(settings, "OCR_API_RETRY_BACKOFF_SECONDS", "") or os.getenv("OCR_API_RETRY_BACKOFF_SECONDS", "5,15,30,60"))
        )

        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = self._credentials
        endpoint = f"{self._location}-documentai.googleapis.com"
        client = documentai.DocumentProcessorServiceClient(
            client_options={"api_endpoint": endpoint}
        )
        name = client.processor_path(project_id, self._location, self._processor_id)
        def _fmt_error(err: Exception) -> str:
            """Build a readable error string for gRPC/API exceptions."""
            parts = []
            base = str(err).strip()
            if base:
                parts.append(base)
            details_fn = getattr(err, "details", None)
            if callable(details_fn):
                try:
                    details = str(details_fn() or "").strip()
                    if details and details not in parts:
                        parts.append(f"details={details}")
                except Exception:
                    pass
            code_fn = getattr(err, "code", None)
            if callable(code_fn):
                try:
                    code = code_fn()
                    if code is not None:
                        parts.append(f"code={code}")
                except Exception:
                    pass
            if not parts:
                parts.append(repr(err))
            return " | ".join(parts)

        # Fail early with actionable config/auth errors before heavy OCR calls.
        # Network path to Google can be transiently unstable; retry validation as well.
        cfg_last_error = None
        cfg_attempts = max(1, max_retries + 1)
        for attempt in range(1, cfg_attempts + 1):
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(client.get_processor, name=name),
                    timeout=30,
                )
                cfg_last_error = None
                break
            except Exception as cfg_err:
                cfg_last_error = cfg_err
                if attempt >= cfg_attempts:
                    break
                delay_idx = min(attempt - 1, len(retry_delays) - 1)
                delay_s = retry_delays[delay_idx]
                logger.warning(
                    "google_document_ai_processor_validation_retry",
                    extra={
                        "attempt": attempt,
                        "max_attempts": cfg_attempts,
                        "delay_s": delay_s,
                        "processor": name,
                        "error": _fmt_error(cfg_err),
                    },
                )
                await asyncio.sleep(delay_s)

        if cfg_last_error is not None:
            raise RuntimeError(
                "Google Document AI processor validation failed after retries. "
                "Verify GOOGLE_APPLICATION_CREDENTIALS, DOCUMENT_AI_PROJECT_ID, DOCUMENT_AI_LOCATION, "
                f"DOCUMENT_AI_PROCESSOR_ID and IAM access to processor '{name}'. "
                f"Root error: {_fmt_error(cfg_last_error)}"
            ) from cfg_last_error

        raw_bytes = self._build_pdf_window_bytes(
            pdf_path=pdf_path,
            first_page=int(first_page) if first_page is not None else None,
            last_page=int(last_page) if last_page is not None else None,
        )
        use_async_batch = self._is_large_request(
            pdf_path=pdf_path,
            first_page=int(first_page) if first_page is not None else None,
            last_page=int(last_page) if last_page is not None else None,
        )
        if use_async_batch:
            return await self._run_ocr_batch(
                pdf_bytes=raw_bytes,
                timeout_s=timeout_s,
                fmt_error=_fmt_error,
            )
        raw_doc = documentai.RawDocument(content=raw_bytes, mime_type="application/pdf")

        process_options = None
        if first_page is not None or last_page is not None:
            p0 = int(first_page or 1)
            p1 = int(last_page or p0)
            process_options = documentai.ProcessOptions(
                individual_page_selector=documentai.ProcessOptions.IndividualPageSelector(
                    pages=list(range(p0, p1 + 1))
                )
            )

        request = documentai.ProcessRequest(
            name=name,
            raw_document=raw_doc,
            process_options=process_options,
        )

        last_error = None
        max_attempts = max(1, max_retries + 1)
        for attempt in range(1, max_attempts + 1):
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(client.process_document, request=request, timeout=timeout_s),
                    timeout=timeout_s + 60,
                )
                doc = result.document
                full_text = getattr(doc, "text", "") or ""
                pages = []
                for i, page in enumerate(getattr(doc, "pages", []) or [], start=1):
                    page_text = self._extract_text_from_layout(getattr(page, "layout", None), full_text)
                    if not page_text and full_text:
                        # Safe fallback when layout anchors are empty
                        page_text = full_text.strip()
                    pages.append(
                        PageText(
                            page_no=i,
                            text=page_text,
                            char_count=len(page_text.strip()),
                            ocr_engine=self.provider_name,
                        )
                    )
                if not pages:
                    raise RuntimeError("Document AI returned no pages")
                return pages
            except Exception as e:
                last_error = _fmt_error(e)
                is_timeout = "timeout" in last_error.lower() or "deadline" in last_error.lower()
                logger.warning(
                    "google_document_ai_attempt_failed",
                    extra={
                        "attempt": attempt,
                        "max_attempts": max_attempts,
                        "error": last_error,
                        "is_timeout_like": is_timeout,
                        "pdf_path": pdf_path,
                        "first_page": first_page,
                        "last_page": last_page,
                    },
                )
                if attempt >= max_attempts:
                    break
                delay_idx = min(attempt - 1, len(retry_delays) - 1)
                await asyncio.sleep(retry_delays[delay_idx])

        raise RuntimeError(f"Google Document AI OCR failed after retries: {last_error}")
