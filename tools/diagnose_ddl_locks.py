#!/usr/bin/env python3
"""Diagnose pg_catalog locks blocking document_topics DDL."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sqlalchemy as sa
from sqlalchemy import create_engine

from app.core.config import settings


def main() -> None:
    engine = create_engine(settings.DATABASE_URL, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        table_exists = conn.execute(
            sa.text(
                "SELECT EXISTS ("
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name='document_topics')"
            )
        ).scalar()
        print("document_topics table exists:", table_exists)

        types = conn.execute(
            sa.text(
                "SELECT typname, typtype FROM pg_type t "
                "JOIN pg_namespace n ON n.oid = t.typnamespace "
                "WHERE n.nspname = 'public' AND typname LIKE '%document_topic%'"
            )
        ).fetchall()
        print("pg_type matches:", types)

        locks = conn.execute(
            sa.text(
                """
                SELECT pid, state, wait_event_type, wait_event, left(query, 120) AS query
                FROM pg_stat_activity
                WHERE datname = current_database()
                  AND pid <> pg_backend_pid()
                  AND state <> 'idle'
                ORDER BY query_start NULLS LAST
                LIMIT 20
                """
            )
        ).fetchall()
        print("active queries:", len(locks))
        for row in locks:
            print(" ", dict(row._mapping))


if __name__ == "__main__":
    main()
