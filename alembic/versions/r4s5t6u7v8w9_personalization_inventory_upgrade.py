"""personalization_inventory_upgrade

Revision ID: r4s5t6u7v8w9
Revises: q3r4s5t6u7v8
Create Date: 2026-04-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "r4s5t6u7v8w9"
down_revision: Union[str, None] = "q3r4s5t6u7v8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "personalized_content_assignments",
        sa.Column("priority_rank", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "personalized_content_assignments",
        sa.Column("diversity_key", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "idx_pca_user_section_bucket",
        "personalized_content_assignments",
        ["user_id", "section", "bucket", "position"],
    )

    # Upgrade section inventory targets to production staging requirements.
    op.execute(
        """
        UPDATE section_inventory_config
        SET
          visible_count = CASE section
            WHEN 'micro_courses' THEN 5
            WHEN 'growth_recommendations' THEN 3
            WHEN 'tutorials' THEN 3
            WHEN 'research_insights' THEN 5
            WHEN 'specialist_tracks' THEN 3
            ELSE visible_count
          END,
          locked_preview_count = CASE section
            WHEN 'micro_courses' THEN 5
            WHEN 'growth_recommendations' THEN 3
            WHEN 'tutorials' THEN 3
            WHEN 'research_insights' THEN 5
            WHEN 'specialist_tracks' THEN 3
            ELSE locked_preview_count
          END,
          reserve_buffer_count = CASE section
            WHEN 'micro_courses' THEN 10
            WHEN 'growth_recommendations' THEN 6
            WHEN 'tutorials' THEN 6
            WHEN 'research_insights' THEN 10
            WHEN 'specialist_tracks' THEN 6
            ELSE reserve_buffer_count
          END
        """
    )


def downgrade() -> None:
    op.drop_index("idx_pca_user_section_bucket", table_name="personalized_content_assignments")
    op.drop_column("personalized_content_assignments", "diversity_key")
    op.drop_column("personalized_content_assignments", "priority_rank")
