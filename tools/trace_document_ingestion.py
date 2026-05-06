#!/usr/bin/env python3
"""
Poll DB for document + latest processing run while ingestion runs.

Usage:
  cd 1ne_backend
  python tools/trace_document_ingestion.py e91d75b7-a3dd-4971-86bf-8feba4c39d53

  python tools/trace_document_ingestion.py <uuid> --interval 3 --until published

Shows: status, step, progress %, pages_processed, chunks, vectors, errors.
Press Ctrl+C to stop.

If the API enqueues ingestion twice, the second job exits early after the DB claim;
status here should still advance from the first worker.

Requires DATABASE_URL / same env as the FastAPI app (loads .env if python-dotenv).
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Load .env for DATABASE_URL when running standalone
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from uuid import UUID

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.domains.content_ingestion.models import Document, DocumentProcessingRun


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def print_row(ts: str, doc: Document, run: DocumentProcessingRun | None) -> None:
    pct = getattr(run, "progress_percentage", None)
    pp = getattr(run, "pages_processed", None)
    ck = getattr(run, "chunks_created", None)
    vc = getattr(run, "vectors_stored", None)
    step = getattr(run, "current_step", None) if run else None
    msg = ""
    if doc.error_message:
        msg = (doc.error_message[:80] + "…") if len(doc.error_message or "") > 80 else doc.error_message
    print(
        f"{ts}  status={doc.status:18} step={step or '-':18} pct={pct!s:>4} "
        f"pages={pp!s:>5} chunks={ck!s:>5} vecs={vc!s:>5} "
        f"doc_pages={doc.total_pages!s:>5}  {msg}"
    )


def main() -> None:
    p = argparse.ArgumentParser(description="Trace document ingestion via DB polling")
    p.add_argument("document_id", help="Document UUID")
    p.add_argument("--interval", type=float, default=2.0, help="Seconds between polls")
    p.add_argument(
        "--until",
        choices=("published", "failed", "terminal"),
        default="terminal",
        help="Stop when status matches (terminal = published or failed)",
    )
    args = p.parse_args()

    doc_id = args.document_id.strip()
    try:
        doc_uuid = UUID(doc_id)
    except ValueError:
        print("ERROR: document_id must be a valid UUID")
        sys.exit(1)
    print(f"Tracing document {doc_uuid} every {args.interval}s (Ctrl+C to stop)")
    print("-" * 120)

    last_sig: tuple | None = None
    last_heartbeat = time.monotonic()
    try:
        while True:
            db: Session = SessionLocal()
            try:
                doc = db.query(Document).filter(Document.id == doc_uuid).first()
                if not doc:
                    print(f"[{utc_now()}] ERROR: document not found")
                    sys.exit(1)
                run = (
                    db.query(DocumentProcessingRun)
                    .filter(DocumentProcessingRun.document_id == doc.id)
                    .order_by(DocumentProcessingRun.started_at.desc())
                    .first()
                )
                sig = (
                    doc.status,
                    getattr(run, "progress_percentage", None),
                    getattr(run, "pages_processed", None),
                    getattr(run, "chunks_created", None),
                    doc.total_pages,
                )
                if sig != last_sig:
                    print_row(utc_now(), doc, run)
                    last_sig = sig
                    last_heartbeat = time.monotonic()
                elif time.monotonic() - last_heartbeat >= 45.0:
                    print(
                        f"[{utc_now()}] … no DB change yet (status={doc.status}); "
                        "large PDFs can sit on one step while pages are read from disk."
                    )
                    last_heartbeat = time.monotonic()

                if args.until == "published" and doc.status == "published":
                    print("Done: published.")
                    break
                if args.until == "failed" and doc.status == "failed":
                    print("Done: failed.")
                    break
                if (
                    args.until == "terminal"
                    and doc.status in ("published", "failed")
                ):
                    print(f"Done: terminal status={doc.status}")
                    break
            finally:
                db.close()

            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped by user.")


if __name__ == "__main__":
    main()
