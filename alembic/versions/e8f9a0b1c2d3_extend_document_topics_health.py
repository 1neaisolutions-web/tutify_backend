"""Extend document_topics_health view with section and mislabel metrics.

Revision ID: e8f9a0b1c2d3
Revises: d7e8f9a0b1c2
Create Date: 2026-06-10

"""
from typing import Sequence, Union

from alembic import op

revision: str = "e8f9a0b1c2d3"
down_revision: Union[str, None] = "d7e8f9a0b1c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP VIEW IF EXISTS document_topics_health")
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
            SUM(CASE WHEN dt.level = 2 THEN 1 ELSE 0 END) AS section_count,
            (
                SELECT COUNT(*)
                FROM chunks c
                JOIN document_topics dt2 ON c.topic_fk = dt2.id
                WHERE c.document_id = d.id
                  AND c.page_start_pdf IS NOT NULL
                  AND dt2.start_page_pdf IS NOT NULL
                  AND (
                    c.page_start_pdf < dt2.start_page_pdf
                    OR (dt2.end_page_pdf IS NOT NULL AND c.page_end_pdf > dt2.end_page_pdf)
                  )
            ) AS mislabeled_chunk_count,
            (
                SELECT COUNT(*)
                FROM document_topics ch
                WHERE ch.document_id = d.id
                  AND ch.level = 1
                  AND ch.topic_key NOT LIKE 'scope:pages%%'
                  AND NOT EXISTS (
                    SELECT 1 FROM document_topics sec
                    WHERE sec.document_id = d.id AND sec.level = 2 AND sec.parent_key = ch.topic_key
                  )
            ) AS chapters_without_sections,
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
