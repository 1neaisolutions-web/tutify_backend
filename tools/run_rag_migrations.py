#!/usr/bin/env python3
"""
Apply RAG pipeline Phase 1 migrations outside Alembic when pooler lock contention blocks DDL.

Runs the same SQL as alembic revisions a4b5c6d7e8f9 through d7e8f9a0b1c2, then stamps alembic_version.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sqlalchemy as sa
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.migration_url import get_migration_database_url

HEAD = "d7e8f9a0b1c2"
STEPS = [
    "a4b5c6d7e8f9",
    "b5c6d7e8f9a0",
    "c6d7e8f9a0b1",
    "d7e8f9a0b1c2",
]


def _engine():
    url = get_migration_database_url(settings.DATABASE_URL, settings.DATABASE_MIGRATION_URL)
    return create_engine(url, isolation_level="AUTOCOMMIT")


def _table_exists(conn, name: str) -> bool:
    return bool(
        conn.execute(
            sa.text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = :name"
            ),
            {"name": name},
        ).scalar()
    )


def _column_exists(conn, table: str, column: str) -> bool:
    return bool(
        conn.execute(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = :table AND column_name = :column"
            ),
            {"table": table, "column": column},
        ).scalar()
    )


def _terminate_stuck_ddl_blockers(conn) -> None:
    """Kill idle-in-transaction sessions that block pg_catalog DDL."""
    rows = conn.execute(
        sa.text(
            """
            SELECT pid
            FROM pg_stat_activity
            WHERE datname = current_database()
              AND pid <> pg_backend_pid()
              AND state = 'idle in transaction'
              AND query_start < now() - interval '30 seconds'
            """
        )
    ).fetchall()
    for (pid,) in rows:
        conn.execute(sa.text("SELECT pg_terminate_backend(:pid)"), {"pid": pid})
        print(f"  terminated stuck backend pid={pid}")


def step_a4(conn) -> None:
    print("==> a4b5c6d7e8f9 document_topics + chunks.topic_fk")
    _terminate_stuck_ddl_blockers(conn)
    if not _table_exists(conn, "document_topics"):
        conn.execute(sa.text("SET lock_timeout = '300s'"))
        conn.execute(sa.text("SET statement_timeout = '600s'"))
        conn.execute(
            sa.text(
                """
                CREATE TABLE document_topics (
                    id UUID NOT NULL,
                    document_id UUID NOT NULL,
                    topic_key VARCHAR(100) NOT NULL,
                    parent_key VARCHAR(100),
                    level SMALLINT DEFAULT 1 NOT NULL,
                    display_title VARCHAR(500) NOT NULL,
                    start_page_pdf INTEGER,
                    end_page_pdf INTEGER,
                    sort_order INTEGER DEFAULT 0 NOT NULL,
                    chunk_count INTEGER DEFAULT 0 NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
                    updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
                    PRIMARY KEY (id),
                    CONSTRAINT uq_document_topic UNIQUE (document_id, topic_key),
                    CONSTRAINT fk_document_topics_document_id
                        FOREIGN KEY (document_id) REFERENCES documents (id) ON DELETE CASCADE
                )
                """
            )
        )
    for sql in (
        "CREATE INDEX IF NOT EXISTS idx_document_topics_document ON document_topics (document_id)",
        "CREATE INDEX IF NOT EXISTS idx_document_topics_parent ON document_topics (document_id, parent_key)",
        "CREATE INDEX IF NOT EXISTS ix_document_topics_id ON document_topics (id)",
    ):
        conn.execute(sa.text(sql))

    if not _column_exists(conn, "chunks", "topic_fk"):
        conn.execute(sa.text("ALTER TABLE chunks ADD COLUMN topic_fk UUID"))
        conn.execute(
            sa.text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint
                        WHERE conname = 'fk_chunks_topic_fk_document_topics'
                    ) THEN
                        ALTER TABLE chunks
                        ADD CONSTRAINT fk_chunks_topic_fk_document_topics
                        FOREIGN KEY (topic_fk) REFERENCES document_topics (id)
                        ON DELETE SET NULL;
                    END IF;
                END $$;
                """
            )
        )
        conn.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_chunks_topic_fk ON chunks (topic_fk)"))


def step_b5(conn) -> None:
    import app.db.base  # noqa: F401 — register all models for ORM FK resolution

    from app.domains.content_ingestion.document_topics_service import populate_document_topics
    from app.domains.content_ingestion.models import Document
    from app.db.session import SessionLocal

    print("==> b5c6d7e8f9a0 backfill document_topics")
    conn.execute(sa.text("SET statement_timeout = '0'"))

    doc_ids = [
        row[0]
        for row in conn.execute(
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

    session = SessionLocal()
    try:
        total = len(doc_ids)
        for index, doc_id in enumerate(doc_ids, start=1):
            doc = session.get(Document, doc_id)
            if doc is None:
                continue
            populate_document_topics(session, doc, replace_existing=True)
            session.commit()
            print(f"  [{index}/{total}] {doc.filename}")
    finally:
        session.close()


def step_c6(conn) -> None:
    print("==> c6d7e8f9a0b1 teacher_quizzes scope columns")
    if not _column_exists(conn, "teacher_quizzes", "scope_topic_ids"):
        conn.execute(sa.text("ALTER TABLE teacher_quizzes ADD COLUMN scope_topic_ids JSONB"))
    if not _column_exists(conn, "teacher_quizzes", "scope_book_ids"):
        conn.execute(sa.text("ALTER TABLE teacher_quizzes ADD COLUMN scope_book_ids JSONB"))


def step_d7(conn) -> None:
    print("==> d7e8f9a0b1c2 document_topics_health view")
    conn.execute(
        sa.text(
            """
            CREATE OR REPLACE VIEW document_topics_health AS
            SELECT
                d.id AS document_id,
                d.tenant_id AS tenant_id,
                d.filename,
                d.status,
                COUNT(dt.id) AS total_topics,
                SUM(CASE WHEN dt.chunk_count = 0 THEN 1 ELSE 0 END) AS empty_topics,
                SUM(CASE WHEN dt.topic_key LIKE 'scope:pages%%' THEN 1 ELSE 0 END) AS fallback_topics,
                SUM(dt.chunk_count) AS total_chunks,
                ROUND(
                    100.0 * SUM(CASE WHEN dt.topic_key NOT LIKE 'scope:pages%%' THEN dt.chunk_count ELSE 0 END)
                    / NULLIF(SUM(dt.chunk_count), 0), 1
                ) AS chapter_coverage_pct
            FROM documents d
            LEFT JOIN document_topics dt ON dt.document_id = d.id
            GROUP BY d.id, d.tenant_id, d.filename, d.status
            """
        )
    )


def stamp(conn, revision: str) -> None:
    conn.execute(sa.text("UPDATE alembic_version SET version_num = :rev"), {"rev": revision})
    print(f"stamped alembic_version -> {revision}")


def main() -> None:
    engine = _engine()
    with engine.connect() as conn:
        current = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar()
        print(f"current alembic_version: {current}")

        if current not in ("d1e2f3a4b5c6", *STEPS):
            print(f"Unexpected version {current!r}; aborting.")
            sys.exit(1)

        if current == "d1e2f3a4b5c6":
            step_a4(conn)
            stamp(conn, "a4b5c6d7e8f9")
            current = "a4b5c6d7e8f9"

        if current == "a4b5c6d7e8f9":
            step_b5(conn)
            stamp(conn, "b5c6d7e8f9a0")
            current = "b5c6d7e8f9a0"

        if current == "b5c6d7e8f9a0":
            step_c6(conn)
            stamp(conn, "c6d7e8f9a0b1")
            current = "c6d7e8f9a0b1"

        if current == "c6d7e8f9a0b1":
            step_d7(conn)
            stamp(conn, HEAD)

        if current == HEAD:
            print("Already at head.")
            return

    print("RAG Phase 1 migrations complete.")


if __name__ == "__main__":
    main()
