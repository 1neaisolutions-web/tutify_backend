"""worksheet_user_id_and_question_hashes

Revision ID: f7g8h9i0j1k2
Revises: e1e2e3e4e5e6
Create Date: 2026-02-09 12:00:00.000000

- worksheet_cache: add user_id (nullable) for regenerate dedupe
- worksheet_question_hashes: new table for per-user question hashes (regenerate uniqueness)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "f7g8h9i0j1k2"
down_revision: Union[str, None] = "e1e2e3e4e5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "worksheet_cache",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(op.f("ix_worksheet_cache_user_id"), "worksheet_cache", ["user_id"], unique=False)

    op.create_table(
        "worksheet_question_hashes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pack_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("topic_signature", sa.String(length=64), nullable=False),
        sa.Column("difficulty", sa.String(length=20), nullable=True),
        sa.Column("question_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["pack_id"], ["content_packs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_worksheet_question_hashes_user_id"), "worksheet_question_hashes", ["user_id"], unique=False)
    op.create_index(op.f("ix_worksheet_question_hashes_pack_id"), "worksheet_question_hashes", ["pack_id"], unique=False)
    op.create_index(op.f("ix_worksheet_question_hashes_topic_signature"), "worksheet_question_hashes", ["topic_signature"], unique=False)
    op.create_index(op.f("ix_worksheet_question_hashes_difficulty"), "worksheet_question_hashes", ["difficulty"], unique=False)
    op.create_index(op.f("ix_worksheet_question_hashes_question_hash"), "worksheet_question_hashes", ["question_hash"], unique=False)
    op.create_index(
        "ix_wqh_user_pack_topic_diff",
        "worksheet_question_hashes",
        ["user_id", "pack_id", "topic_signature", "difficulty"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_wqh_user_pack_topic_diff", table_name="worksheet_question_hashes")
    op.drop_index(op.f("ix_worksheet_question_hashes_question_hash"), table_name="worksheet_question_hashes")
    op.drop_index(op.f("ix_worksheet_question_hashes_difficulty"), table_name="worksheet_question_hashes")
    op.drop_index(op.f("ix_worksheet_question_hashes_topic_signature"), table_name="worksheet_question_hashes")
    op.drop_index(op.f("ix_worksheet_question_hashes_pack_id"), table_name="worksheet_question_hashes")
    op.drop_index(op.f("ix_worksheet_question_hashes_user_id"), table_name="worksheet_question_hashes")
    op.drop_table("worksheet_question_hashes")

    op.drop_index(op.f("ix_worksheet_cache_user_id"), table_name="worksheet_cache")
    op.drop_column("worksheet_cache", "user_id")
