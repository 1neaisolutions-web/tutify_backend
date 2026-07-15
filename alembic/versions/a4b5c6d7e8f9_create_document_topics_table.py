"""Create document_topics table and chunks.topic_fk.

Revision ID: a4b5c6d7e8f9
Revises: d1e2f3a4b5c6
Create Date: 2026-06-05

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a4b5c6d7e8f9"
down_revision: Union[str, None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = current_database()
              AND pid <> pg_backend_pid()
              AND state = 'idle in transaction'
              AND query_start < now() - interval '30 seconds'
            """
        )
    )
    op.execute(sa.text("SET lock_timeout = '120s'"))
    op.execute(sa.text("SET statement_timeout = '300s'"))
    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS document_topics (
                id UUID NOT NULL,
                document_id UUID NOT NULL,
                topic_key VARCHAR(100) NOT NULL,
                parent_key VARCHAR(100),
                level SMALLINT DEFAULT 1 NOT NULL,
                display_title VARCHAR(500) NOT NULL,
                start_page_pdf INTEGER,
                end_page_pdf INTEGER,
                sort_order INTEGER DEFAULT 0 NOT NULL,
                chunk_count INTEGER DEFAULT 0 NOT NULL,
                created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
                updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
                PRIMARY KEY (id),
                CONSTRAINT uq_document_topic UNIQUE (document_id, topic_key),
                CONSTRAINT fk_document_topics_document_id
                    FOREIGN KEY (document_id) REFERENCES documents (id) ON DELETE CASCADE
            )
            """
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS idx_document_topics_document "
            "ON document_topics (document_id)"
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS idx_document_topics_parent "
            "ON document_topics (document_id, parent_key)"
        )
    )
    op.execute(
        sa.text("CREATE INDEX IF NOT EXISTS ix_document_topics_id ON document_topics (id)")
    )
    op.execute(sa.text("ALTER TABLE chunks ADD COLUMN IF NOT EXISTS topic_fk UUID"))
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = 'fk_chunks_topic_fk_document_topics'
                ) THEN
                    ALTER TABLE chunks
                    ADD CONSTRAINT fk_chunks_topic_fk_document_topics
                    FOREIGN KEY (topic_fk) REFERENCES document_topics (id)
                    ON DELETE SET NULL;
                END IF;
            END $$;
            """
        )
    )
    op.execute(
        sa.text("CREATE INDEX IF NOT EXISTS idx_chunks_topic_fk ON chunks (topic_fk)")
    )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS idx_chunks_topic_fk"))
    op.execute(
        sa.text(
            "ALTER TABLE chunks DROP CONSTRAINT IF EXISTS fk_chunks_topic_fk_document_topics"
        )
    )
    op.execute(sa.text("ALTER TABLE chunks DROP COLUMN IF EXISTS topic_fk"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_document_topics_id"))
    op.execute(sa.text("DROP INDEX IF EXISTS idx_document_topics_parent"))
    op.execute(sa.text("DROP INDEX IF EXISTS idx_document_topics_document"))
    op.execute(sa.text("DROP TABLE IF EXISTS document_topics"))
