"""
SQLAlchemy models for Teacher Tools quizzes.

Key constraint: quiz generation reads only published chunks from ingestion and
never calls OCR providers directly.
"""

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


class TeacherQuiz(Base):
    """A teacher-authored quiz aligned to the Teacher Tools UI contract."""

    __tablename__ = "teacher_quizzes"

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
    student_instructions = Column(Text, nullable=True)
    teacher_notes = Column(Text, nullable=True)
    time_limit_minutes = Column(Integer, nullable=False, default=30)

    # draft | published | scheduled | archived
    status = Column(String(32), nullable=False, default="draft", index=True)
    assigned_at = Column(DateTime(timezone=True), nullable=True)
    due_at = Column(DateTime(timezone=True), nullable=True)

    # RAG scope (pack IDs, topics, refinement)
    source_pack_ids = Column(JSONB, nullable=False, default=list)  # list[str] UUID strings
    scope_topics = Column(JSONB, nullable=False, default=list)  # list[str]
    scope_topic_ids = Column(JSONB, nullable=True)  # list[str] document_topics.id UUIDs
    scope_book_ids = Column(JSONB, nullable=True)  # [{pack_id, doc_id, topic_ids[]}]
    scope_refinement = Column(Text, nullable=True)
    topic_summary = Column(Text, nullable=True)  # pre-computed display label
    generate_without_sources = Column(Boolean, nullable=False, default=False)

    difficulty = Column(String(32), nullable=True)  # foundation | standard | challenge
    shuffle_questions = Column(Boolean, nullable=False, default=True)
    shuffle_answers = Column(Boolean, nullable=False, default=True)
    negative_marking = Column(Boolean, nullable=False, default=False)

    handout_layout = Column(JSONB, nullable=True)
    class_keys = Column(JSONB, nullable=False, default=list)  # UI "classes" (e.g. ["g8c"])

    # denormalized counts for list performance
    questions_count = Column(Integer, nullable=False, default=0)
    total_marks = Column(Float, nullable=False, default=0.0)
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

    questions = relationship(
        "TeacherQuizQuestion",
        back_populates="quiz",
        cascade="all, delete-orphan",
        order_by="TeacherQuizQuestion.sort_order",
    )
    generation_runs = relationship(
        "TeacherQuizGenerationRun",
        back_populates="quiz",
        cascade="all, delete-orphan",
        order_by="TeacherQuizGenerationRun.created_at",
    )

    __table_args__ = (
        Index("ix_teacher_quizzes_tenant_status_updated", "tenant_id", "status", "updated_at"),
    )


class TeacherQuizQuestion(Base):
    """One question belonging to a teacher quiz."""

    __tablename__ = "teacher_quiz_questions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    quiz_id = Column(
        UUID(as_uuid=True),
        ForeignKey("teacher_quizzes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    sort_order = Column(Integer, nullable=False, default=0)
    # mcq | tf | short
    type = Column(String(16), nullable=False)
    prompt = Column(Text, nullable=False)
    points = Column(Float, nullable=False, default=1.0)
    options = Column(JSONB, nullable=True)  # list[str] for mcq
    response_lines = Column(Integer, nullable=True)  # short only
    extra = Column(JSONB, nullable=True)  # review badges, metadata

    quiz = relationship("TeacherQuiz", back_populates="questions")


class TeacherQuizGenerationRun(Base):
    """Audit row for each generate/regenerate operation."""

    __tablename__ = "teacher_quiz_generation_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    quiz_id = Column(
        UUID(as_uuid=True),
        ForeignKey("teacher_quizzes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # pending | completed | failed
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

    quiz = relationship("TeacherQuiz", back_populates="generation_runs")

    __table_args__ = (
        Index("ix_teacher_quiz_gen_quiz_created", "quiz_id", "created_at"),
    )

