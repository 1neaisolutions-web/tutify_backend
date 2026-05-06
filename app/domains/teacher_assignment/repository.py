from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import desc, func, or_, cast, String
from sqlalchemy.orm import Session

from app.domains.teacher_assignment.models import (
    TeacherAssignment,
    TeacherAssignmentGenerationRun,
)


@dataclass(frozen=True)
class AssignmentListFilters:
    q: str | None = None
    subject: str | None = None
    grade: str | None = None
    status: str | None = None
    class_key: str | None = None
    date_from: str | None = None  # YYYY-MM-DD
    date_to: str | None = None  # YYYY-MM-DD


class TeacherAssignmentRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_assignments(
        self,
        tenant_id: UUID,
        filters: AssignmentListFilters,
        page: int = 1,
        page_size: int = 50,
    ) -> Tuple[List[TeacherAssignment], int]:
        q = self.db.query(TeacherAssignment).filter(TeacherAssignment.tenant_id == tenant_id)

        if filters.q:
            term = f"%{filters.q.lower()}%"
            q = q.filter(func.lower(TeacherAssignment.title).ilike(term))

        if filters.subject:
            q = q.filter(TeacherAssignment.subject == filters.subject)

        if filters.grade:
            q = q.filter(TeacherAssignment.grade == filters.grade)

        if filters.status:
            q = q.filter(TeacherAssignment.status == filters.status)

        if filters.class_key:
            bind = self.db.get_bind()
            dialect = bind.dialect.name if bind is not None else ""
            if dialect == "postgresql":
                q = q.filter(
                    TeacherAssignment.class_keys.contains([filters.class_key])  # type: ignore[attr-defined]
                )
            else:
                q = q.filter(
                    cast(TeacherAssignment.class_keys, String).ilike(f"%{filters.class_key}%")
                )

        bind = self.db.get_bind()
        dialect = bind.dialect.name if bind is not None else ""
        if dialect == "postgresql":
            if filters.date_from:
                q = q.filter(
                    or_(
                        TeacherAssignment.due_at.is_(None),
                        func.to_char(TeacherAssignment.due_at, "YYYY-MM-DD") >= filters.date_from,
                    )
                )
            if filters.date_to:
                q = q.filter(
                    or_(
                        TeacherAssignment.due_at.is_(None),
                        func.to_char(TeacherAssignment.due_at, "YYYY-MM-DD") <= filters.date_to,
                    )
                )

        q = q.order_by(
            desc(TeacherAssignment.updated_at),
            desc(TeacherAssignment.created_at),
        )
        total = q.count()
        offset = (page - 1) * page_size
        items = q.offset(offset).limit(page_size).all()
        return items, total

    def get_assignment(
        self,
        tenant_id: UUID,
        assignment_id: UUID,
    ) -> Optional[TeacherAssignment]:
        return (
            self.db.query(TeacherAssignment)
            .filter(
                TeacherAssignment.tenant_id == tenant_id,
                TeacherAssignment.id == assignment_id,
            )
            .first()
        )

    def create_assignment(self, assignment: TeacherAssignment) -> TeacherAssignment:
        self.db.add(assignment)
        self.db.commit()
        self.db.refresh(assignment)
        return assignment

    def update_assignment(self, assignment: TeacherAssignment) -> TeacherAssignment:
        self.db.add(assignment)
        self.db.commit()
        self.db.refresh(assignment)
        return assignment

    def delete_assignment(self, assignment: TeacherAssignment) -> None:
        self.db.delete(assignment)
        self.db.commit()

    def duplicate_assignment(
        self,
        *,
        source: TeacherAssignment,
        new_id: UUID,
        new_title: str,
        now: datetime,
    ) -> TeacherAssignment:
        copy = TeacherAssignment(
            id=new_id,
            tenant_id=source.tenant_id,
            owner_user_id=source.owner_user_id,
            title=new_title,
            subject=source.subject,
            grade=source.grade,
            assignment_type=source.assignment_type,
            rigor_profile=source.rigor_profile,
            student_instructions=source.student_instructions,
            teacher_notes=source.teacher_notes,
            status="draft" if source.status == "archived" else source.status,
            due_at=None,
            assigned_at=None,
            source_pack_ids=list(source.source_pack_ids or []),
            scope_topics=list(source.scope_topics or []),
            scope_refinement=source.scope_refinement,
            topic_summary=source.topic_summary,
            generate_without_sources=bool(source.generate_without_sources),
            difficulty=source.difficulty,
            brief_topics=list(source.brief_topics or []),
            handout_layout=source.handout_layout,
            class_keys=list(source.class_keys or []),
            topics_count=source.topics_count,
            lines_count=source.lines_count,
            assigned_count=0,
            submitted_count=0,
            pending_count=0,
            graded_count=0,
            content_version=1,
            created_at=now,
            updated_at=now,
        )
        self.db.add(copy)
        self.db.commit()
        self.db.refresh(copy)
        return copy

    def find_generation_run_by_idempotency(
        self,
        assignment_id: UUID,
        idempotency_key: str,
    ) -> Optional[TeacherAssignmentGenerationRun]:
        return (
            self.db.query(TeacherAssignmentGenerationRun)
            .filter(
                TeacherAssignmentGenerationRun.assignment_id == assignment_id,
                TeacherAssignmentGenerationRun.idempotency_key == idempotency_key,
            )
            .order_by(desc(TeacherAssignmentGenerationRun.created_at))
            .first()
        )

    def create_generation_run(self, run: TeacherAssignmentGenerationRun) -> TeacherAssignmentGenerationRun:
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run
