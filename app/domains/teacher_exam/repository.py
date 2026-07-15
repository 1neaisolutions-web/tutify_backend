from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, List, Optional, Tuple
from uuid import UUID, uuid4

from sqlalchemy import String, cast, desc, func, or_
from sqlalchemy.orm import Session, joinedload

from app.domains.teacher_exam.models import (
    TeacherExam,
    TeacherExamGenerationRun,
    TeacherExamQuestion,
    TeacherExamSection,
)


@dataclass(frozen=True)
class ExamListFilters:
    q: str | None = None
    subject: str | None = None
    grade: str | None = None
    status: str | None = None
    class_key: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    exam_type: str | None = None
    term: str | None = None


class TeacherExamRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_exams(
        self,
        tenant_id: UUID,
        filters: ExamListFilters,
        page: int = 1,
        page_size: int = 50,
        owner_user_id: Optional[UUID] = None,
    ) -> Tuple[List[TeacherExam], int]:
        q = self.db.query(TeacherExam).filter(TeacherExam.tenant_id == tenant_id)
        if owner_user_id is not None:
            q = q.filter(TeacherExam.owner_user_id == owner_user_id)

        if filters.q:
            term = f"%{filters.q.lower()}%"
            q = q.filter(func.lower(TeacherExam.title).ilike(term))

        if filters.subject:
            q = q.filter(TeacherExam.subject == filters.subject)

        if filters.grade:
            q = q.filter(TeacherExam.grade == filters.grade)

        if filters.status:
            q = q.filter(TeacherExam.status == filters.status)

        if filters.exam_type:
            q = q.filter(TeacherExam.exam_type == filters.exam_type)

        if filters.term:
            q = q.filter(TeacherExam.term == filters.term)

        if filters.class_key:
            bind = self.db.get_bind()
            dialect = bind.dialect.name if bind is not None else ""
            if dialect == "postgresql":
                q = q.filter(TeacherExam.class_keys.contains([filters.class_key]))  # type: ignore[attr-defined]
            else:
                q = q.filter(cast(TeacherExam.class_keys, String).ilike(f"%{filters.class_key}%"))

        bind = self.db.get_bind()
        dialect = bind.dialect.name if bind is not None else ""
        if dialect == "postgresql":
            if filters.date_from:
                q = q.filter(
                    or_(
                        TeacherExam.schedule_start.is_(None),
                        func.to_char(TeacherExam.schedule_start, "YYYY-MM-DD") >= filters.date_from,
                    )
                )
            if filters.date_to:
                q = q.filter(
                    or_(
                        TeacherExam.schedule_start.is_(None),
                        func.to_char(TeacherExam.schedule_start, "YYYY-MM-DD") <= filters.date_to,
                    )
                )

        q = q.order_by(desc(TeacherExam.updated_at), desc(TeacherExam.created_at))

        total = q.count()
        offset = (page - 1) * page_size
        items = q.offset(offset).limit(page_size).all()
        return items, total

    def get_exam(
        self,
        tenant_id: UUID,
        exam_id: UUID,
        with_questions: bool = True,
        with_sections: bool = True,
    ) -> Optional[TeacherExam]:
        q = self.db.query(TeacherExam).filter(
            TeacherExam.tenant_id == tenant_id,
            TeacherExam.id == exam_id,
        )
        if with_sections:
            q = q.options(joinedload(TeacherExam.sections))
        if with_questions:
            q = q.options(joinedload(TeacherExam.questions))
        return q.first()

    def create_exam(self, exam: TeacherExam) -> TeacherExam:
        self.db.add(exam)
        self.db.commit()
        self.db.refresh(exam)
        return exam

    def update_exam(self, exam: TeacherExam) -> TeacherExam:
        self.db.add(exam)
        self.db.commit()
        self.db.refresh(exam)
        return exam

    def delete_exam(self, exam: TeacherExam) -> None:
        self.db.delete(exam)
        self.db.commit()

    def get_question(
        self,
        tenant_id: UUID,
        exam_id: UUID,
        question_id: UUID,
        question_type: Optional[str] = None,
    ) -> Optional[TeacherExamQuestion]:
        q = (
            self.db.query(TeacherExamQuestion)
            .join(TeacherExam, TeacherExamQuestion.exam_id == TeacherExam.id)
            .filter(
                TeacherExamQuestion.id == question_id,
                TeacherExamQuestion.exam_id == exam_id,
                TeacherExam.tenant_id == tenant_id,
            )
        )
        if question_type:
            q = q.filter(TeacherExamQuestion.question_type == question_type)
        return q.first()

    def replace_all_content(
        self,
        exam: TeacherExam,
        sections: Iterable[TeacherExamSection],
        questions: Iterable[TeacherExamQuestion],
    ) -> TeacherExam:
        self.db.query(TeacherExamSection).filter(TeacherExamSection.exam_id == exam.id).delete(
            synchronize_session=False
        )
        self.db.query(TeacherExamQuestion).filter(TeacherExamQuestion.exam_id == exam.id).delete(
            synchronize_session=False
        )
        self.db.flush()

        for s in sections:
            s.exam_id = exam.id
            self.db.add(s)
        for qq in questions:
            qq.exam_id = exam.id
            self.db.add(qq)

        self.db.flush()
        self.db.refresh(exam)
        self.db.commit()
        return self.get_exam(exam.tenant_id, exam.id, True, True) or exam

    def replace_questions_for_type(
        self,
        exam: TeacherExam,
        question_type: str,
        questions: List[TeacherExamQuestion],
    ) -> TeacherExam:
        self.db.query(TeacherExamQuestion).filter(
            TeacherExamQuestion.exam_id == exam.id,
            TeacherExamQuestion.question_type == question_type,
        ).delete(synchronize_session=False)
        self.db.flush()

        for qq in questions:
            qq.exam_id = exam.id
            self.db.add(qq)

        self.db.flush()
        self.db.commit()
        return self.get_exam(exam.tenant_id, exam.id, True, True) or exam

    def find_generation_run_by_idempotency(
        self,
        exam_id: UUID,
        idempotency_key: str,
    ) -> Optional[TeacherExamGenerationRun]:
        return (
            self.db.query(TeacherExamGenerationRun)
            .filter(
                TeacherExamGenerationRun.exam_id == exam_id,
                TeacherExamGenerationRun.idempotency_key == idempotency_key,
            )
            .order_by(desc(TeacherExamGenerationRun.created_at))
            .first()
        )

    def create_generation_run(self, run: TeacherExamGenerationRun) -> TeacherExamGenerationRun:
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def duplicate_exam(
        self,
        *,
        source: TeacherExam,
        new_id: UUID,
        new_title: str,
        now: datetime,
    ) -> TeacherExam:
        copy = TeacherExam(
            id=new_id,
            tenant_id=source.tenant_id,
            owner_user_id=source.owner_user_id,
            title=new_title,
            subject=source.subject,
            grade=source.grade,
            exam_type=source.exam_type,
            term=source.term,
            international_standard=source.international_standard,
            duration_minutes=source.duration_minutes,
            total_marks=source.total_marks,
            schedule_start=None,
            schedule_end=None,
            class_keys=list(source.class_keys or []),
            status="draft",
            completion_pct=0.0,
            section_target_count=source.section_target_count,
            source_pack_ids=list(source.source_pack_ids or []),
            scope_topics=list(source.scope_topics or []),
            scope_topic_ids=list(source.scope_topic_ids or []),
            scope_refinement=source.scope_refinement,
            topic_summary=source.topic_summary,
            generate_without_sources=bool(source.generate_without_sources),
            paper_config=dict(source.paper_config or {}),
            handout_layout=source.handout_layout,
            student_instructions=source.student_instructions,
            teacher_notes=source.teacher_notes,
            sections_count=source.sections_count,
            mcq_count=source.mcq_count,
            short_count=source.short_count,
            long_count=source.long_count,
            submission_count=0,
            avg_score=None,
            content_version=1,
            created_at=now,
            updated_at=now,
        )
        self.db.add(copy)
        self.db.flush()

        for sec in source.sections or []:
            self.db.add(
                TeacherExamSection(
                    id=uuid4(),
                    exam_id=copy.id,
                    sort_order=sec.sort_order,
                    title=sec.title,
                    marks=sec.marks,
                    description=sec.description,
                )
            )
        for qq in source.questions or []:
            self.db.add(
                TeacherExamQuestion(
                    id=uuid4(),
                    exam_id=copy.id,
                    question_type=qq.question_type,
                    sort_order=qq.sort_order,
                    stem=qq.stem,
                    options=qq.options,
                    subparts=qq.subparts,
                    marks_per=qq.marks_per,
                )
            )
        self.db.commit()
        self.db.refresh(copy)
        return self.get_exam(copy.tenant_id, copy.id, True, True) or copy

    def bulk_reorder_questions(
        self,
        exam: TeacherExam,
        question_type: str,
        order: List[dict],
    ) -> TeacherExam:
        quiz_question_ids = {str(q.id) for q in (exam.questions or []) if q.question_type == question_type}
        order_map: dict[str, int] = {}
        for item in order:
            qid = str(item["id"]) if not isinstance(item["id"], str) else item["id"]
            if qid not in quiz_question_ids:
                continue
            order_map[qid] = int(item["sort_order"])
        for q in exam.questions or []:
            if q.question_type != question_type:
                continue
            qid = str(q.id)
            if qid in order_map:
                q.sort_order = order_map[qid]
                self.db.add(q)
        exam.updated_at = datetime.now(timezone.utc)
        self.db.add(exam)
        self.db.commit()
        self.db.refresh(exam)
        return self.get_exam(exam.tenant_id, exam.id, True, True) or exam

    def add_question(self, exam: TeacherExam, question: TeacherExamQuestion) -> TeacherExam:
        same_type = [q for q in (exam.questions or []) if q.question_type == question.question_type]
        orders = [q.sort_order for q in same_type]
        question.sort_order = (max(orders) + 1) if orders else 0
        question.exam_id = exam.id
        self.db.add(question)
        self.db.flush()
        self.db.commit()
        return self.get_exam(exam.tenant_id, exam.id, True, True) or exam

    def patch_question_row(
        self,
        exam: TeacherExam,
        question: TeacherExamQuestion,
        patch: dict,
    ) -> TeacherExam:
        if "stem" in patch and patch["stem"] is not None:
            question.stem = patch["stem"]
        if "options" in patch:
            question.options = patch["options"]
        if "subparts" in patch:
            question.subparts = patch["subparts"]
        if "marksPer" in patch and patch["marksPer"] is not None:
            question.marks_per = float(patch["marksPer"])
        self.db.add(question)
        exam.updated_at = datetime.now(timezone.utc)
        self.db.add(exam)
        self.db.commit()
        return self.get_exam(exam.tenant_id, exam.id, True, True) or exam

    def delete_question_row(self, exam: TeacherExam, question: TeacherExamQuestion) -> TeacherExam:
        self.db.delete(question)
        self.db.flush()
        exam.updated_at = datetime.now(timezone.utc)
        self.db.add(exam)
        self.db.commit()
        return self.get_exam(exam.tenant_id, exam.id, True, True) or exam
