"""
SQLAlchemy models for Teacher Tools assignments.

brief_topics is stored as JSONB (array of {id, title, lines:[{id,text}]}).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.db.base_class import Base


class TeacherAssignment(Base):
    """A teacher-authored assignment brief aligned to the Teacher Tools UI contract."""

    __tablename__ = "teacher_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    owner_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False,
        index=True,
    )

    title = Column(String(500), nullable=False)
    subject = Column(String(120), nullable=False)
    grade = Column(String(80), nullable=False)
    assignment_type = Column(String(80), nullable=False, default="Structured response")
    rigor_profile = Column(String(80), nullable=False, default="Standard")
    student_instructions = Column(Text, nullable=True)
    teacher_notes = Column(Text, nullable=True)

    # draft | active | pending_review | graded | archived
    status = Column(String(32), nullable=False, default="draft", index=True)
    due_at = Column(DateTime(timezone=True), nullable=True)
    assigned_at = Column(DateTime(timezone=True), nullable=True)

    # RAG scope
    source_pack_ids = Column(JSONB, nullable=False, default=list)
    scope_topics = Column(JSONB, nullable=False, default=list)
    scope_refinement = Column(Text, nullable=True)
    topic_summary = Column(Text, nullable=True)
    generate_without_sources = Column(Boolean, nullable=False, default=False)

    difficulty = Column(String(32), nullable=True)  # foundation | standard | challenge

    brief_topics = Column(JSONB, nullable=False, default=list)
    handout_layout = Column(JSONB, nullable=True)
    class_keys = Column(JSONB, nullable=False, default=list)

    topics_count = Column(Integer, nullable=False, default=0)
    lines_count = Column(Integer, nullable=False, default=0)
    assigned_count = Column(Integer, nullable=False, default=0)
    submitted_count = Column(Integer, nullable=False, default=0)
    pending_count = Column(Integer, nullable=False, default=0)
    graded_count = Column(Integer, nullable=False, default=0)

    content_version = Column(Integer, nullable=False, default=1)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    generation_runs = relationship(
        "TeacherAssignmentGenerationRun",
        back_populates="assignment",
        cascade="all, delete-orphan",
        order_by="TeacherAssignmentGenerationRun.created_at",
    )

    __table_args__ = (
        Index(
            "ix_teacher_assignments_tenant_status_updated",
            "tenant_id",
            "status",
            "updated_at",
        ),
    )


class TeacherAssignmentGenerationRun(Base):
    """Audit row for each generate/regenerate operation."""

    __tablename__ = "teacher_assignment_generation_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    assignment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("teacher_assignments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    run_type = Column(String(16), nullable=False, default="full")
    status = Column(String(32), nullable=False, default="completed")
    error_code = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)

    input_hash = Column(String(64), nullable=True)
    idempotency_key = Column(String(128), nullable=True, index=True)
    retrieval_warnings = Column(JSONB, nullable=True)
    retrieval_metadata = Column(JSONB, nullable=True)
    llm_model = Column(String(120), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    assignment = relationship("TeacherAssignment", back_populates="generation_runs")

    __table_args__ = (
        Index("ix_teacher_assignment_gen_assign_created", "assignment_id", "created_at"),
    )
