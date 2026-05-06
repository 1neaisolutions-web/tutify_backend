"""Normalize access_codes.code to uppercase alphanumeric (no hyphens).

Revision ID: e5f6a7b8c9d0
Revises: c1d2e3f4b5a6
Create Date: 2026-05-03

Redemption sends codes without hyphens; admin/stored values used STAFF-XXXX-XXXX.
lookup failed on exact string match. This migration aligns DB with normalize_access_code().
"""
from typing import Sequence, Union

from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "c1d2e3f4b5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PostgreSQL: strip non-alphanumeric, uppercase
    op.execute(
        """
        UPDATE access_codes
        SET code = upper(regexp_replace(code, '[^A-Za-z0-9]', '', 'g'))
        """
    )


def downgrade() -> None:
    # Cannot restore original hyphenation
    pass
