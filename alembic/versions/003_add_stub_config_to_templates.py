"""Add stub_config to templates

Revision ID: 003_add_stub_config
Revises: c975d20ddc1d
Create Date: 2026-02-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "003_add_stub_config"
down_revision: Union[str, None] = "c975d20ddc1d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [c["name"] for c in inspector.get_columns("templates")]
    if "stub_config" not in columns:
        op.add_column(
            "templates",
            sa.Column("stub_config", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("templates", "stub_config")
