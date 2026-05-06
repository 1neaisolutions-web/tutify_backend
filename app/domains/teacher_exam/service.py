from __future__ import annotations

import asyncio
import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.domains.auth.models import User
from app.domains.teacher_exam.errors import generation_failed, generation_timeout, not_found, validation_failed
from app.domains.teacher_exam.generation import ExamGenerationService, GeneratedExam
from app.domains.teacher_exam.models import TeacherExam, TeacherExamGenerationRun, TeacherExamQuestion, TeacherExamSection
from app.domains.teacher_exam.repository import ExamListFilters, TeacherExamRepository
from app.domains.teacher_exam.retrieval import ExamRetrievalService
from app.domains.teacher_exam.schemas import ExamPaperConfigSchema

logger = get_logger(__name__)


def _topic_summary(scope_topics: List[str], scope_refinement: Optional[str]) -> str:
    base = " · ".join([t for t in scope_topics if t and t.strip()])
    if scope_refinement and scope_refinement.strip():
        return f"{base} — {scope_refinement.strip()}" if base else scope_refinement.strip()
    return base or "General scope"


def _source_summary(exam: TeacherExam) -> Optional[str]:
    if exam.generate_without_sources:
        return "Generation without catalog retrieval (grounding off)"
    pack_count = len(exam.source_pack_ids or [])
    topic_count = len(exam.scope_topics or [])
    refine = " · scope hint applied" if (exam.scope_refinement or "").strip() else ""
    return f"Catalog retrieval · {pack_count} source{'s' if pack_count != 1 else ''} · {topic_count} topic strand{'s' if topic_count != 1 else ''}{refine}"


def compute_total_marks_from_paper(paper: Dict[str, Any]) -> float:
    p = paper or {}
    obj_count = int(p.get("objCount") or 0)
    obj_marks = float(p.get("objMarksPer") or 0)
    part_a = obj_count * obj_marks

    short_rule = p.get("shortRule") or "all"
    short_marks = float(p.get("shortMarksPer") or 0)
    short_eff = int(p.get("shortN") or 0) if short_rule == "pickNM" else int(p.get("shortCount") or 0)
    part_b1 = short_eff * short_marks

    long_rule = p.get("longRule") or "all"
    long_marks = float(p.get("longMarksPer") or 0)
    long_eff = int(p.get("longN") or 0) if long_rule == "pickNM" else int(p.get("longCount") or 0)
    part_b2 = long_eff * long_marks

    return round(part_a + part_b1 + part_b2, 2)


def _paper_as_dict(paper: Any) -> Dict[str, Any]:
    if isinstance(paper, dict):
        return dict(paper)
    if hasattr(paper, "model_dump"):
        return paper.model_dump()
    return ExamPaperConfigSchema().model_dump()


class TeacherExamService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = TeacherExamRepository(db)
        self.retrieval = ExamRetrievalService(db)
        self.generator = ExamGenerationService()

    def _recalc_counts(self, exam: TeacherExam) -> None:
        exam.sections_count = len(exam.sections or [])
        exam.mcq_count = len([q for q in exam.questions or [] if q.question_type == "mcq"])
        exam.short_count = len([q for q in exam.questions or [] if q.question_type == "short"])
        exam.long_count = len([q for q in exam.questions or [] if q.question_type == "long"])
        exam.total_marks = compute_total_marks_from_paper(exam.paper_config or {})

    def list_exams(
        self,
        *,
        current_user: User,
        filters: ExamListFilters,
        page: int,
        page_size: int,
    ) -> Tuple[List[TeacherExam], int]:
        return self.repo.list_exams(current_user.tenant_id, filters, page=page, page_size=page_size)

    def get_exam(self, *, current_user: User, exam_id: UUID) -> TeacherExam:
        exam = self.repo.get_exam(current_user.tenant_id, exam_id, with_questions=True, with_sections=True)
        if not exam:
            raise not_found()
        return exam

    def create_exam(self, *, current_user: User, payload: Dict[str, Any]) -> TeacherExam:
        now = datetime.now(timezone.utc)
        paper = _paper_as_dict(payload.get("paper"))
        exam = TeacherExam(
            id=uuid4(),
            tenant_id=current_user.tenant_id,
            owner_user_id=current_user.id,
            title=payload["title"],
            subject=payload["subject"],
            grade=payload["grade"],
            exam_type=payload.get("examType") or "Unit test",
            term=payload.get("term") or "Term 1",
            international_standard=payload.get("internationalStandard") or "Standard",
            duration_minutes=int(payload.get("durationMinutes") or 60),
            total_marks=compute_total_marks_from_paper(paper),
            schedule_start=payload.get("scheduleStart"),
            schedule_end=payload.get("scheduleEnd"),
            class_keys=list(payload.get("classes") or []),
            status=payload.get("status") or "draft",
            completion_pct=0.0,
            section_target_count=int(payload.get("sectionTargetCount") or 4),
            source_pack_ids=list(payload.get("sourceBookIds") or []),
            scope_topics=list(payload.get("scopeTopics") or []),
            scope_refinement=payload.get("scopeRefinement"),
            topic_summary=_topic_summary(list(payload.get("scopeTopics") or []), payload.get("scopeRefinement")),
            generate_without_sources=bool(payload.get("generateWithoutSources") or False),
            paper_config=paper,
            handout_layout=payload.get("handoutLayout"),
            student_instructions=payload.get("studentInstructions"),
            teacher_notes=payload.get("teacherNotes"),
            sections_count=0,
            mcq_count=0,
            short_count=0,
            long_count=0,
            submission_count=0,
            avg_score=None,
            content_version=1,
            created_at=now,
            updated_at=now,
        )
        self._recalc_counts(exam)
        return self.repo.create_exam(exam)

    def patch_exam(self, *, current_user: User, exam_id: UUID, patch: Dict[str, Any]) -> TeacherExam:
        exam = self.repo.get_exam(current_user.tenant_id, exam_id, with_questions=True, with_sections=True)
        if not exam:
            raise not_found()

        mapping = [
            ("title", "title"),
            ("subject", "subject"),
            ("grade", "grade"),
            ("examType", "exam_type"),
            ("term", "term"),
            ("internationalStandard", "international_standard"),
            ("durationMinutes", "duration_minutes"),
            ("scheduleStart", "schedule_start"),
            ("scheduleEnd", "schedule_end"),
            ("classes", "class_keys"),
            ("status", "status"),
            ("completionPct", "completion_pct"),
            ("sectionTargetCount", "section_target_count"),
            ("sourceBookIds", "source_pack_ids"),
            ("scopeTopics", "scope_topics"),
            ("scopeRefinement", "scope_refinement"),
            ("generateWithoutSources", "generate_without_sources"),
            ("studentInstructions", "student_instructions"),
            ("teacherNotes", "teacher_notes"),
            ("handoutLayout", "handout_layout"),
        ]
        for json_key, attr in mapping:
            if json_key in patch and patch[json_key] is not None:
                setattr(exam, attr, patch[json_key])

        if "paper" in patch and patch["paper"] is not None:
            exam.paper_config = _paper_as_dict(patch["paper"])

        if "scopeTopics" in patch or "scopeRefinement" in patch:
            exam.topic_summary = _topic_summary(list(exam.scope_topics or []), exam.scope_refinement)

        exam.updated_at = datetime.now(timezone.utc)
        self._recalc_counts(exam)
        return self.repo.update_exam(exam)

    def delete_exam(self, *, current_user: User, exam_id: UUID) -> None:
        exam = self.repo.get_exam(current_user.tenant_id, exam_id, with_questions=False, with_sections=False)
        if not exam:
            raise not_found()
        self.repo.delete_exam(exam)

    def duplicate_exam(self, *, current_user: User, exam_id: UUID) -> TeacherExam:
        exam = self.repo.get_exam(current_user.tenant_id, exam_id, with_questions=True, with_sections=True)
        if not exam:
            raise not_found()
        now = datetime.now(timezone.utc)
        return self.repo.duplicate_exam(source=exam, new_id=uuid4(), new_title=f"{exam.title} (copy)", now=now)

    def _generated_to_entities(self, exam_id: UUID, gen: GeneratedExam) -> Tuple[List[TeacherExamSection], List[TeacherExamQuestion]]:
        sections: List[TeacherExamSection] = []
        for i, s in enumerate(gen.sections):
            sections.append(
                TeacherExamSection(
                    id=uuid4(),
                    exam_id=exam_id,
                    sort_order=i,
                    title=s.title,
                    marks=float(s.marks),
                    description=s.description or None,
                )
            )
        questions: List[TeacherExamQuestion] = []
        for i, m in enumerate(gen.mcqs):
            questions.append(
                TeacherExamQuestion(
                    id=uuid4(),
                    exam_id=exam_id,
                    question_type="mcq",
                    sort_order=i,
                    stem=m.stem,
                    options=list(m.options),
                    subparts=None,
                    marks_per=float(m.marks_per),
                )
            )
        for i, s in enumerate(gen.shorts):
            questions.append(
                TeacherExamQuestion(
                    id=uuid4(),
                    exam_id=exam_id,
                    question_type="short",
                    sort_order=i,
                    stem=s.stem,
                    options=None,
                    subparts=None,
                    marks_per=float(s.marks_per),
                )
            )
        for i, lg in enumerate(gen.longs):
            questions.append(
                TeacherExamQuestion(
                    id=uuid4(),
                    exam_id=exam_id,
                    question_type="long",
                    sort_order=i,
                    stem=lg.stem,
                    options=None,
                    subparts=list(lg.subparts),
                    marks_per=float(lg.marks_per),
                )
            )
        return sections, questions

    async def generate_full_exam(
        self,
        *,
        current_user: User,
        exam_id: UUID,
        req: Dict[str, Any],
        idempotency_key: Optional[str],
    ) -> Tuple[TeacherExamGenerationRun, TeacherExam, List[str]]:
        exam = self.repo.get_exam(current_user.tenant_id, exam_id, with_questions=True, with_sections=True)
        if not exam:
            raise not_found()

        if idempotency_key:
            prior = self.repo.find_generation_run_by_idempotency(exam.id, idempotency_key)
            if prior and prior.status == "completed":
                fresh = self.repo.get_exam(current_user.tenant_id, exam_id, True, True)
                if fresh:
                    return prior, fresh, list(prior.retrieval_warnings or [])

        difficulty = req.get("difficulty")
        teacher_notes = req.get("teacherNotes") or exam.teacher_notes
        scope = req.get("regenerateScope") or "all"

        paper = exam.paper_config or {}
        topic_label = exam.topic_summary or _topic_summary(list(exam.scope_topics or []), exam.scope_refinement)

        context_text = ""
        citations: List[Dict[str, str]] = []
        retrieval_warnings: List[str] = []
        retrieval_meta: Dict[str, Any] = {}

        if not exam.generate_without_sources:
            try:
                pack_ids = [UUID(str(x)) for x in (exam.source_pack_ids or []) if x]
            except Exception:
                raise validation_failed("Invalid pack IDs on exam.")
            rr = self.retrieval.retrieve(
                tenant_id=current_user.tenant_id,
                pack_ids=pack_ids,
                topics=list(exam.scope_topics or []),
                refinement=exam.scope_refinement,
                max_chunks=18,
            )
            context_text = rr.context_text
            citations = rr.citations
            retrieval_warnings.extend(rr.warnings)
            retrieval_meta = rr.metadata
        else:
            retrieval_warnings.append("Generation without sources (grounding off).")

        timeout_s = float(getattr(settings, "QUIZ_GENERATION_TIMEOUT_SECONDS", 180.0))
        input_payload = {
            "exam_id": str(exam.id),
            "subject": exam.subject,
            "grade": exam.grade,
            "topic": topic_label,
            "difficulty": difficulty,
            "scope": scope,
            "teacherNotes": teacher_notes or "",
            "grounded": not exam.generate_without_sources,
        }
        input_hash = self.generator.build_input_hash(input_payload)

        prior_stems: List[str] = []
        for q in exam.questions or []:
            if q and getattr(q, "stem", None):
                prior_stems.append(str(q.stem))

        async def _run_generation() -> Tuple[GeneratedExam, List[str], Dict[str, Any]]:
            gen = await self.generator.generate_full_exam(
                subject=exam.subject,
                grade=exam.grade,
                topic_label=topic_label,
                international_standard=exam.international_standard,
                paper_config=paper,
                section_target_count=int(exam.section_target_count or 4),
                difficulty=difficulty if isinstance(difficulty, str) else None,
                teacher_notes=teacher_notes,
                retrieved_chunks=context_text,
                avoid_question_stems=prior_stems or None,
            )
            meta = {"model_used": "exam_llm"}
            return gen, gen.warnings, meta

        try:
            gen, gen_warnings, gen_meta = await asyncio.wait_for(_run_generation(), timeout=timeout_s)
        except asyncio.TimeoutError as e:
            run = TeacherExamGenerationRun(
                exam_id=exam.id,
                scope=scope,
                status="failed",
                error_code="GENERATION_TIMEOUT",
                error_message=f"Timed out after {timeout_s}s",
                input_hash=input_hash,
                idempotency_key=idempotency_key,
                retrieval_warnings=retrieval_warnings,
                retrieval_metadata={"citations": citations, **retrieval_meta},
                llm_model=None,
            )
            self.repo.create_generation_run(run)
            raise generation_timeout() from e
        except Exception as e:
            run = TeacherExamGenerationRun(
                exam_id=exam.id,
                scope=scope,
                status="failed",
                error_code="GENERATION_FAILED",
                error_message=str(e)[:1000],
                input_hash=input_hash,
                idempotency_key=idempotency_key,
                retrieval_warnings=retrieval_warnings,
                retrieval_metadata={"citations": citations, **retrieval_meta},
                llm_model=None,
            )
            self.repo.create_generation_run(run)
            raise generation_failed("Exam generation failed") from e

        warnings = retrieval_warnings + gen_warnings
        llm_model = gen_meta.get("model_used")

        if scope == "all":
            sections, questions = self._generated_to_entities(exam.id, gen)
            exam = self.repo.replace_all_content(exam, sections, questions)
        elif scope == "mcq":
            mcq_rows = [
                TeacherExamQuestion(
                    id=uuid4(),
                    exam_id=exam.id,
                    question_type="mcq",
                    sort_order=i,
                    stem=m.stem,
                    options=list(m.options),
                    subparts=None,
                    marks_per=float(m.marks_per),
                )
                for i, m in enumerate(gen.mcqs)
            ]
            exam = self.repo.replace_questions_for_type(exam, "mcq", mcq_rows)
        elif scope == "short":
            short_rows = [
                TeacherExamQuestion(
                    id=uuid4(),
                    exam_id=exam.id,
                    question_type="short",
                    sort_order=i,
                    stem=s.stem,
                    options=None,
                    subparts=None,
                    marks_per=float(s.marks_per),
                )
                for i, s in enumerate(gen.shorts)
            ]
            exam = self.repo.replace_questions_for_type(exam, "short", short_rows)
        elif scope == "long":
            long_rows = [
                TeacherExamQuestion(
                    id=uuid4(),
                    exam_id=exam.id,
                    question_type="long",
                    sort_order=i,
                    stem=lg.stem,
                    options=None,
                    subparts=list(lg.subparts),
                    marks_per=float(lg.marks_per),
                )
                for i, lg in enumerate(gen.longs)
            ]
            exam = self.repo.replace_questions_for_type(exam, "long", long_rows)
        else:
            raise validation_failed("Invalid regenerate scope.")

        exam = self.repo.get_exam(current_user.tenant_id, exam.id, True, True) or exam
        self._recalc_counts(exam)
        exam.topic_summary = exam.topic_summary or topic_label
        exam.teacher_notes = teacher_notes or exam.teacher_notes
        exam.content_version = int(exam.content_version or 1) + 1
        exam.updated_at = datetime.now(timezone.utc)
        exam = self.repo.update_exam(exam)

        run = TeacherExamGenerationRun(
            exam_id=exam.id,
            scope=scope,
            status="completed",
            input_hash=input_hash,
            idempotency_key=idempotency_key,
            retrieval_warnings=warnings,
            retrieval_metadata={"citations": citations, **retrieval_meta, "llm": gen_meta},
            llm_model=str(llm_model) if llm_model else None,
        )
        run = self.repo.create_generation_run(run)

        logger.info(
            "exam_generated",
            extra={
                "tenant_id": str(current_user.tenant_id),
                "exam_id": str(exam.id),
                "scope": scope,
                "content_version": exam.content_version,
            },
        )
        return run, exam, warnings

    def add_mcq(self, *, current_user: User, exam_id: UUID, payload: Dict[str, Any]) -> TeacherExam:
        exam = self.repo.get_exam(current_user.tenant_id, exam_id, True, True)
        if not exam:
            raise not_found()
        paper = dict(exam.paper_config or {})
        paper["objCount"] = min(100, int(paper.get("objCount") or 0) + 1)
        exam.paper_config = paper
        exam.updated_at = datetime.now(timezone.utc)
        exam = self.repo.update_exam(exam)
        exam = self.repo.get_exam(current_user.tenant_id, exam.id, True, True) or exam
        q = TeacherExamQuestion(
            id=uuid4(),
            exam_id=exam.id,
            question_type="mcq",
            sort_order=0,
            stem=payload["stem"],
            options=list(payload.get("options") or []),
            subparts=None,
            marks_per=float(payload.get("marksPer") or 1.0),
        )
        exam = self.repo.add_question(exam, q)
        self._recalc_counts(exam)
        exam.updated_at = datetime.now(timezone.utc)
        return self.repo.update_exam(exam)

    def patch_mcq(self, *, current_user: User, exam_id: UUID, question_id: UUID, patch: Dict[str, Any]) -> TeacherExam:
        exam = self.repo.get_exam(current_user.tenant_id, exam_id, True, True)
        if not exam:
            raise not_found()
        q = self.repo.get_question(current_user.tenant_id, exam_id, question_id, "mcq")
        if not q:
            raise not_found("Question not found")
        return self.repo.patch_question_row(exam, q, patch)

    def delete_mcq(self, *, current_user: User, exam_id: UUID, question_id: UUID) -> TeacherExam:
        exam = self.repo.get_exam(current_user.tenant_id, exam_id, True, True)
        if not exam:
            raise not_found()
        q = self.repo.get_question(current_user.tenant_id, exam_id, question_id, "mcq")
        if not q:
            raise not_found("Question not found")
        paper = dict(exam.paper_config or {})
        paper["objCount"] = max(1, int(paper.get("objCount") or 1) - 1)
        exam.paper_config = paper
        exam.updated_at = datetime.now(timezone.utc)
        exam = self.repo.update_exam(exam)
        exam = self.repo.delete_question_row(exam, q)
        self._recalc_counts(exam)
        exam.updated_at = datetime.now(timezone.utc)
        return self.repo.update_exam(exam)

    def add_short(self, *, current_user: User, exam_id: UUID, payload: Dict[str, Any]) -> TeacherExam:
        exam = self.repo.get_exam(current_user.tenant_id, exam_id, True, True)
        if not exam:
            raise not_found()
        paper = dict(exam.paper_config or {})
        if (paper.get("shortRule") or "pickNM") == "pickNM":
            paper["shortM"] = min(20, int(paper.get("shortM") or 0) + 1)
        else:
            paper["shortCount"] = min(20, int(paper.get("shortCount") or 0) + 1)
        exam.paper_config = paper
        exam.updated_at = datetime.now(timezone.utc)
        exam = self.repo.update_exam(exam)
        exam = self.repo.get_exam(current_user.tenant_id, exam.id, True, True) or exam
        q = TeacherExamQuestion(
            id=uuid4(),
            exam_id=exam.id,
            question_type="short",
            sort_order=0,
            stem=payload["stem"],
            options=None,
            subparts=None,
            marks_per=float(payload.get("marksPer") or 5.0),
        )
        exam = self.repo.add_question(exam, q)
        self._recalc_counts(exam)
        exam.updated_at = datetime.now(timezone.utc)
        return self.repo.update_exam(exam)

    def patch_short(self, *, current_user: User, exam_id: UUID, question_id: UUID, patch: Dict[str, Any]) -> TeacherExam:
        exam = self.repo.get_exam(current_user.tenant_id, exam_id, True, True)
        if not exam:
            raise not_found()
        q = self.repo.get_question(current_user.tenant_id, exam_id, question_id, "short")
        if not q:
            raise not_found("Question not found")
        return self.repo.patch_question_row(exam, q, patch)

    def delete_short(self, *, current_user: User, exam_id: UUID, question_id: UUID) -> TeacherExam:
        exam = self.repo.get_exam(current_user.tenant_id, exam_id, True, True)
        if not exam:
            raise not_found()
        q = self.repo.get_question(current_user.tenant_id, exam_id, question_id, "short")
        if not q:
            raise not_found("Question not found")
        paper = dict(exam.paper_config or {})
        if (paper.get("shortRule") or "pickNM") == "pickNM":
            paper["shortM"] = max(2, int(paper.get("shortM") or 2) - 1)
            sn = int(paper.get("shortN") or 0)
            sm = int(paper.get("shortM") or 0)
            if sn >= sm:
                paper["shortN"] = max(0, sm - 1)
        else:
            paper["shortCount"] = max(1, int(paper.get("shortCount") or 1) - 1)
        exam.paper_config = paper
        exam.updated_at = datetime.now(timezone.utc)
        exam = self.repo.update_exam(exam)
        exam = self.repo.delete_question_row(exam, q)
        self._recalc_counts(exam)
        exam.updated_at = datetime.now(timezone.utc)
        return self.repo.update_exam(exam)

    def add_long(self, *, current_user: User, exam_id: UUID, payload: Dict[str, Any]) -> TeacherExam:
        exam = self.repo.get_exam(current_user.tenant_id, exam_id, True, True)
        if not exam:
            raise not_found()
        paper = dict(exam.paper_config or {})
        if (paper.get("longRule") or "pickNM") == "pickNM":
            paper["longM"] = min(10, int(paper.get("longM") or 0) + 1)
        else:
            paper["longCount"] = min(10, int(paper.get("longCount") or 0) + 1)
        exam.paper_config = paper
        exam.updated_at = datetime.now(timezone.utc)
        exam = self.repo.update_exam(exam)
        exam = self.repo.get_exam(current_user.tenant_id, exam.id, True, True) or exam
        q = TeacherExamQuestion(
            id=uuid4(),
            exam_id=exam.id,
            question_type="long",
            sort_order=0,
            stem=payload["stem"],
            options=None,
            subparts=list(payload.get("subparts") or []),
            marks_per=float(payload.get("marksPer") or 10.0),
        )
        exam = self.repo.add_question(exam, q)
        self._recalc_counts(exam)
        exam.updated_at = datetime.now(timezone.utc)
        return self.repo.update_exam(exam)

    def patch_long(self, *, current_user: User, exam_id: UUID, question_id: UUID, patch: Dict[str, Any]) -> TeacherExam:
        exam = self.repo.get_exam(current_user.tenant_id, exam_id, True, True)
        if not exam:
            raise not_found()
        q = self.repo.get_question(current_user.tenant_id, exam_id, question_id, "long")
        if not q:
            raise not_found("Question not found")
        return self.repo.patch_question_row(exam, q, patch)

    def delete_long(self, *, current_user: User, exam_id: UUID, question_id: UUID) -> TeacherExam:
        exam = self.repo.get_exam(current_user.tenant_id, exam_id, True, True)
        if not exam:
            raise not_found()
        q = self.repo.get_question(current_user.tenant_id, exam_id, question_id, "long")
        if not q:
            raise not_found("Question not found")
        paper = dict(exam.paper_config or {})
        if (paper.get("longRule") or "pickNM") == "pickNM":
            paper["longM"] = max(2, int(paper.get("longM") or 2) - 1)
            ln = int(paper.get("longN") or 0)
            lm = int(paper.get("longM") or 0)
            if ln >= lm:
                paper["longN"] = max(0, lm - 1)
        else:
            paper["longCount"] = max(1, int(paper.get("longCount") or 1) - 1)
        exam.paper_config = paper
        exam.updated_at = datetime.now(timezone.utc)
        exam = self.repo.update_exam(exam)
        exam = self.repo.delete_question_row(exam, q)
        self._recalc_counts(exam)
        exam.updated_at = datetime.now(timezone.utc)
        return self.repo.update_exam(exam)

    def reorder_questions(
        self,
        *,
        current_user: User,
        exam_id: UUID,
        question_type: str,
        order: List[dict],
    ) -> TeacherExam:
        exam = self.repo.get_exam(current_user.tenant_id, exam_id, True, True)
        if not exam:
            raise not_found()
        return self.repo.bulk_reorder_questions(exam, question_type, order)

    async def regenerate_mcq(self, *, current_user: User, exam_id: UUID, question_id: UUID) -> TeacherExam:
        exam = self.repo.get_exam(current_user.tenant_id, exam_id, True, True)
        if not exam:
            raise not_found()
        q = self.repo.get_question(current_user.tenant_id, exam_id, question_id, "mcq")
        if not q:
            raise not_found("Question not found")

        topic_label = exam.topic_summary or _topic_summary(list(exam.scope_topics or []), exam.scope_refinement)
        context_text = ""
        if not exam.generate_without_sources:
            try:
                pack_ids = [UUID(str(x)) for x in (exam.source_pack_ids or []) if x]
            except Exception:
                raise validation_failed("Invalid pack IDs on exam.")
            rr = self.retrieval.retrieve(
                tenant_id=current_user.tenant_id,
                pack_ids=pack_ids,
                topics=list(exam.scope_topics or []),
                refinement=exam.scope_refinement,
                max_chunks=18,
            )
            context_text = rr.context_text

        timeout_s = float(getattr(settings, "QUIZ_GENERATION_TIMEOUT_SECONDS", 180.0))
        try:
            gen = await asyncio.wait_for(
                self.generator.regenerate_mcq(
                    subject=exam.subject,
                    grade=exam.grade,
                    topic_label=topic_label,
                    paper_config=exam.paper_config or {},
                    difficulty=None,
                    retrieved_chunks=context_text,
                    marks_per=float(q.marks_per),
                    seed=random.randint(0, 1_000_000),
                    previous_stem=str(q.stem or ""),
                    previous_options=list(q.options) if q.options is not None else None,
                ),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError as e:
            raise generation_timeout() from e
        except Exception as e:
            raise generation_failed("MCQ regeneration failed") from e

        patch = {"stem": gen.stem, "options": list(gen.options), "marksPer": gen.marks_per}
        return self.repo.patch_question_row(exam, q, patch)

    async def regenerate_short(self, *, current_user: User, exam_id: UUID, question_id: UUID) -> TeacherExam:
        exam = self.repo.get_exam(current_user.tenant_id, exam_id, True, True)
        if not exam:
            raise not_found()
        q = self.repo.get_question(current_user.tenant_id, exam_id, question_id, "short")
        if not q:
            raise not_found("Question not found")

        topic_label = exam.topic_summary or _topic_summary(list(exam.scope_topics or []), exam.scope_refinement)
        context_text = ""
        if not exam.generate_without_sources:
            try:
                pack_ids = [UUID(str(x)) for x in (exam.source_pack_ids or []) if x]
            except Exception:
                raise validation_failed("Invalid pack IDs on exam.")
            rr = self.retrieval.retrieve(
                tenant_id=current_user.tenant_id,
                pack_ids=pack_ids,
                topics=list(exam.scope_topics or []),
                refinement=exam.scope_refinement,
                max_chunks=18,
            )
            context_text = rr.context_text

        timeout_s = float(getattr(settings, "QUIZ_GENERATION_TIMEOUT_SECONDS", 180.0))
        try:
            gen = await asyncio.wait_for(
                self.generator.regenerate_short(
                    subject=exam.subject,
                    grade=exam.grade,
                    topic_label=topic_label,
                    marks_per=float(q.marks_per),
                    difficulty=None,
                    retrieved_chunks=context_text,
                    seed=random.randint(0, 1_000_000),
                    previous_stem=str(q.stem or ""),
                ),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError as e:
            raise generation_timeout() from e
        except Exception as e:
            raise generation_failed("Short regeneration failed") from e

        patch = {"stem": gen.stem, "marksPer": gen.marks_per}
        return self.repo.patch_question_row(exam, q, patch)

    async def regenerate_long(self, *, current_user: User, exam_id: UUID, question_id: UUID) -> TeacherExam:
        exam = self.repo.get_exam(current_user.tenant_id, exam_id, True, True)
        if not exam:
            raise not_found()
        q = self.repo.get_question(current_user.tenant_id, exam_id, question_id, "long")
        if not q:
            raise not_found("Question not found")

        topic_label = exam.topic_summary or _topic_summary(list(exam.scope_topics or []), exam.scope_refinement)
        context_text = ""
        if not exam.generate_without_sources:
            try:
                pack_ids = [UUID(str(x)) for x in (exam.source_pack_ids or []) if x]
            except Exception:
                raise validation_failed("Invalid pack IDs on exam.")
            rr = self.retrieval.retrieve(
                tenant_id=current_user.tenant_id,
                pack_ids=pack_ids,
                topics=list(exam.scope_topics or []),
                refinement=exam.scope_refinement,
                max_chunks=18,
            )
            context_text = rr.context_text

        timeout_s = float(getattr(settings, "QUIZ_GENERATION_TIMEOUT_SECONDS", 180.0))
        try:
            gen = await asyncio.wait_for(
                self.generator.regenerate_long(
                    subject=exam.subject,
                    grade=exam.grade,
                    topic_label=topic_label,
                    paper_config=exam.paper_config or {},
                    difficulty=None,
                    retrieved_chunks=context_text,
                    marks_per=float(q.marks_per),
                    seed=random.randint(0, 1_000_000),
                    previous_stem=str(q.stem or ""),
                    previous_subparts=list(q.subparts) if q.subparts is not None else None,
                ),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError as e:
            raise generation_timeout() from e
        except Exception as e:
            raise generation_failed("Long regeneration failed") from e

        patch = {"stem": gen.stem, "subparts": list(gen.subparts), "marksPer": gen.marks_per}
        return self.repo.patch_question_row(exam, q, patch)
