"""create_teacher_identity_tables

Revision ID: b2c3d4e5f6a7
Revises: a2b3c4d5e6f7
Create Date: 2026-03-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # teacher_experiences
    op.create_table(
        "teacher_experiences",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("institution_name", sa.String(200), nullable=False),
        sa.Column("role_title", sa.String(200), nullable=False),
        sa.Column("subject_area", sa.String(100), nullable=True),
        sa.Column("grade_band", sa.String(50), nullable=True),
        sa.Column("employment_type", sa.String(50), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("location_city", sa.String(100), nullable=True),
        sa.Column("location_country", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_teacher_experiences_id"), "teacher_experiences", ["id"], unique=False)
    op.create_index(op.f("ix_teacher_experiences_user_id"), "teacher_experiences", ["user_id"], unique=False)
    op.create_index(op.f("ix_teacher_experiences_employment_type"), "teacher_experiences", ["employment_type"], unique=False)
    op.create_index("idx_teacher_experience_user_dates", "teacher_experiences", ["user_id", "start_date"], unique=False)

    # teacher_education
    op.create_table(
        "teacher_education",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("institution_name", sa.String(200), nullable=False),
        sa.Column("degree", sa.String(200), nullable=False),
        sa.Column("field_of_study", sa.String(200), nullable=False),
        sa.Column("start_year", sa.Integer(), nullable=True),
        sa.Column("end_year", sa.Integer(), nullable=True),
        sa.Column("is_completed", sa.Boolean(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_teacher_education_id"), "teacher_education", ["id"], unique=False)
    op.create_index(op.f("ix_teacher_education_user_id"), "teacher_education", ["user_id"], unique=False)
    op.create_index("idx_teacher_education_user", "teacher_education", ["user_id", "end_year"], unique=False)

    # teacher_career_documents (before teacher_certifications due to FK)
    op.create_table(
        "teacher_career_documents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("document_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("file_name", sa.String(500), nullable=False),
        sa.Column("file_path", sa.String(1000), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_teacher_career_documents_id"), "teacher_career_documents", ["id"], unique=False)
    op.create_index(op.f("ix_teacher_career_documents_user_id"), "teacher_career_documents", ["user_id"], unique=False)
    op.create_index(op.f("ix_teacher_career_documents_document_type"), "teacher_career_documents", ["document_type"], unique=False)
    op.create_index(op.f("ix_teacher_career_documents_status"), "teacher_career_documents", ["status"], unique=False)
    op.create_index("idx_teacher_career_doc_user_type", "teacher_career_documents", ["user_id", "document_type"], unique=False)

    # teacher_certifications
    op.create_table(
        "teacher_certifications",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("issuer", sa.String(200), nullable=False),
        sa.Column("license_number", sa.String(100), nullable=True),
        sa.Column("issue_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("credential_url", sa.String(500), nullable=True),
        sa.Column("document_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["teacher_career_documents.id"], ondelete="SET NULL"),
    )
    op.create_index(op.f("ix_teacher_certifications_id"), "teacher_certifications", ["id"], unique=False)
    op.create_index(op.f("ix_teacher_certifications_user_id"), "teacher_certifications", ["user_id"], unique=False)
    op.create_index(op.f("ix_teacher_certifications_document_id"), "teacher_certifications", ["document_id"], unique=False)
    op.create_index("idx_teacher_cert_user", "teacher_certifications", ["user_id"], unique=False)

    # teacher_achievements
    op.create_table(
        "teacher_achievements",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("organization", sa.String(200), nullable=True),
        sa.Column("date", sa.Date(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_teacher_achievements_id"), "teacher_achievements", ["id"], unique=False)
    op.create_index(op.f("ix_teacher_achievements_user_id"), "teacher_achievements", ["user_id"], unique=False)
    op.create_index("idx_teacher_achievement_user", "teacher_achievements", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_teacher_achievement_user", table_name="teacher_achievements")
    op.drop_index(op.f("ix_teacher_achievements_user_id"), table_name="teacher_achievements")
    op.drop_index(op.f("ix_teacher_achievements_id"), table_name="teacher_achievements")
    op.drop_table("teacher_achievements")

    op.drop_index("idx_teacher_cert_user", table_name="teacher_certifications")
    op.drop_index(op.f("ix_teacher_certifications_document_id"), table_name="teacher_certifications")
    op.drop_index(op.f("ix_teacher_certifications_user_id"), table_name="teacher_certifications")
    op.drop_index(op.f("ix_teacher_certifications_id"), table_name="teacher_certifications")
    op.drop_table("teacher_certifications")

    op.drop_index("idx_teacher_career_doc_user_type", table_name="teacher_career_documents")
    op.drop_index(op.f("ix_teacher_career_documents_status"), table_name="teacher_career_documents")
    op.drop_index(op.f("ix_teacher_career_documents_document_type"), table_name="teacher_career_documents")
    op.drop_index(op.f("ix_teacher_career_documents_user_id"), table_name="teacher_career_documents")
    op.drop_index(op.f("ix_teacher_career_documents_id"), table_name="teacher_career_documents")
    op.drop_table("teacher_career_documents")

    op.drop_index("idx_teacher_education_user", table_name="teacher_education")
    op.drop_index(op.f("ix_teacher_education_user_id"), table_name="teacher_education")
    op.drop_index(op.f("ix_teacher_education_id"), table_name="teacher_education")
    op.drop_table("teacher_education")

    op.drop_index("idx_teacher_experience_user_dates", table_name="teacher_experiences")
    op.drop_index(op.f("ix_teacher_experiences_employment_type"), table_name="teacher_experiences")
    op.drop_index(op.f("ix_teacher_experiences_user_id"), table_name="teacher_experiences")
    op.drop_index(op.f("ix_teacher_experiences_id"), table_name="teacher_experiences")
    op.drop_table("teacher_experiences")
