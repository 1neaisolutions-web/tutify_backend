"""Backfill document_topics from chapter_map and link chunks.topic_fk.

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
Create Date: 2026-06-05

Processes one document per commit to avoid long transactions and statement timeouts.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

revision: str = "b5c6d7e8f9a0"
down_revision: Union[str, None] = "a4b5c6d7e8f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    import app.db.base  # noqa: F401 — register all models for ORM FK resolution

    from app.domains.content_ingestion.document_topics_service import populate_document_topics
    from app.domains.content_ingestion.models import Document
    from app.db.session import SessionLocal

    bind = op.get_bind()
    bind.execute(sa.text("SET statement_timeout = '0'"))

    doc_ids = [
        row[0]
        for row in bind.execute(
            sa.text(
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
    if total == 0:
        return

    session = SessionLocal()
    try:
        for index, doc_id in enumerate(doc_ids, start=1):
            doc = session.get(Document, doc_id)
            if doc is None:
                continue
            populate_document_topics(session, doc, replace_existing=True)
            session.commit()
            print(f"[backfill] {index}/{total} document_id={doc_id} filename={doc.filename!r}")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def downgrade() -> None:
    op.execute(sa.text("UPDATE chunks SET topic_fk = NULL"))
    op.execute(sa.text("DELETE FROM document_topics"))
