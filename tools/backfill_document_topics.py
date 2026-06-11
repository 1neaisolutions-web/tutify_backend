#!/usr/bin/env python3
"""Backfill document_topics and topic_fk; optionally rechunk from page_texts."""
from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal
from app.domains.content_ingestion.document_topics_service import populate_document_topics
from app.domains.content_ingestion.enums import DocumentStatus
from app.domains.content_ingestion.models import Document, PageText
from app.domains.content_ingestion.services.rechunk_service import RechunkService


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Backfill document topics or rechunk from pages")
    p.add_argument("--rechunk", action="store_true", help="Rechunk from page_texts + auto sections")
    p.add_argument("--document-id", type=str, default=None, help="Single document UUID")
    return p.parse_args()


async def _rechunk_one(db, doc: Document) -> None:
    page_count = db.query(PageText).filter(PageText.document_id == doc.id).count()
    if page_count == 0:
        print(f"  SKIP {doc.filename}: no page_texts")
        return
    report = await RechunkService(db).rechunk_document(doc.id)
    if report.errors:
        print(f"  FAIL {doc.filename}: {report.errors}")
        return
    print(
        f"  OK {doc.filename}: chunks={report.chunks_created} "
        f"sections+={report.sections_added} coverage={report.coverage:.1%} "
        f"mislabeled={report.mislabeled_count}"
    )


def main() -> int:
    args = _parse_args()
    db = SessionLocal()
    try:
        q = db.query(Document).filter(Document.status == DocumentStatus.PUBLISHED.value)
        if args.document_id:
            q = q.filter(Document.id == uuid.UUID(args.document_id))
        docs = q.order_by(Document.created_at.asc()).all()
        mode = "rechunk" if args.rechunk else "reprocess-topics"
        print(f"{mode}: {len(docs)} published document(s)...")

        if args.rechunk:
            for doc in docs:
                asyncio.run(_rechunk_one(db, doc))
            return 0

        low_coverage = []
        for doc in docs:
            report = populate_document_topics(db, doc, replace_existing=True)
            db.commit()
            print(
                f"  {doc.filename}: coverage={report.coverage:.1%} "
                f"topics={len(doc.document_topics or [])} "
                f"empty={len(report.chapters_with_zero_chunks)}"
            )
            if report.coverage < 0.95:
                low_coverage.append((doc.id, doc.filename, report.coverage))
        if low_coverage:
            print("\nLow coverage documents:")
            for doc_id, name, cov in low_coverage:
                print(f"  - {name} ({doc_id}): {cov:.1%}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
