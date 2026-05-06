#!/usr/bin/env python3
"""
Run full content-ingestion pipeline for a PDF on disk (same DB + DOCUMENTS_DIR as the API).

Usage (from 1ne_backend):
  python tools/ingest_local_pdf.py "c:/path/to/file.pdf" [max_hours] [toc.json]

  toc.json  Optional path to a JSON file containing the chapter map array
            (list of {id, title, level, parent_id, start_page_pdf, end_page_pdf, keywords}).
            When provided, overrides any TOC auto-detected from the PDF outline.

Loads `.env` then forces `EMBEDDING_PROVIDER=fake` for **this process only** so large PDFs
complete without OpenAI quota (override: set env `INGEST_LOCAL_RESPECT_EMBEDDING=1` before running).
"""
from __future__ import annotations

import asyncio
import io
import os
import sys
import time
from pathlib import Path
from typing import Optional
from uuid import UUID

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

if os.environ.get("INGEST_LOCAL_RESPECT_EMBEDDING", "").lower() not in ("1", "true", "yes"):
    os.environ["EMBEDDING_PROVIDER"] = "fake"
    os.environ.setdefault("VECTOR_STORE", "pgvector")

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.domains.auth.models import Tenant, TenantType
from app.domains.content_ingestion.enums import DocumentStatus
from app.domains.content_ingestion.models import ContentPack, Document, DocumentProcessingRun
from app.domains.content_ingestion.services.document_service import DocumentService
from app.domains.content_ingestion.services.ingestion_service import IngestionService


def _get_or_create_tenant(db: Session) -> Tenant:
    tenant = db.query(Tenant).first()
    if not tenant:
        tenant_id = UUID("00000000-0000-0000-0000-000000000001")
        tenant = Tenant(
            id=tenant_id,
            name="LOCAL_INGEST_TENANT",
            slug="local-ingest-tenant",
            type=TenantType.PLATFORM,
            hierarchy_path=f"/{tenant_id}/",
            is_active=True,
        )
        db.add(tenant)
        db.commit()
    return tenant


def _get_or_create_pack(db: Session, tenant_id: UUID) -> ContentPack:
    pack = db.query(ContentPack).filter(ContentPack.tenant_id == tenant_id).first()
    if not pack:
        pack_id = UUID("00000000-0000-0000-0000-000000000002")
        pack = ContentPack(id=pack_id, name="LOCAL_INGEST_PACK", tenant_id=tenant_id, is_active=True)
        db.add(pack)
        db.commit()
    return pack


def _load_toc_json(toc_path: Optional[Path]) -> Optional[list]:
    """Load and return chapter map from a JSON file, or None if not provided."""
    if not toc_path:
        return None
    if not toc_path.exists():
        raise FileNotFoundError(f"TOC file not found: {toc_path}")
    import json
    data = json.loads(toc_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"TOC JSON must be a list of chapter objects, got {type(data).__name__}")
    print(f"[toc] loaded {len(data)} chapters from {toc_path.name}", flush=True)
    return data


def _create_document(
    db: Session,
    pack_id: UUID,
    tenant_id: UUID,
    pdf_path: Path,
    chapter_map: Optional[list] = None,
) -> Document:
    import hashlib
    import uuid
    from datetime import datetime

    from app.core.config import settings

    if not pdf_path.exists():
        raise FileNotFoundError(pdf_path)

    file_content = pdf_path.read_bytes()
    file_hash = hashlib.sha256(file_content).hexdigest()
    file_size = len(file_content)

    documents_dir = Path(settings.DOCUMENTS_DIR)
    documents_dir.mkdir(parents=True, exist_ok=True)
    unique_name = f"{uuid.uuid4()}_{int(datetime.now().timestamp())}{pdf_path.suffix}"
    stored = documents_dir / unique_name
    stored.write_bytes(file_content)

    svc = DocumentService(db)
    doc = svc.create_document(
        pack_id=pack_id,
        filename=pdf_path.name,
        file_path=str(stored),
        file_size=file_size,
        mime_type="application/pdf",
        source_type="pdf",
        tenant_id=tenant_id,
        uploaded_by=None,
        title=pdf_path.stem,
        author=None,
        chapter_map=chapter_map,
        document_hash=file_hash,
    )
    return doc


async def _poll_loop(document_id: UUID, stop: asyncio.Event, interval: float = 12.0) -> None:
    """Separate DB session — safe alongside ingestion."""
    last = ""
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
            return
        except asyncio.TimeoutError:
            pass
        s = SessionLocal()
        try:
            doc = s.query(Document).filter(Document.id == document_id).first()
            run = (
                s.query(DocumentProcessingRun)
                .filter(DocumentProcessingRun.document_id == document_id)
                .order_by(DocumentProcessingRun.started_at.desc())
                .first()
            )
            if not doc:
                continue
            line = (
                f"[poll] status={doc.status} step={getattr(run, 'current_step', None)} "
                f"progress%={getattr(run, 'progress_percentage', None)} "
                f"pages={getattr(run, 'pages_processed', None)}/{doc.total_pages or '?'}"
            )
            if doc.error_message and doc.status == DocumentStatus.FAILED.value:
                line += f" err={doc.error_message[:120]}"
            if line != last:
                print(line, flush=True)
                last = line
        finally:
            s.close()


async def _run_ingest_with_deadline(db: Session, document_id: UUID, deadline: float):
    ing = IngestionService(db)
    return await asyncio.wait_for(ing.ingest_document(document_id), timeout=max(1.0, deadline - time.time()))


async def _main_async(pdf_path: Path, max_wait_hours: float, toc_path: Optional[Path] = None) -> int:
    chapter_map = _load_toc_json(toc_path)
    db = SessionLocal()
    try:
        tenant = _get_or_create_tenant(db)
        pack = _get_or_create_pack(db, tenant.id)
        doc = _create_document(db, pack.id, tenant.id, pdf_path, chapter_map=chapter_map)
        print(f"document_id={doc.id} file={pdf_path.name}", flush=True)

        deadline = time.time() + max_wait_hours * 3600
        stop = asyncio.Event()
        poller = asyncio.create_task(_poll_loop(doc.id, stop))

        try:
            final = await _run_ingest_with_deadline(db, doc.id, deadline)
        except asyncio.TimeoutError:
            print(f"TIMEOUT after {max_wait_hours}h — document may still be processing in DB", flush=True)
            return 2
        except Exception as e:
            print(f"INGEST EXCEPTION: {e}", flush=True)
            try:
                db.rollback()
            except Exception:
                pass
            s = SessionLocal()
            try:
                d = s.query(Document).filter(Document.id == doc.id).first()
                if d:
                    print(f"status={d.status} err={d.error_message}", flush=True)
            finally:
                s.close()
            return 1
        finally:
            stop.set()
            poller.cancel()
            try:
                await poller
            except asyncio.CancelledError:
                pass

        db.refresh(final)
        print(f"DONE status={final.status}", flush=True)
        if final.status == DocumentStatus.FAILED.value:
            print(f"error: {final.error_message}", flush=True)
            return 1
        if final.status != DocumentStatus.PUBLISHED.value:
            return 2
        return 0
    finally:
        db.close()


def main() -> int:
    pdf = Path(sys.argv[1] if len(sys.argv) > 1 else "").expanduser()
    if not pdf or not pdf.is_file():
        print("Usage: python tools/ingest_local_pdf.py <path-to.pdf> [max_hours] [toc.json]", flush=True)
        return 2
    hours = float(sys.argv[2]) if len(sys.argv) > 2 else 6.0
    toc_path = Path(sys.argv[3]).expanduser() if len(sys.argv) > 3 else None
    return asyncio.run(_main_async(pdf, hours, toc_path))


if __name__ == "__main__":
    raise SystemExit(main())
