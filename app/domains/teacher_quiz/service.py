from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.domains.auth.models import User
from app.domains.content_ingestion.models import DocumentTopic
from app.domains.content_ingestion.scope_query import validate_scope_topic_ids_for_tenant
from app.domains.content_ingestion.topic_scope import RetrievalScopeError
from app.domains.teacher_quiz.errors import QuizError, generation_failed, not_found, retrieval_scope_failed, validation_failed
from app.domains.teacher_quiz.generation import QuizGenerationService
from app.domains.teacher_quiz.models import TeacherQuiz, TeacherQuizGenerationRun, TeacherQuizQuestion
from app.domains.teacher_quiz.repository import QuizListFilters, TeacherQuizRepository
from app.domains.teacher_quiz.retrieval import QuizRetrievalService

logger = get_logger(__name__)


def _topic_summary(scope_topics: List[str], scope_refinement: Optional[str]) -> str:
    base = " · ".join([t for t in scope_topics if t and t.strip()])
    if scope_refinement and scope_refinement.strip():
        return f"{base} — {scope_refinement.strip()}" if base else scope_refinement.strip()
    return base or "General scope"


def _parse_scope_topic_ids(raw: Optional[List[Any]]) -> List[UUID]:
    out: List[UUID] = []
    for item in raw or []:
        try:
            out.append(UUID(str(item)))
        except (ValueError, TypeError):
            continue
    return out


def _compute_max_chunks(question_count: int) -> int:
    per_q = int(getattr(settings, "QUIZ_MAX_CHUNKS_PER_QUESTION", 3))
    cap = int(getattr(settings, "QUIZ_MAX_CHUNKS_CAP", 30))
    return min(cap, max(6, question_count * per_q))


def _validate_sourced_scope(
    db: Session,
    *,
    tenant_id: UUID,
    generate_without_sources: bool,
    source_pack_ids: List[Any],
    scope_topic_ids: Optional[List[Any]],
) -> None:
    if generate_without_sources:
        return
    strict = bool(getattr(settings, "QUIZ_STRICT_SCOPE_ONLY", True))
    if not strict:
        return
    ids = _parse_scope_topic_ids(scope_topic_ids)
    if not ids:
        raise validation_failed("Select at least one chapter or topic.")
    try:
        pack_ids = [UUID(str(x)) for x in (source_pack_ids or []) if x]
    except (ValueError, TypeError) as e:
        raise validation_failed("Invalid pack IDs on quiz.") from e
    if not pack_ids:
        raise validation_failed("Select at least one source book.")
    valid = validate_scope_topic_ids_for_tenant(
        db, tenant_id=tenant_id, pack_ids=pack_ids, topic_ids=ids
    )
    if len(valid) != len(ids):
        raise validation_failed("One or more selected topics are invalid for the chosen books.")


def _allowed_topic_titles(db: Session, topic_ids: List[UUID]) -> List[str]:
    if not topic_ids:
        return []
    rows = (
        db.query(DocumentTopic.display_title)
        .filter(DocumentTopic.id.in_(topic_ids))
        .all()
    )
    return [r[0] for r in rows if r[0]]


def _compute_total_marks(questions: List[TeacherQuizQuestion]) -> float:
    return round(sum(float(q.points or 0.0) for q in questions) * 10) / 10.0


class TeacherQuizService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = TeacherQuizRepository(db)
        self.retrieval = QuizRetrievalService(db)
        self.generator = QuizGenerationService()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def list_quizzes(
        self,
        *,
        current_user: User,
        filters: QuizListFilters,
        page: int,
        page_size: int,
    ) -> Tuple[List[TeacherQuiz], int]:
        return self.repo.list_quizzes(current_user.tenant_id, filters, page=page, page_size=page_size,
                                      owner_user_id=current_user.id)

    def get_quiz(self, *, current_user: User, quiz_id: UUID) -> TeacherQuiz:
        quiz = self.repo.get_quiz(current_user.tenant_id, quiz_id, with_questions=True)
        if not quiz:
            raise not_found()
        return quiz

    def create_quiz(self, *, current_user: User, payload: Dict[str, Any]) -> TeacherQuiz:
        _validate_sourced_scope(
            self.db,
            tenant_id=current_user.tenant_id,
            generate_without_sources=bool(payload.get("generateWithoutSources") or False),
            source_pack_ids=list(payload.get("sourceBookIds") or []),
            scope_topic_ids=list(payload.get("scopeTopicIds") or []),
        )
        now = datetime.now(timezone.utc)
        quiz = TeacherQuiz(
            id=uuid4(),
            tenant_id=current_user.tenant_id,
            owner_user_id=current_user.id,
            title=payload["title"],
            subject=payload["subject"],
            grade=payload["grade"],
            class_keys=list(payload.get("classes") or []),
            time_limit_minutes=int(payload.get("timeLimitMinutes") or 30),
            student_instructions=payload.get("studentInstructions"),
            teacher_notes=payload.get("teacherNotes"),
            status=payload.get("status") or "draft",
            assigned_at=payload.get("assignedAt"),
            due_at=payload.get("dueAt"),
            source_pack_ids=list(payload.get("sourceBookIds") or []),
            scope_topics=list(payload.get("scopeTopics") or []),
            scope_topic_ids=list(payload.get("scopeTopicIds") or []),
            scope_book_ids=payload.get("scopeBookIds"),
            scope_refinement=payload.get("scopeRefinement"),
            topic_summary=_topic_summary(list(payload.get("scopeTopics") or []), payload.get("scopeRefinement")),
            generate_without_sources=bool(payload.get("generateWithoutSources") or False),
            difficulty=payload.get("difficulty"),
            shuffle_questions=bool(payload.get("shuffleQuestions", True)),
            shuffle_answers=bool(payload.get("shuffleAnswers", True)),
            negative_marking=bool(payload.get("negativeMarking", False)),
            handout_layout=payload.get("handoutLayout"),
            questions_count=0,
            total_marks=0.0,
            submission_count=0,
            avg_score=0.0,
            content_version=1,
            created_at=now,
            updated_at=now,
        )
        return self.repo.create_quiz(quiz)

    def patch_quiz(self, *, current_user: User, quiz_id: UUID, patch: Dict[str, Any]) -> TeacherQuiz:
        quiz = self.repo.get_quiz(current_user.tenant_id, quiz_id, with_questions=True)
        if not quiz:
            raise not_found()

        # Update allowed fields
        for key, attr in [
            ("title", "title"),
            ("subject", "subject"),
            ("grade", "grade"),
            ("classes", "class_keys"),
            ("timeLimitMinutes", "time_limit_minutes"),
            ("studentInstructions", "student_instructions"),
            ("teacherNotes", "teacher_notes"),
            ("status", "status"),
            ("assignedAt", "assigned_at"),
            ("dueAt", "due_at"),
            ("sourceBookIds", "source_pack_ids"),
            ("scopeTopics", "scope_topics"),
            ("scopeTopicIds", "scope_topic_ids"),
            ("scopeBookIds", "scope_book_ids"),
            ("scopeRefinement", "scope_refinement"),
            ("generateWithoutSources", "generate_without_sources"),
            ("difficulty", "difficulty"),
            ("shuffleQuestions", "shuffle_questions"),
            ("shuffleAnswers", "shuffle_answers"),
            ("negativeMarking", "negative_marking"),
            ("handoutLayout", "handout_layout"),
        ]:
            if key in patch and patch[key] is not None:
                setattr(quiz, attr, patch[key])

        if "scopeTopics" in patch or "scopeRefinement" in patch:
            quiz.topic_summary = _topic_summary(list(quiz.scope_topics or []), quiz.scope_refinement)

        quiz.updated_at = datetime.now(timezone.utc)
        return self.repo.update_quiz(quiz)

    def delete_quiz(self, *, current_user: User, quiz_id: UUID) -> None:
        quiz = self.repo.get_quiz(current_user.tenant_id, quiz_id, with_questions=False)
        if not quiz:
            raise not_found()
        self.repo.delete_quiz(quiz)

    def duplicate_quiz(self, *, current_user: User, quiz_id: UUID) -> TeacherQuiz:
        quiz = self.repo.get_quiz(current_user.tenant_id, quiz_id, with_questions=True)
        if not quiz:
            raise not_found()
        now = datetime.now(timezone.utc)
        return self.repo.duplicate_quiz(
            source=quiz,
            new_id=uuid4(),
            new_title=f"{quiz.title} (copy)",
            now=now,
        )

    # ------------------------------------------------------------------
    # Individual question CRUD
    # ------------------------------------------------------------------

    def add_question(
        self,
        *,
        current_user: User,
        quiz_id: UUID,
        payload: Dict[str, Any],
    ) -> TeacherQuiz:
        from uuid import uuid4 as _uuid4

        quiz = self.repo.get_quiz(current_user.tenant_id, quiz_id, with_questions=True)
        if not quiz:
            raise not_found()
        extra: Dict[str, Any] = {}
        if payload.get("reviewBadges"):
            extra["reviewBadges"] = payload["reviewBadges"]
        question = TeacherQuizQuestion(
            id=_uuid4(),
            quiz_id=quiz.id,
            sort_order=0,  # will be set by repo.add_question
            type=payload["type"],
            prompt=payload["prompt"],
            points=float(payload.get("points") or 1.0),
            options=payload.get("options"),
            response_lines=payload.get("response_lines"),
            extra=extra or None,
        )
        return self.repo.add_question(quiz, question)

    def patch_question(
        self,
        *,
        current_user: User,
        quiz_id: UUID,
        question_id: UUID,
        patch: Dict[str, Any],
    ) -> TeacherQuiz:
        quiz = self.repo.get_quiz(current_user.tenant_id, quiz_id, with_questions=True)
        if not quiz:
            raise not_found()
        question = self.repo.get_question(current_user.tenant_id, quiz_id, question_id)
        if not question:
            raise not_found("Question not found")
        return self.repo.patch_question(quiz, question, patch)

    def delete_question(
        self,
        *,
        current_user: User,
        quiz_id: UUID,
        question_id: UUID,
    ) -> TeacherQuiz:
        quiz = self.repo.get_quiz(current_user.tenant_id, quiz_id, with_questions=True)
        if not quiz:
            raise not_found()
        question = self.repo.get_question(current_user.tenant_id, quiz_id, question_id)
        if not question:
            raise not_found("Question not found")
        if len(quiz.questions) <= 1:
            raise validation_failed("Cannot delete the last question in a quiz.")
        return self.repo.delete_question(quiz, question)

    def reorder_questions(
        self,
        *,
        current_user: User,
        quiz_id: UUID,
        order: List[Dict[str, Any]],
    ) -> TeacherQuiz:
        quiz = self.repo.get_quiz(current_user.tenant_id, quiz_id, with_questions=True)
        if not quiz:
            raise not_found()
        return self.repo.bulk_reorder_questions(quiz, order)

    async def regenerate_question(
        self,
        *,
        current_user: User,
        quiz_id: UUID,
        question_id: UUID,
        idempotency_key: Optional[str] = None,
    ) -> TeacherQuiz:
        """Re-generate a single question using the quiz's stored RAG scope."""
        quiz = self.repo.get_quiz(current_user.tenant_id, quiz_id, with_questions=True)
        if not quiz:
            raise not_found()
        question = self.repo.get_question(current_user.tenant_id, quiz_id, question_id)
        if not question:
            raise not_found("Question not found")

        # Retrieve context (reuse same RAG pipeline)
        context_text = ""
        citations: List[Dict[str, str]] = []
        chunk_texts: Dict[str, str] = {}
        allowed_titles: List[str] = []
        if not quiz.generate_without_sources:
            _validate_sourced_scope(
                self.db,
                tenant_id=current_user.tenant_id,
                generate_without_sources=False,
                source_pack_ids=list(quiz.source_pack_ids or []),
                scope_topic_ids=list(quiz.scope_topic_ids or []),
            )
            try:
                pack_ids = [UUID(x) for x in (quiz.source_pack_ids or []) if x]
            except Exception:
                raise validation_failed("Invalid pack IDs on quiz.")
            if pack_ids:
                scope_ids = _parse_scope_topic_ids(quiz.scope_topic_ids)
                try:
                    rr = self.retrieval.retrieve(
                        tenant_id=current_user.tenant_id,
                        pack_ids=pack_ids,
                        topics=list(quiz.scope_topics or []),
                        scope_topic_ids=scope_ids,
                        refinement=quiz.scope_refinement,
                        max_chunks=_compute_max_chunks(1),
                        generate_without_sources=False,
                        seed=str(quiz.id),
                    )
                except RetrievalScopeError as e:
                    raise retrieval_scope_failed(
                        e.message,
                        topic_ids=e.topic_ids,
                        fallback_available=e.fallback_available,
                    ) from e
                context_text = rr.context_text
                citations = rr.citations
                chunk_texts = rr.chunk_texts
                allowed_titles = _allowed_topic_titles(self.db, scope_ids)

        # Generate exactly 1 question of the same type
        qtype = question.type
        timeout_s = float(getattr(settings, "QUIZ_GENERATION_TIMEOUT_SECONDS", 180.0))
        try:
            gen_questions, _, _ = await asyncio.wait_for(
                self.generator.generate_questions(
                    subject=quiz.subject,
                    grade=quiz.grade,
                    topic_label=quiz.topic_summary or "General scope",
                    difficulty=quiz.difficulty,
                    question_count=1,
                    include_mcq=(qtype == "mcq"),
                    include_tf=(qtype == "tf"),
                    include_short=(qtype == "short"),
                    counts_by_type=None,
                    teacher_notes=quiz.teacher_notes,
                    context_text=context_text,
                    avoid_prompts=[q.prompt for q in (quiz.questions or []) if q.prompt],
                    must_differ_from=question.prompt,
                    allowed_topic_titles=allowed_titles,
                    sources_grounded=not quiz.generate_without_sources,
                    source_citations=citations,
                    chunk_texts=chunk_texts,
                ),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError as e:
            raise QuizError(code="GENERATION_TIMEOUT", message="Regeneration timed out", http_status=504) from e
        except Exception as e:
            raise generation_failed("Question regeneration failed") from e

        if not gen_questions:
            raise generation_failed("Generator returned no question.")

        new_q = gen_questions[0]
        # Preserve sort_order and quiz_id; replace content
        patch: Dict[str, Any] = {
            "prompt": new_q.prompt,
            "points": new_q.points,
            "options": new_q.options,
            "response_lines": new_q.response_lines,
            "reviewBadges": (new_q.extra or {}).get("reviewBadges"),
            "extra": new_q.extra,
        }
        return self.repo.patch_question(quiz, question, patch)

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    async def generate_for_quiz(
        self,
        *,
        current_user: User,
        quiz_id: UUID,
        req: Dict[str, Any],
        idempotency_key: Optional[str],
    ) -> Tuple[TeacherQuizGenerationRun, TeacherQuiz, List[str]]:
        quiz = self.repo.get_quiz(current_user.tenant_id, quiz_id, with_questions=True)
        if not quiz:
            raise not_found()

        # Idempotency: if key seen, return latest state without re-running.
        if idempotency_key:
            prior = self.repo.find_generation_run_by_idempotency(quiz.id, idempotency_key)
            if prior and prior.status == "completed":
                return prior, quiz, list(prior.retrieval_warnings or [])

        difficulty = req.get("difficulty") or quiz.difficulty
        teacher_notes = req.get("teacherNotes") or quiz.teacher_notes

        question_count = int(req.get("questionCount") or 10)
        include_mcq = bool(req.get("includeMcq", True))
        include_tf = bool(req.get("includeTf", True))
        include_short = bool(req.get("includeShort", True))
        counts_by_type = req.get("countsByType")

        # Retrieval (only when sources enabled)
        context_text = ""
        citations: List[Dict[str, str]] = []
        chunk_texts: Dict[str, str] = {}
        retrieval_warnings: List[str] = []
        retrieval_meta: Dict[str, Any] = {}

        if not quiz.generate_without_sources:
            _validate_sourced_scope(
                self.db,
                tenant_id=current_user.tenant_id,
                generate_without_sources=False,
                source_pack_ids=list(quiz.source_pack_ids or []),
                scope_topic_ids=list(quiz.scope_topic_ids or []),
            )
            try:
                pack_ids = [UUID(x) for x in (quiz.source_pack_ids or []) if x]
            except Exception:
                raise validation_failed("Invalid pack IDs on quiz.")

            scope_ids = _parse_scope_topic_ids(quiz.scope_topic_ids)
            max_chunks = _compute_max_chunks(question_count)
            try:
                rr = self.retrieval.retrieve(
                    tenant_id=current_user.tenant_id,
                    pack_ids=pack_ids,
                    topics=list(quiz.scope_topics or []),
                    scope_topic_ids=scope_ids,
                    refinement=quiz.scope_refinement,
                    max_chunks=max_chunks,
                    generate_without_sources=bool(quiz.generate_without_sources),
                    seed=str(quiz.id),
                )
            except RetrievalScopeError as e:
                raise retrieval_scope_failed(
                    e.message,
                    topic_ids=e.topic_ids,
                    fallback_available=e.fallback_available,
                ) from e
            context_text = rr.context_text
            citations = rr.citations
            chunk_texts = rr.chunk_texts
            retrieval_warnings.extend(rr.warnings)
            retrieval_meta = rr.metadata
            allowed_titles = _allowed_topic_titles(
                self.db, _parse_scope_topic_ids(quiz.scope_topic_ids)
            )
            if not retrieval_meta.get("applied_topic_filter") or int(
                retrieval_meta.get("chunk_count") or 0
            ) == 0:
                logger.warning(
                    "quiz_scope_anomaly",
                    extra={
                        "quiz_id": str(quiz.id),
                        "tenant_id": str(current_user.tenant_id),
                        "metadata": retrieval_meta,
                    },
                )
        else:
            retrieval_warnings.append("Generation without sources (grounding off).")
            allowed_titles = []

        # LLM generation with timeout guard
        timeout_s = float(getattr(settings, "QUIZ_GENERATION_TIMEOUT_SECONDS", 180.0))
        input_payload = {
            "quiz_id": str(quiz.id),
            "subject": quiz.subject,
            "grade": quiz.grade,
            "topic": quiz.topic_summary or _topic_summary(list(quiz.scope_topics or []), quiz.scope_refinement),
            "difficulty": difficulty,
            "questionCount": question_count,
            "includeMcq": include_mcq,
            "includeTf": include_tf,
            "includeShort": include_short,
            "countsByType": counts_by_type,
            "teacherNotes": teacher_notes or "",
            "grounded": not quiz.generate_without_sources,
        }
        input_hash = self.generator.build_input_hash(input_payload)

        try:
            gen_questions, gen_warnings, gen_meta = await asyncio.wait_for(
                self.generator.generate_questions(
                    subject=quiz.subject,
                    grade=quiz.grade,
                    topic_label=quiz.topic_summary or input_payload["topic"],
                    difficulty=difficulty,
                    question_count=question_count,
                    include_mcq=include_mcq,
                    include_tf=include_tf,
                    include_short=include_short,
                    counts_by_type=counts_by_type,
                    teacher_notes=teacher_notes,
                    context_text=context_text,
                    avoid_prompts=[q.prompt for q in (quiz.questions or []) if q.prompt],
                    allowed_topic_titles=allowed_titles,
                    sources_grounded=not quiz.generate_without_sources,
                    source_citations=citations,
                    chunk_texts=chunk_texts,
                ),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError as e:
            run = TeacherQuizGenerationRun(
                quiz_id=quiz.id,
                status="failed",
                error_code="GENERATION_TIMEOUT",
                error_message=f"Timed out after {timeout_s}s",
                input_hash=input_hash,
                idempotency_key=idempotency_key,
                retrieval_warnings=retrieval_warnings,
                retrieval_metadata={"citations": citations, **retrieval_meta},
                llm_model=None,
            )
            run = self.repo.create_generation_run(run)
            raise QuizError(code="GENERATION_TIMEOUT", message="Generation timed out", http_status=504) from e
        except Exception as e:
            run = TeacherQuizGenerationRun(
                quiz_id=quiz.id,
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
            raise generation_failed("Quiz generation failed") from e

        warnings = retrieval_warnings + gen_warnings
        llm_model = gen_meta.get("model_used")

        # Persist questions
        db_questions: List[TeacherQuizQuestion] = []
        for i, q in enumerate(gen_questions):
            db_questions.append(
                TeacherQuizQuestion(
                    sort_order=i,
                    type=q.qtype,
                    prompt=q.prompt,
                    points=q.points,
                    options=q.options,
                    response_lines=q.response_lines,
                    extra=q.extra,
                )
            )

        quiz.questions = db_questions
        quiz.questions_count = len(db_questions)
        quiz.total_marks = _compute_total_marks(db_questions)
        quiz.difficulty = difficulty or quiz.difficulty
        quiz.teacher_notes = teacher_notes or quiz.teacher_notes
        quiz.topic_summary = quiz.topic_summary or input_payload["topic"]
        quiz.content_version = int(quiz.content_version or 1) + 1
        quiz.updated_at = datetime.now(timezone.utc)
        self.repo.update_quiz(quiz)

        run = TeacherQuizGenerationRun(
            quiz_id=quiz.id,
            status="completed",
            input_hash=input_hash,
            idempotency_key=idempotency_key,
            retrieval_warnings=warnings,
            retrieval_metadata={"citations": citations, **retrieval_meta, "llm": gen_meta},
            llm_model=str(llm_model) if llm_model else None,
        )
        run = self.repo.create_generation_run(run)

        logger.info(
            "quiz_generated",
            extra={
                "tenant_id": str(current_user.tenant_id),
                "quiz_id": str(quiz.id),
                "question_count": quiz.questions_count,
                "content_version": quiz.content_version,
            },
        )
        return run, quiz, warnings

