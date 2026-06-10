"""
Resolve the database URL used for Alembic DDL and long-running backfills.

Set DATABASE_MIGRATION_URL when your app uses a pooler that blocks DDL (e.g. some
PgBouncer transaction-mode setups). When unset, migrations use DATABASE_URL.
"""
from __future__ import annotations

from typing import Optional


def get_migration_database_url(
    database_url: str,
    migration_url: Optional[str] = None,
) -> str:
    """Return the URL for Alembic migrations and backfill scripts."""
    return migration_url or database_url
