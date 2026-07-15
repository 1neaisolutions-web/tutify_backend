"""SQLAlchemy models for Teacher Tools worksheets."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Boolean,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.db.base_class import Base


class TeacherWorksheet(Base):
    __tablename__ = "teacher_worksheets"

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
    output_format = Column(String(32), nullable=False, default="interactive_digital")
    class_keys = Column(JSONB, nullable=False, default=list)
    student_instructions = Column(Text, nullable=True)
    teacher_notes = Column(Text, nullable=True)

    status = Column(String(32), nullable=False, default="draft", index=True)
    assigned_at = Column(DateTime(timezone=True), nullable=True)
    due_at = Column(DateTime(timezone=True), nullable=True)

    source_pack_ids = Column(JSONB, nullable=False, default=list)
    scope_topics = Column(JSONB, nullable=False, default=list)
    scope_topic_ids = Column(JSONB, nullable=True)
    scope_refinement = Column(Text, nullable=True)
    topic_summary = Column(Text, nullable=True)
    generate_without_sources = Column(Boolean, nullable=False, default=False)

    difficulty = Column(String(32), nullable=True)
    handout_layout = Column(JSONB, nullable=True)

    sessions_count = Column(Integer, nullable=False, default=0)
    blocks_count = Column(Integer, nullable=False, default=0)
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

    sessions = relationship(
        "TeacherWorksheetSession",
        back_populates="worksheet",
        cascade="all, delete-orphan",
        order_by="TeacherWorksheetSession.sort_order",
    )
    generation_runs = relationship(
        "TeacherWorksheetGenerationRun",
        back_populates="worksheet",
        cascade="all, delete-orphan",
        order_by="TeacherWorksheetGenerationRun.created_at",
    )

    __table_args__ = (Index("ix_teacher_worksheets_tenant_status_updated", "tenant_id", "status", "updated_at"),)


class TeacherWorksheetSession(Base):
    __tablename__ = "teacher_worksheet_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    worksheet_id = Column(
        UUID(as_uuid=True),
        ForeignKey("teacher_worksheets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sort_order = Column(Integer, nullable=False, default=0)
    title = Column(String(255), nullable=False, default="Session 1")
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    worksheet = relationship("TeacherWorksheet", back_populates="sessions")
    blocks = relationship(
        "TeacherWorksheetBlock",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="TeacherWorksheetBlock.sort_order",
    )

    __table_args__ = (Index("ix_teacher_worksheet_sessions_worksheet", "worksheet_id", "sort_order"),)


class TeacherWorksheetBlock(Base):
    __tablename__ = "teacher_worksheet_blocks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    worksheet_id = Column(
        UUID(as_uuid=True),
        ForeignKey("teacher_worksheets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("teacher_worksheet_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sort_order = Column(Integer, nullable=False, default=0)
    type = Column(String(16), nullable=False)
    prompt = Column(Text, nullable=True)
    points = Column(Float, nullable=False, default=1.0)
    data = Column(JSONB, nullable=False, default=dict)

    session = relationship("TeacherWorksheetSession", back_populates="blocks")

    __table_args__ = (
        Index("ix_teacher_worksheet_blocks_session", "session_id", "sort_order"),
        Index("ix_teacher_worksheet_blocks_worksheet", "worksheet_id"),
    )


class TeacherWorksheetGenerationRun(Base):
    __tablename__ = "teacher_worksheet_generation_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    worksheet_id = Column(
        UUID(as_uuid=True),
        ForeignKey("teacher_worksheets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scope = Column(String(16), nullable=False, default="all")
    target_block_id = Column(UUID(as_uuid=True), nullable=True)

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

    worksheet = relationship("TeacherWorksheet", back_populates="generation_runs")

    __table_args__ = (
        Index("ix_wsheet_gen_worksheet_created", "worksheet_id", "created_at"),
        Index("ix_wsheet_gen_idempotency_key", "idempotency_key"),
    )
