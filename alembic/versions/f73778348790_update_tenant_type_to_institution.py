"""update tenant type to institution

Revision ID: f73778348790
Revises: d1e2f3a4b5c6
Create Date: 2026-06-15 10:14:17.938235

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f73778348790'
down_revision: Union[str, None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ensure enum value is committed before UPDATE (PostgreSQL restriction).
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE tenanttype ADD VALUE IF NOT EXISTS 'institution'")

    connection = op.get_bind()
    connection.execute(sa.text("""
        UPDATE tenants
        SET type = 'institution'
        WHERE type = 'school'
    """))


def downgrade() -> None:
    connection = op.get_bind()

    connection.execute(sa.text("""
        UPDATE tenants 
        SET type = 'school' 
        WHERE type = 'institution'
    """))

