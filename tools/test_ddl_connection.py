#!/usr/bin/env python3
"""Test whether DDL can run on the configured database URL."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sqlalchemy as sa
from sqlalchemy import create_engine

from app.core.config import settings


def main() -> None:
    engine = create_engine(settings.DATABASE_URL, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        conn.execute(sa.text("SET lock_timeout = '60s'"))
        conn.execute(sa.text("SET statement_timeout = '120s'"))
        conn.execute(
            sa.text(
                """
                CREATE TABLE IF NOT EXISTS _migration_ddl_probe (
                    id INTEGER PRIMARY KEY
                )
                """
            )
        )
        conn.execute(sa.text("DROP TABLE IF EXISTS _migration_ddl_probe"))
        print("DDL probe succeeded on DATABASE_URL")


if __name__ == "__main__":
    main()
