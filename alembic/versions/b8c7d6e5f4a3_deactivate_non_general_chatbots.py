"""deactivate_non_general_chatbots

Revision ID: b8c7d6e5f4a3
Revises: a9b8c7d6e5f4
Create Date: 2025-05-02 10:01:00.000000

Only the general-teaching-assistant chatbot is shown during the initial launch.
All others remain in the database (is_active=False) and can be re-enabled via
the admin panel when ready.
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'b8c7d6e5f4a3'
down_revision: Union[str, None] = 'a9b8c7d6e5f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        UPDATE chatbots
        SET is_active = false
        WHERE slug != 'general-teaching-assistant'
    """)


def downgrade() -> None:
    op.execute("UPDATE chatbots SET is_active = true")
