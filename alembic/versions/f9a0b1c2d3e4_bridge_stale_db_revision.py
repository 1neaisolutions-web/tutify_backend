"""Bridge missing stale revision f9a0b1c2d3e4 so alembic can upgrade.

This DB was stamped to a revision that no longer exists in the repo.
We recreate it as a no-op parent of the known local head chain.
"""
from typing import Sequence, Union

revision: str = "f9a0b1c2d3e4"
down_revision: Union[str, None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
