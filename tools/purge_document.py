"""
Purge a document and all related ingestion data from the database, plus its stored file.

Usage:
  python tools/purge_document.py <document_uuid>
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import UUID

# Ensure repo root is on sys.path when run from anywhere
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal
from app.domains.content_ingestion.models import (
    Document,
    PageText,
    Chunk,
    DocumentProcessingRun,
    QAValidation,
    MathBlock,
)


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python tools/purge_document.py <document_uuid>")
        return 2

    try:
        doc_id = UUID(sys.argv[1])
    except Exception:
        print(f"[FAIL] Invalid UUID: {sys.argv[1]!r}")
        return 2

    db = SessionLocal()
    file_path: str | None = None
    try:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            print(f"[OK] Document not found: {doc_id}")
            return 0

        file_path = doc.file_path

        # Counts before
        counts_before = {
            "documents": db.query(Document).filter(Document.id == doc_id).count(),
            "page_texts": db.query(PageText).filter(PageText.document_id == doc_id).count(),
            "chunks": db.query(Chunk).filter(Chunk.document_id == doc_id).count(),
            "runs": db.query(DocumentProcessingRun).filter(DocumentProcessingRun.document_id == doc_id).count(),
            "qa_validations": db.query(QAValidation).filter(QAValidation.document_id == doc_id).count(),
            "math_blocks": db.query(MathBlock).filter(MathBlock.document_id == doc_id).count(),
        }
        print("[INFO] Counts before:", counts_before)

        # Delete children first (even though FK CASCADE exists, this is explicit and portable)
        db.query(QAValidation).filter(QAValidation.document_id == doc_id).delete(synchronize_session=False)
        db.query(MathBlock).filter(MathBlock.document_id == doc_id).delete(synchronize_session=False)
        db.query(Chunk).filter(Chunk.document_id == doc_id).delete(synchronize_session=False)
        db.query(PageText).filter(PageText.document_id == doc_id).delete(synchronize_session=False)
        db.query(DocumentProcessingRun).filter(DocumentProcessingRun.document_id == doc_id).delete(synchronize_session=False)
        db.query(Document).filter(Document.id == doc_id).delete(synchronize_session=False)
        db.commit()

        # Counts after
        counts_after = {
            "documents": db.query(Document).filter(Document.id == doc_id).count(),
            "page_texts": db.query(PageText).filter(PageText.document_id == doc_id).count(),
            "chunks": db.query(Chunk).filter(Chunk.document_id == doc_id).count(),
            "runs": db.query(DocumentProcessingRun).filter(DocumentProcessingRun.document_id == doc_id).count(),
            "qa_validations": db.query(QAValidation).filter(QAValidation.document_id == doc_id).count(),
            "math_blocks": db.query(MathBlock).filter(MathBlock.document_id == doc_id).count(),
        }
        print("[INFO] Counts after:", counts_after)
        print("[OK] DB purge complete.")

    finally:
        db.close()

    # Remove stored file (best-effort)
    if file_path:
        abs_path = Path(file_path)
        if not abs_path.is_absolute():
            # workspace root assumed as cwd when running this script from repo
            abs_path = Path.cwd() / file_path
        if abs_path.exists():
            try:
                abs_path.unlink()
                print(f"[OK] Deleted file: {abs_path}")
            except Exception as e:
                print(f"[WARN] Could not delete file {abs_path}: {e}")
        else:
            print(f"[OK] File already missing: {abs_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

