"""Add stub_config to template_versions

Revision ID: 004_stub_config_versions
Revises: 003_add_stub_config
Create Date: 2026-02-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "004_stub_config_versions"
down_revision: Union[str, None] = "003_add_stub_config"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [c["name"] for c in inspector.get_columns("template_versions")]
    if "stub_config" not in columns:
        op.add_column(
            "template_versions",
            sa.Column("stub_config", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("template_versions", "stub_config")
