"""Add chatbots.exclude_from_history; set TRUE for general-teaching-assistant.

Revision ID: z2a3b4c5d6e7
Revises: y1z2a3b4c5d6
Create Date: 2026-05-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "z2a3b4c5d6e7"
down_revision: Union[str, tuple, None] = "y1z2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "chatbots",
        sa.Column(
            "exclude_from_history",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.execute(
        """
        UPDATE chatbots
        SET exclude_from_history = TRUE
        WHERE slug = 'general-teaching-assistant'
        """
    )


def downgrade() -> None:
    op.drop_column("chatbots", "exclude_from_history")
