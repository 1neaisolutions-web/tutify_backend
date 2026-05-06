"""add ocr_policy and structure_map

Revision ID: b1c2d3e4f5a6
Revises: da71b2113835
Create Date: 2026-02-13

Adds ContentPack.ocr_policy (math | non_math | auto) and Document.structure_map (JSONB).
Backward compatible: both nullable with defaults.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "da71b2113835"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "content_packs",
        sa.Column("ocr_policy", sa.String(50), nullable=True, server_default="auto"),
    )
    op.add_column(
        "documents",
        sa.Column("structure_map", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("documents", "structure_map")
    op.drop_column("content_packs", "ocr_policy")
