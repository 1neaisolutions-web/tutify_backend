"""rename_user_usage_quota_index

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-05-06

Avoid duplicate index name idx_user_tier (UserSubscription already uses it).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "c8d9e0f1a2b3"
down_revision: Union[str, None] = "b7c8d9e0f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("idx_user_tier", table_name="user_usage_quotas", if_exists=True)
    op.create_index(
        "idx_user_usage_quota_user_tier",
        "user_usage_quotas",
        ["user_id", "subscription_tier"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_user_usage_quota_user_tier", table_name="user_usage_quotas", if_exists=True)
    op.create_index(
        "idx_user_tier",
        "user_usage_quotas",
        ["user_id", "subscription_tier"],
        unique=False,
    )
