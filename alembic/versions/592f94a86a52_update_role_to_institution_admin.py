"""update role to institution_admin

Revision ID: 592f94a86a52
Revises: f73778348790
Create Date: 2026-06-15 10:34:29.954053

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '592f94a86a52'
down_revision: Union[str, None] = 'f73778348790'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ensure enum value is committed before UPDATE (PostgreSQL restriction).
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE rolename ADD VALUE IF NOT EXISTS 'institution_admin'")

    connection = op.get_bind()
    connection.execute(sa.text("""
        UPDATE roles
        SET name = 'institution_admin'::rolename
        WHERE name = 'school_admin'::rolename
    """))


def downgrade() -> None:
 
  connection = op.get_bind()
  connection.execute(sa.text("""
        UPDATE roles
        SET name = 'school_admin'::rolename
        WHERE name = 'institution_admin'::rolename
    """))

