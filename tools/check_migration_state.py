#!/usr/bin/env python3
"""Quick check of migration / document_topics state."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

from app.db.session import SessionLocal


def main() -> None:
    db = SessionLocal()
    try:
        versions = db.execute(text("SELECT version_num FROM alembic_version")).fetchall()
        print("alembic_version:", [v[0] for v in versions])

        tables = db.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name IN "
                "('document_topics', 'chunks', 'teacher_quizzes')"
            )
        ).fetchall()
        print("tables:", [t[0] for t in tables])

        col = db.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'chunks' AND column_name = 'topic_fk'"
            )
        ).fetchone()
        print("chunks.topic_fk exists:", col is not None)

        quiz_cols = db.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'teacher_quizzes' "
                "AND column_name IN ('scope_topic_ids', 'scope_book_ids')"
            )
        ).fetchall()
        print("teacher_quizzes scope cols:", [c[0] for c in quiz_cols])

        try:
            dt_count = db.execute(text("SELECT COUNT(*) FROM document_topics")).scalar()
            print("document_topics count:", dt_count)
        except Exception as exc:
            print("document_topics query failed:", exc)
            db.rollback()

        doc_count = db.execute(text("SELECT COUNT(*) FROM documents")).scalar()
        chunk_count = db.execute(text("SELECT COUNT(*) FROM chunks")).scalar()
        print(f"documents={doc_count}, chunks={chunk_count}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
