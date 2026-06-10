"""Create document_topics_health view.

Revision ID: d7e8f9a0b1c2
Revises: c6d7e8f9a0b1
Create Date: 2026-06-05

"""
from typing import Sequence, Union

from alembic import op

revision: str = "d7e8f9a0b1c2"
down_revision: Union[str, None] = "c6d7e8f9a0b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE VIEW document_topics_health AS
        SELECT
            d.id AS document_id,
            d.tenant_id AS tenant_id,
            d.filename,
            d.status,
            COUNT(dt.id) AS total_topics,
            SUM(CASE WHEN dt.chunk_count = 0 THEN 1 ELSE 0 END) AS empty_topics,
            SUM(CASE WHEN dt.topic_key LIKE 'scope:pages%%' THEN 1 ELSE 0 END) AS fallback_topics,
            SUM(dt.chunk_count) AS total_chunks,
            ROUND(
                100.0 * SUM(CASE WHEN dt.topic_key NOT LIKE 'scope:pages%%' THEN dt.chunk_count ELSE 0 END)
                / NULLIF(SUM(dt.chunk_count), 0), 1
            ) AS chapter_coverage_pct
        FROM documents d
        LEFT JOIN document_topics dt ON dt.document_id = d.id
        GROUP BY d.id, d.tenant_id, d.filename, d.status
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS document_topics_health")
