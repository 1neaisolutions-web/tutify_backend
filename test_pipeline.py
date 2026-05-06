"""
Self-healing PDF ingestion pipeline test script.

Usage:
    python test_pipeline.py --pdf test_pipeline_pdf.pdf
    python test_pipeline.py --pdf "My Book.pdf" --skip-chapter-map
    python test_pipeline.py --pdf test_pipeline_pdf.pdf --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import ReadTimeout as RequestsReadTimeout
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional dependency fallback
    load_dotenv = None


DEFAULT_TOC_METADATA: Dict[str, Any] = {
    "title": "AI Concepts Test Document",
    "author": "anonymous",
    "created_at": "2026-04-24",
    "source": "test_pipeline_pdf.pdf",
    "toc": [
        {"page": 1, "title": "Introduction to Artificial Intelligence", "type": "clear_text"},
        {"page": 2, "title": "Key Concepts in AI", "type": "clear_text"},
        {"page": 3, "title": "Applications of AI", "type": "clear_text"},
        {"page": 4, "title": "Scanned Style Content", "type": "ocr_target"},
        {"page": 5, "title": "Low Quality Content", "type": "ocr_target"},
        {"page": 6, "title": "Table Content", "type": "structured_table"},
        {"page": 7, "title": "Mixed Content", "type": "mixed"},
        {"page": 8, "title": "AI Workflow", "type": "mixed"},
        {"page": 9, "title": "Advantages of AI", "type": "mixed"},
        {"page": 10, "title": "Noisy Page", "type": "noisy"},
    ],
}

TERMINAL_STATUSES = {"published", "failed"}
CODE_RETRYABLE_STEPS = {"chunking", "indexing", "upload"}
MAX_CODE_RETRIES = 3


def now_str() -> str:
    return datetime.now().strftime("%H:%M:%S")


def print_status(msg: str) -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        try:
            enc = getattr(sys.stdout, "encoding", None) or "utf-8"
            safe = msg.encode(enc, errors="replace").decode(enc, errors="replace")
            print(safe, flush=True)
        except Exception:
            sys.stdout.buffer.write((msg + "\n").encode("utf-8", errors="replace"))
            sys.stdout.buffer.flush()


def normalize_status(status_value: Optional[str]) -> str:
    if not status_value:
        return "UNKNOWN"
    return str(status_value).strip().upper()


def to_chapter_map(toc_metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
    toc_items = toc_metadata.get("toc", [])
    chapter_map: List[Dict[str, Any]] = []
    for idx, item in enumerate(toc_items, start=1):
        page = int(item["page"])
        chapter_map.append(
            {
                "id": f"ch{idx}",
                "title": item["title"],
                "level": 1,
                "parent_id": None,
                "start_page_pdf": page,
                "end_page_pdf": page,
                "keywords": [item.get("type", "mixed")],
            }
        )
    return chapter_map


@dataclass
class PipelineSummary:
    upload: str = "FAIL"
    ocr: str = "FAIL"
    chunking: str = "FAIL"
    embedding: str = "FAIL"
    indexing: str = "FAIL"
    vector_db: str = "FAIL"
    overall: str = "FAIL"
    document_id: Optional[str] = None
    statuses_seen: List[str] = field(default_factory=list)
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    chunk_count: int = 0
    sample_chunk: Optional[Dict[str, Any]] = None


class PipelineTester:
    def __init__(
        self,
        pdf_path: Path,
        dry_run: bool = False,
        cli_email: str = "",
        cli_password: str = "",
        cli_token: str = "",
        cli_pack_id: str = "",
        skip_chapter_map: bool = False,
    ) -> None:
        if load_dotenv:
            load_dotenv()

        self.pdf_path = pdf_path
        self.dry_run = dry_run
        self.skip_chapter_map = skip_chapter_map
        self.base_url = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
        # Priority: CLI args > dedicated API_* envs > common fallback env names.
        self.api_email = (
            cli_email
            or os.getenv("API_EMAIL", "")
            or os.getenv("EMAIL", "")
            or os.getenv("ADMIN_EMAIL", "")
        )
        self.api_password = (
            cli_password
            or os.getenv("API_PASSWORD", "")
            or os.getenv("PASSWORD", "")
            or os.getenv("ADMIN_PASSWORD", "")
        )
        self.api_token = (
            cli_token
            or os.getenv("API_TOKEN", "")
            or os.getenv("ACCESS_TOKEN", "")
        )
        self.pack_id = cli_pack_id or os.getenv("API_PACK_ID", "")
        self.force_ocr = os.getenv("PIPELINE_FORCE_OCR", "true").lower() in {"1", "true", "yes"}
        self.timeout_seconds = int(os.getenv("PIPELINE_TIMEOUT_SECONDS", "300"))
        self.poll_interval_seconds = int(os.getenv("PIPELINE_POLL_INTERVAL_SECONDS", "3"))
        self.request_timeout = int(os.getenv("PIPELINE_REQUEST_TIMEOUT_SECONDS", "30"))
        self.poll_error_tolerance = int(os.getenv("PIPELINE_POLL_ERROR_TOLERANCE", "20"))
        self.http_retry_attempts = int(os.getenv("PIPELINE_HTTP_RETRY_ATTEMPTS", "5"))
        self.http_retry_backoff_seconds = float(
            os.getenv("PIPELINE_HTTP_RETRY_BACKOFF_SECONDS", "1.5")
        )
        self.database_url = os.getenv("DATABASE_URL", "")
        self.report_path = Path(os.getenv("PIPELINE_REPORT_PATH", "pipeline_result.json"))

        self.session = requests.Session()
        self.summary = PipelineSummary()
        self.toc_metadata = DEFAULT_TOC_METADATA

    def _request(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        **kwargs: Any,
    ) -> requests.Response:
        attempts = max(1, self.http_retry_attempts)
        delay = max(0.1, self.http_retry_backoff_seconds)
        last_exc: Optional[Exception] = None
        for attempt in range(1, attempts + 1):
            try:
                return self.session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    timeout=timeout or self.request_timeout,
                    **kwargs,
                )
            except (RequestsConnectionError, RequestsReadTimeout) as exc:
                last_exc = exc
                if attempt >= attempts:
                    break
                print_status(
                    f"[{now_str()}] HTTP retry {attempt}/{attempts} for {method} {url}: {exc}"
                )
                time.sleep(delay)
                delay = min(delay * 1.8, 8.0)
                continue
            except requests.RequestException as exc:
                raise RuntimeError(f"Network error calling {method} {url}: {exc}") from exc
        raise RuntimeError(f"Network error calling {method} {url}: {last_exc}") from last_exc

    def _check_backend_health(self) -> None:
        url = f"{self.base_url}/health"
        response = self._request("GET", url, timeout=10)
        if response.status_code != 200:
            raise RuntimeError(
                f"Backend health check failed ({response.status_code}): {response.text}"
            )

    def _save_report(self) -> None:
        report = {
            "timestamp": datetime.now().isoformat(),
            "base_url": self.base_url,
            "pdf_path": str(self.pdf_path),
            "dry_run": self.dry_run,
            "document_id": self.summary.document_id,
            "statuses_seen": self.summary.statuses_seen,
            "error_code": self.summary.error_code,
            "error_message": self.summary.error_message,
            "chunk_count": self.summary.chunk_count,
            "sample_chunk": self.summary.sample_chunk,
            "checks": {
                "upload": self.summary.upload,
                "ocr": self.summary.ocr,
                "chunking": self.summary.chunking,
                "embedding": self.summary.embedding,
                "indexing": self.summary.indexing,
                "vector_db": self.summary.vector_db,
                "overall": self.summary.overall,
            },
        }
        self.report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    def validate_local_inputs(self) -> None:
        if not self.pdf_path.exists() or not self.pdf_path.is_file():
            raise ValueError(f"PDF not found: {self.pdf_path}")
        if self.pdf_path.suffix.lower() != ".pdf":
            raise ValueError(f"Input must be a PDF file: {self.pdf_path}")
        if self.pdf_path.stat().st_size == 0:
            raise ValueError(f"PDF is empty: {self.pdf_path}")

        if self.skip_chapter_map:
            return
        if not isinstance(self.toc_metadata.get("toc"), list) or not self.toc_metadata["toc"]:
            raise ValueError("TOC metadata is invalid: 'toc' must be a non-empty list")
        for item in self.toc_metadata["toc"]:
            if not isinstance(item, dict):
                raise ValueError("Each TOC entry must be an object")
            if "page" not in item or "title" not in item:
                raise ValueError("Each TOC entry must contain 'page' and 'title'")
            int(item["page"])

    def get_access_token(self) -> str:
        if self.api_token:
            return self.api_token
        if not self.api_email or not self.api_password:
            raise ValueError(
                "Set API_TOKEN or both API_EMAIL and API_PASSWORD in environment."
            )

        url = f"{self.base_url}/api/v1/auth/login"
        payload = {"email": self.api_email, "password": self.api_password}
        response = self._request("POST", url, json=payload)
        if response.status_code != 200:
            raise RuntimeError(
                f"Login failed ({response.status_code}): {response.text}"
            )
        data = response.json()
        token = data.get("access_token")
        if not token:
            raise RuntimeError("Login succeeded but response did not contain access_token.")
        return token

    def resolve_pack_id(self, auth_headers: Dict[str, str]) -> str:
        if self.pack_id:
            return self.pack_id
        url = f"{self.base_url}/api/v1/admin/content-packs?is_active=true&limit=1"
        response = self._request("GET", url, headers=auth_headers)
        if response.status_code != 200:
            raise RuntimeError(
                f"Failed to list content packs ({response.status_code}): {response.text}"
            )
        packs = response.json()
        if not packs:
            raise RuntimeError(
                "No active content pack found. Set API_PACK_ID in .env or create a pack first."
            )
        return packs[0]["id"]

    def upload_document(
        self,
        auth_headers: Dict[str, str],
        pack_id: str,
    ) -> str:
        url = f"{self.base_url}/api/v1/admin/documents"
        title = (self.toc_metadata.get("title") or "").strip() or self.pdf_path.stem
        author = (self.toc_metadata.get("author") or "").strip() or "unknown"
        form_data: Dict[str, Any] = {
            "pack_id": pack_id,
            "title": title,
            "author": author,
            "force_ocr": str(self.force_ocr).lower(),
        }
        if not self.skip_chapter_map:
            form_data["chapter_map"] = json.dumps(to_chapter_map(self.toc_metadata))

        size_mb = self.pdf_path.stat().st_size / (1024 * 1024)
        upload_timeout = self.request_timeout
        if size_mb > 8:
            upload_timeout = max(
                self.request_timeout,
                int(os.getenv("PIPELINE_LARGE_UPLOAD_TIMEOUT_SECONDS", "900")),
            )
        try:
            with self.pdf_path.open("rb") as fp:
                files = {
                    "file": (self.pdf_path.name, fp, "application/pdf"),
                }
                response = self._request(
                    "POST",
                    url,
                    headers=auth_headers,
                    data=form_data,
                    files=files,
                    timeout=upload_timeout,
                )
        except Exception as exc:
            raise RuntimeError(f"Upload request failed: {exc}") from exc

        if response.status_code < 200 or response.status_code >= 300:
            raise RuntimeError(
                f"UPLOAD_ERROR: {response.status_code} {response.text}"
            )
        payload = response.json()
        document_id = payload.get("id")
        if not document_id:
            raise RuntimeError("Upload response missing document id.")
        print_status(f"Document ID: {document_id}")
        self.summary.upload = "PASS"
        self.summary.document_id = document_id
        return document_id

    def fetch_document_status(
        self,
        auth_headers: Dict[str, str],
        document_id: str,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/admin/documents/{document_id}"
        response = self._request("GET", url, headers=auth_headers)
        if response.status_code != 200:
            raise RuntimeError(
                f"Status fetch failed ({response.status_code}): {response.text}"
            )
        return response.json()

    def retry_processing(
        self,
        auth_headers: Dict[str, str],
        document_id: str,
    ) -> None:
        url = f"{self.base_url}/api/v1/admin/documents/{document_id}/retry"
        response = self._request("POST", url, headers=auth_headers)
        if response.status_code < 200 or response.status_code >= 300:
            raise RuntimeError(
                f"Retry endpoint failed ({response.status_code}): {response.text}"
            )

    @staticmethod
    def classify_error(error_code: str, error_message: str) -> Tuple[str, str, str]:
        code = (error_code or "").upper().strip()
        msg = (error_message or "").strip()

        if code == "OCR_ERROR":
            return (
                "ocr",
                "infra",
                "⚠️ OCR service failed. Check if Tesseract/Google Vision is configured and running. This is an infrastructure issue, not a code bug.",
            )
        if code == "EMBEDDING_ERROR":
            return (
                "embedding",
                "infra",
                "⚠️ Embedding API failed. Check your OpenAI/embedding API key, quota, and network access. This is an external service issue, not a code bug.",
            )
        if code == "CHUNKING_ERROR":
            return (
                "chunking",
                "code",
                "🐛 Chunking failed. Likely a code bug — check chunk size config, text encoding issues, or empty page handling.",
            )
        if code == "INDEXING_ERROR":
            return (
                "indexing",
                "code",
                "🐛 Indexing/Vector DB write failed. Check DB connection string, collection name, and vector dimensions match.",
            )
        if code == "UPLOAD_ERROR":
            return (
                "upload",
                "code",
                "🐛 File upload failed. Check multipart form-data format, file path, and API endpoint URL.",
            )
        return ("unknown", "unknown", f"❓ Unknown error: {code or 'FAILED'}. Check server logs for details.")

    def poll_until_terminal(
        self,
        auth_headers: Dict[str, str],
        document_id: str,
    ) -> Dict[str, Any]:
        deadline = time.time() + self.timeout_seconds
        last_status = None
        transient_errors = 0

        while time.time() < deadline:
            try:
                data = self.fetch_document_status(auth_headers, document_id)
                transient_errors = 0
            except Exception as exc:
                transient_errors += 1
                print_status(
                    f"[{now_str()}] Poll warning ({transient_errors}/{self.poll_error_tolerance}): {exc}"
                )
                if transient_errors >= self.poll_error_tolerance:
                    raise RuntimeError(
                        f"Exceeded polling error tolerance ({self.poll_error_tolerance}). Last error: {exc}"
                    ) from exc
                time.sleep(self.poll_interval_seconds)
                continue

            status_raw = str(data.get("status", "unknown")).lower()
            status_display = normalize_status(status_raw)

            if status_display != last_status:
                self.summary.statuses_seen.append(status_display)
                print_status(f"[{now_str()}] Status: {status_display}")
                last_status = status_display

            if status_raw in TERMINAL_STATUSES:
                return data
            time.sleep(self.poll_interval_seconds)

        raise TimeoutError(
            f"Timeout: PUBLISHED not reached within {self.timeout_seconds} seconds."
        )

    def verify_vector_db(self, document_id: str) -> None:
        if not self.database_url:
            raise RuntimeError("DATABASE_URL is not set; cannot verify vector DB.")

        query_count = text(
            """
            SELECT COUNT(*) AS chunk_count
            FROM chunks
            WHERE document_id = CAST(:document_id AS uuid)
              AND embedding_v IS NOT NULL
            """
        )
        query_sample = text(
            """
            SELECT chunk_id, text, topic_id, topic_title, metadata_json, page_start_pdf, page_end_pdf
            FROM chunks
            WHERE document_id = CAST(:document_id AS uuid)
            ORDER BY created_at ASC
            LIMIT 1
            """
        )

        engine = create_engine(self.database_url)
        try:
            with engine.connect() as conn:
                count = int(conn.execute(query_count, {"document_id": document_id}).scalar() or 0)
                self.summary.chunk_count = count
                if count > 0:
                    print_status(f"✅ Chunks stored: {count}")
                    self.summary.vector_db = "PASS"
                else:
                    print_status("❌ 0 chunks found — embedding or indexing may have silently failed")
                    self.summary.vector_db = "FAIL"

                sample_row = conn.execute(query_sample, {"document_id": document_id}).mappings().first()
                if sample_row:
                    sample = dict(sample_row)
                    sample["text"] = (sample.get("text") or "")[:300]
                    self.summary.sample_chunk = sample
                    print_status("Sample chunk:")
                    print_status(f"  - chunk_id: {sample.get('chunk_id')}")
                    print_status(
                        f"  - pages: {sample.get('page_start_pdf')} -> {sample.get('page_end_pdf')}"
                    )
                    print_status(f"  - topic_title: {sample.get('topic_title')}")
                    print_status(f"  - text: {sample.get('text')}")
                else:
                    print_status("❌ No sample chunk found for this document ID.")
                    self.summary.vector_db = "FAIL"
        except SQLAlchemyError as exc:
            raise RuntimeError(f"Vector DB verification failed: {exc}") from exc
        finally:
            engine.dispose()

    def update_step_passes_from_statuses(self) -> None:
        seen = {s.lower() for s in self.summary.statuses_seen}
        if "ocr_running" in seen:
            self.summary.ocr = "PASS"
        if "chunking" in seen or "normalizing" in seen:
            self.summary.chunking = "PASS"
        if "embedding" in seen:
            self.summary.embedding = "PASS"
        if "indexing" in seen:
            self.summary.indexing = "PASS"

    def print_final_summary(self) -> None:
        all_pass = all(
            [
                self.summary.upload == "PASS",
                self.summary.ocr == "PASS",
                self.summary.chunking == "PASS",
                self.summary.embedding == "PASS",
                self.summary.indexing == "PASS",
                self.summary.vector_db == "PASS",
            ]
        )
        self.summary.overall = "PASS" if all_pass else "FAIL"

        print_status("\n============ PIPELINE TEST SUMMARY ============")
        print_status(f"Upload:        {self.summary.upload}")
        print_status(f"OCR:           {self.summary.ocr}")
        print_status(f"Chunking:      {self.summary.chunking}")
        print_status(f"Embedding:     {self.summary.embedding}")
        print_status(f"Indexing:      {self.summary.indexing}")
        if self.summary.vector_db == "PASS":
            print_status(f"Vector DB:     PASS — {self.summary.chunk_count} chunks stored")
        else:
            print_status("Vector DB:     FAIL")
        if all_pass:
            print_status("Overall:       ✅ ALL CHECKS PASSED")
        else:
            print_status("Overall:       ❌ CHECKS FAILED")
        print_status("===============================================\n")

    def run(self) -> int:
        self.validate_local_inputs()
        if self.dry_run:
            print_status("Dry-run validation passed. No API calls were made.")
            self.summary.overall = "PASS"
            self._save_report()
            return 0

        try:
            from pypdf import PdfReader

            n_pages = len(PdfReader(str(self.pdf_path)).pages)
        except Exception:
            n_pages = 0
        if n_pages > 30:
            per_page = int(os.getenv("PIPELINE_TIMEOUT_SECONDS_PER_PAGE", "45"))
            # Cap auto-extension so large PDFs don't make tests look "stuck" for hours.
            # Override via env if you explicitly want longer.
            max_auto = int(os.getenv("PIPELINE_MAX_AUTO_TIMEOUT_SECONDS", str(30 * 60)))
            min_deadline = min(max_auto, 600 + n_pages * per_page)
            if self.timeout_seconds < min_deadline:
                print_status(
                    f"[{now_str()}] Large PDF (~{n_pages} pages): extending poll deadline "
                    f"{self.timeout_seconds}s -> {min_deadline}s (set PIPELINE_TIMEOUT_SECONDS to override)."
                )
                self.timeout_seconds = min_deadline

        self._check_backend_health()
        token = self.get_access_token()
        auth_headers = {"Authorization": f"Bearer {token}"}
        pack_id = self.resolve_pack_id(auth_headers)

        try:
            document_id = self.upload_document(auth_headers, pack_id)
        except Exception as exc:
            print_status(f"Upload failed: {exc}")
            self.summary.error_code = "UPLOAD_ERROR"
            self.summary.error_message = str(exc)
            self._save_report()
            self.print_final_summary()
            return 1

        code_retry_count = 0
        outer_cycles = 0
        max_outer_cycles = 50
        while True:
            outer_cycles += 1
            if outer_cycles > max_outer_cycles:
                print_status(
                    f"🛑 Safety stop: exceeded {max_outer_cycles} processing cycles "
                    "(check backend logs; increase max_outer_cycles if intentional)."
                )
                self.summary.error_code = "LOOP_GUARD"
                self.summary.error_message = "Too many terminal poll cycles"
                break
            try:
                final_data = self.poll_until_terminal(auth_headers, document_id)
            except TimeoutError as exc:
                print_status(str(exc))
                self.summary.error_code = "TIMEOUT"
                self.summary.error_message = str(exc)
                self.update_step_passes_from_statuses()
                self._save_report()
                self.print_final_summary()
                return 1
            except Exception as exc:
                print_status(f"Polling failed: {exc}")
                self.summary.error_code = "POLL_ERROR"
                self.summary.error_message = str(exc)
                self.update_step_passes_from_statuses()
                self._save_report()
                self.print_final_summary()
                return 1

            self.update_step_passes_from_statuses()
            status_raw = str(final_data.get("status", "unknown")).lower()
            if status_raw == "published":
                try:
                    self.verify_vector_db(document_id)
                except Exception as exc:
                    print_status(f"Vector DB check failed: {exc}")
                    self.summary.vector_db = "FAIL"
                # Some pipelines emit NORMALIZING instead of explicit CHUNKING.
                # If document is published and chunks exist in DB, chunking is effectively successful.
                if self.summary.chunk_count > 0:
                    self.summary.chunking = "PASS"
                break

            error_code = str(final_data.get("error_code") or "FAILED")
            error_message = str(final_data.get("error_message") or "")
            self.summary.error_code = error_code
            self.summary.error_message = error_message
            step, category, reason_text = self.classify_error(error_code, error_message)
            print_status(reason_text)

            if category == "infra":
                if step == "ocr":
                    self.summary.ocr = "FAIL"
                elif step == "embedding":
                    self.summary.embedding = "FAIL"
                break

            if step in CODE_RETRYABLE_STEPS:
                code_retry_count += 1
                if code_retry_count >= MAX_CODE_RETRIES:
                    print_status(f"🛑 Repeated failure in {step}. Stopping. Check logs above.")
                    break
                print_status(f"🔄 Retrying {step}... attempt {code_retry_count + 1}/{MAX_CODE_RETRIES}")
                try:
                    if step == "upload":
                        document_id = self.upload_document(auth_headers, pack_id)
                    else:
                        self.retry_processing(auth_headers, document_id)
                    continue
                except Exception as exc:
                    print_status(f"Retry failed immediately: {exc}")
                    if code_retry_count >= MAX_CODE_RETRIES:
                        print_status(f"🛑 Repeated failure in {step}. Stopping. Check logs above.")
                        break
                    continue

            break

        self.print_final_summary()
        self._save_report()
        return 0 if self.summary.overall == "PASS" else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Self-healing PDF pipeline test script")
    parser.add_argument("--pdf", required=True, help="Path to PDF file to upload")
    parser.add_argument("--email", default="", help="Login email (overrides .env)")
    parser.add_argument("--password", default="", help="Login password (overrides .env)")
    parser.add_argument("--token", default="", help="Bearer token (skips login)")
    parser.add_argument("--pack-id", default="", help="Content pack ID (skip auto-detect)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inputs and metadata without making API calls",
    )
    parser.add_argument(
        "--skip-chapter-map",
        action="store_true",
        help="Omit chapter_map (matches UI upload without TOC); backend uses PDF outline when available.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tester = PipelineTester(
        pdf_path=Path(args.pdf),
        dry_run=args.dry_run,
        cli_email=args.email,
        cli_password=args.password,
        cli_token=args.token,
        cli_pack_id=args.pack_id,
        skip_chapter_map=args.skip_chapter_map,
    )
    return tester.run()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print_status("\nInterrupted by user.")
        raise SystemExit(130)
