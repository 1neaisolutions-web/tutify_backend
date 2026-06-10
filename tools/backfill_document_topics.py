#!/usr/bin/env python3
"""Backfill document_topics and chunks.topic_fk for all documents."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal
from app.domains.content_ingestion.document_topics_service import populate_document_topics
from app.domains.content_ingestion.models import Document


def main() -> None:
    db = SessionLocal()
    try:
        doc_ids = [
            row[0]
            for row in db.execute(
                __import__("sqlalchemy").text(
                    """
                    SELECT d.id
                    FROM documents d
                    WHERE d.chapter_map IS NOT NULL
                       OR EXISTS (SELECT 1 FROM chunks c WHERE c.document_id = d.id)
                    ORDER BY d.created_at
                    """
                )
            ).fetchall()
        ]
        total = len(doc_ids)
        for index, doc_id in enumerate(doc_ids, start=1):
            doc = db.get(Document, doc_id)
            if doc is None:
                continue
            report = populate_document_topics(db, doc, replace_existing=True)
            db.commit()
            print(
                f"[{index}/{total}] {doc.filename}: topics={report.total_chunks} "
                f"coverage={report.coverage:.1%} assigned={report.chunks_assigned}/{report.total_chunks}"
            )
        print("Backfill complete.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
