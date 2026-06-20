"""
SQLAlchemy models for Teacher Tools exams (paper composition + scheduling).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.db.base_class import Base


class TeacherExam(Base):
    """Teacher-authored exam aligned to the Teacher Tools exam UI contract."""

    __tablename__ = "teacher_exams"

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
    exam_type = Column(String(80), nullable=False, default="Unit test")
    term = Column(String(40), nullable=False, default="Term 1")
    international_standard = Column(String(80), nullable=False, default="Standard")

    duration_minutes = Column(Integer, nullable=False, default=60)
    total_marks = Column(Float, nullable=False, default=0.0)
    schedule_start = Column(DateTime(timezone=True), nullable=True)
    schedule_end = Column(DateTime(timezone=True), nullable=True)
    class_keys = Column(JSONB, nullable=False, default=list)

    status = Column(String(32), nullable=False, default="draft", index=True)
    completion_pct = Column(Float, nullable=False, default=0.0)
    section_target_count = Column(Integer, nullable=False, default=4)

    source_pack_ids = Column(JSONB, nullable=False, default=list)
    scope_topics = Column(JSONB, nullable=False, default=list)
    scope_topic_ids = Column(JSONB, nullable=True)
    scope_refinement = Column(Text, nullable=True)
    topic_summary = Column(Text, nullable=True)
    generate_without_sources = Column(Boolean, nullable=False, default=False)

    paper_config = Column(JSONB, nullable=False, default=dict)
    handout_layout = Column(JSONB, nullable=True)
    student_instructions = Column(Text, nullable=True)
    teacher_notes = Column(Text, nullable=True)

    sections_count = Column(Integer, nullable=False, default=0)
    mcq_count = Column(Integer, nullable=False, default=0)
    short_count = Column(Integer, nullable=False, default=0)
    long_count = Column(Integer, nullable=False, default=0)
    submission_count = Column(Integer, nullable=False, default=0)
    avg_score = Column(Float, nullable=True)
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

    sections = relationship(
        "TeacherExamSection",
        back_populates="exam",
        cascade="all, delete-orphan",
        order_by="TeacherExamSection.sort_order",
    )
    questions = relationship(
        "TeacherExamQuestion",
        back_populates="exam",
        cascade="all, delete-orphan",
        order_by="TeacherExamQuestion.sort_order",
    )
    generation_runs = relationship(
        "TeacherExamGenerationRun",
        back_populates="exam",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_teacher_exams_tenant_status_updated", "tenant_id", "status", "updated_at"),
        Index("ix_teacher_exams_tenant_schedule", "tenant_id", "schedule_start"),
    )


class TeacherExamSection(Base):
    __tablename__ = "teacher_exam_sections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    exam_id = Column(
        UUID(as_uuid=True),
        ForeignKey("teacher_exams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sort_order = Column(Integer, nullable=False, default=0)
    title = Column(String(300), nullable=False)
    marks = Column(Float, nullable=False, default=0.0)
    description = Column(Text, nullable=True)

    exam = relationship("TeacherExam", back_populates="sections")

    __table_args__ = (Index("ix_teacher_exam_sections_exam", "exam_id", "sort_order"),)


class TeacherExamQuestion(Base):
    __tablename__ = "teacher_exam_questions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    exam_id = Column(
        UUID(as_uuid=True),
        ForeignKey("teacher_exams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_type = Column(String(16), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    stem = Column(Text, nullable=False)
    options = Column(JSONB, nullable=True)
    subparts = Column(JSONB, nullable=True)
    marks_per = Column(Float, nullable=False, default=1.0)

    exam = relationship("TeacherExam", back_populates="questions")

    __table_args__ = (Index("ix_teacher_exam_questions_exam_type", "exam_id", "question_type", "sort_order"),)


class TeacherExamGenerationRun(Base):
    __tablename__ = "teacher_exam_generation_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    exam_id = Column(
        UUID(as_uuid=True),
        ForeignKey("teacher_exams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scope = Column(String(16), nullable=False, default="all")
    target_question_id = Column(UUID(as_uuid=True), nullable=True)

    status = Column(String(32), nullable=False, default="completed")
    error_code = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)

    input_hash = Column(String(64), nullable=True)
    idempotency_key = Column(String(128), nullable=True)
    retrieval_warnings = Column(JSONB, nullable=True)
    retrieval_metadata = Column(JSONB, nullable=True)
    llm_model = Column(String(120), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    exam = relationship("TeacherExam", back_populates="generation_runs")

    __table_args__ = (
        Index("ix_exam_gen_exam_created", "exam_id", "created_at"),
        # Idempotency is scoped per exam.
        Index("ix_exam_gen_idempotency", "exam_id", "idempotency_key", unique=True),
    )
