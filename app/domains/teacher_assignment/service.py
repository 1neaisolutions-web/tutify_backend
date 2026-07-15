from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.domains.auth.models import User
from app.domains.content_ingestion.teacher_scope_validation import (
    SourcedScopeValidationError,
    parse_scope_topic_ids,
    validate_sourced_scope,
)
from app.domains.content_ingestion.topic_scope import RetrievalScopeError
from app.domains.teacher_assignment.errors import (
    AssignmentError,
    generation_failed,
    not_found,
    retrieval_scope_failed,
    validation_failed,
)
from app.domains.teacher_assignment.generation import AssignmentGenerationService
from app.domains.teacher_assignment.models import (
    TeacherAssignment,
    TeacherAssignmentGenerationRun,
)
from app.domains.teacher_assignment.repository import (
    AssignmentListFilters,
    TeacherAssignmentRepository,
)
from app.domains.teacher_quiz.retrieval import QuizRetrievalService

logger = get_logger(__name__)


def _topic_summary(scope_topics: List[str], scope_refinement: Optional[str]) -> str:
    base = " · ".join([t for t in scope_topics if t and t.strip()])
    if scope_refinement and scope_refinement.strip():
        return f"{base} — {scope_refinement.strip()}" if base else scope_refinement.strip()
    return base or "General scope"


def _compute_counts(brief_topics: List[Dict[str, Any]]) -> Tuple[int, int]:
    tc = len(brief_topics)
    lc = sum(len(t.get("lines", [])) for t in brief_topics if isinstance(t, dict))
    return tc, lc


def _materialize_brief_topics(gen_topics: list) -> List[Dict[str, Any]]:
    result = []
    for gt in gen_topics:
        result.append(
            {
                "id": gt.topic_id,
                "title": gt.title,
                "lines": [
                    {"id": str(uuid.uuid4()), "text": ln}
                    for ln in gt.lines
                ],
            }
        )
    return result


def _assignment_retrieval(
    service: "TeacherAssignmentService",
    *,
    assignment: TeacherAssignment,
    tenant_id: UUID,
    max_chunks: int,
) -> Tuple[str, list, List[str], Dict[str, Any]]:
    if assignment.generate_without_sources:
        return "", [], [], {}
    try:
        validate_sourced_scope(
            service.db,
            tenant_id=tenant_id,
            generate_without_sources=False,
            source_pack_ids=list(assignment.source_pack_ids or []),
            scope_topic_ids=list(assignment.scope_topic_ids or []),
        )
    except SourcedScopeValidationError as e:
        raise validation_failed(e.message) from e
    try:
        pack_ids = [UUID(x) for x in (assignment.source_pack_ids or []) if x]
    except Exception:
        raise validation_failed("Invalid pack IDs on assignment.")
    scope_ids = parse_scope_topic_ids(assignment.scope_topic_ids)
    try:
        rr = service.retrieval.retrieve(
            tenant_id=tenant_id,
            pack_ids=pack_ids,
            topics=list(assignment.scope_topics or []),
            scope_topic_ids=scope_ids,
            refinement=assignment.scope_refinement,
            max_chunks=max_chunks,
            generate_without_sources=False,
            seed=str(assignment.id),
        )
    except RetrievalScopeError as e:
        raise retrieval_scope_failed(
            e.message,
            topic_ids=e.topic_ids,
            fallback_available=e.fallback_available,
        ) from e
    return rr.context_text, rr.citations, list(rr.warnings), dict(rr.metadata or {})


class TeacherAssignmentService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = TeacherAssignmentRepository(db)
        self.retrieval = QuizRetrievalService(db)
        self.generator = AssignmentGenerationService()

    def list_assignments(
        self,
        *,
        current_user: User,
        filters: AssignmentListFilters,
        page: int,
        page_size: int,
    ) -> Tuple[List[TeacherAssignment], int]:
        return self.repo.list_assignments(
            current_user.tenant_id, filters, page=page, page_size=page_size,
            owner_user_id=current_user.id,
        )

    def get_assignment(self, *, current_user: User, assignment_id: UUID) -> TeacherAssignment:
        a = self.repo.get_assignment(current_user.tenant_id, assignment_id)
        if not a:
            raise not_found()
        return a

    def create_assignment(self, *, current_user: User, payload: Dict[str, Any]) -> TeacherAssignment:
        try:
            validate_sourced_scope(
                self.db,
                tenant_id=current_user.tenant_id,
                generate_without_sources=bool(payload.get("generateWithoutSources") or False),
                source_pack_ids=list(payload.get("sourceBookIds") or []),
                scope_topic_ids=list(payload.get("scopeTopicIds") or []),
            )
        except SourcedScopeValidationError as e:
            raise validation_failed(e.message) from e
        now = datetime.now(timezone.utc)
        brief = list(payload.get("briefTopics") or [])
        tc, lc = _compute_counts(brief)
        a = TeacherAssignment(
            id=uuid.uuid4(),
            tenant_id=current_user.tenant_id,
            owner_user_id=current_user.id,
            title=payload["title"],
            subject=payload["subject"],
            grade=payload["grade"],
            class_keys=list(payload.get("classes") or []),
            assignment_type=payload.get("type") or "Structured response",
            rigor_profile=payload.get("rigorProfile") or "Standard",
            student_instructions=payload.get("studentInstructions"),
            teacher_notes=payload.get("teacherNotes"),
            status=payload.get("status") or "draft",
            due_at=payload.get("dueAt"),
            assigned_at=payload.get("assignedAt"),
            source_pack_ids=list(payload.get("sourceBookIds") or []),
            scope_topics=list(payload.get("scopeTopics") or []),
            scope_topic_ids=list(payload.get("scopeTopicIds") or []),
            scope_refinement=payload.get("scopeRefinement"),
            topic_summary=_topic_summary(
                list(payload.get("scopeTopics") or []),
                payload.get("scopeRefinement"),
            ),
            generate_without_sources=bool(payload.get("generateWithoutSources") or False),
            difficulty=payload.get("difficulty"),
            brief_topics=brief,
            handout_layout=payload.get("handoutLayout"),
            topics_count=tc,
            lines_count=lc,
            assigned_count=0,
            submitted_count=0,
            pending_count=0,
            graded_count=0,
            content_version=1,
            created_at=now,
            updated_at=now,
        )
        return self.repo.create_assignment(a)

    def patch_assignment(
        self,
        *,
        current_user: User,
        assignment_id: UUID,
        patch: Dict[str, Any],
    ) -> TeacherAssignment:
        a = self.repo.get_assignment(current_user.tenant_id, assignment_id)
        if not a:
            raise not_found()

        field_map = [
            ("title", "title"),
            ("subject", "subject"),
            ("grade", "grade"),
            ("classes", "class_keys"),
            ("type", "assignment_type"),
            ("rigorProfile", "rigor_profile"),
            ("studentInstructions", "student_instructions"),
            ("teacherNotes", "teacher_notes"),
            ("status", "status"),
            ("dueAt", "due_at"),
            ("assignedAt", "assigned_at"),
            ("sourceBookIds", "source_pack_ids"),
            ("scopeTopics", "scope_topics"),
            ("scopeTopicIds", "scope_topic_ids"),
            ("scopeRefinement", "scope_refinement"),
            ("generateWithoutSources", "generate_without_sources"),
            ("difficulty", "difficulty"),
            ("briefTopics", "brief_topics"),
            ("handoutLayout", "handout_layout"),
        ]
        for key, attr in field_map:
            if key in patch and patch[key] is not None:
                setattr(a, attr, patch[key])

        if "briefTopics" in patch and patch["briefTopics"] is not None:
            tc, lc = _compute_counts(list(a.brief_topics or []))
            a.topics_count = tc
            a.lines_count = lc

        if "scopeTopics" in patch or "scopeRefinement" in patch or "scopeTopicIds" in patch:
            a.topic_summary = _topic_summary(list(a.scope_topics or []), a.scope_refinement)

        if not a.generate_without_sources and (
            "scopeTopicIds" in patch or "scopeTopics" in patch or "sourceBookIds" in patch
        ):
            try:
                validate_sourced_scope(
                    self.db,
                    tenant_id=current_user.tenant_id,
                    generate_without_sources=False,
                    source_pack_ids=list(a.source_pack_ids or []),
                    scope_topic_ids=list(a.scope_topic_ids or []),
                )
            except SourcedScopeValidationError as e:
                raise validation_failed(e.message) from e

        a.updated_at = datetime.now(timezone.utc)
        return self.repo.update_assignment(a)

    def delete_assignment(self, *, current_user: User, assignment_id: UUID) -> None:
        a = self.repo.get_assignment(current_user.tenant_id, assignment_id)
        if not a:
            raise not_found()
        self.repo.delete_assignment(a)

    def duplicate_assignment(self, *, current_user: User, assignment_id: UUID) -> TeacherAssignment:
        a = self.repo.get_assignment(current_user.tenant_id, assignment_id)
        if not a:
            raise not_found()
        now = datetime.now(timezone.utc)
        return self.repo.duplicate_assignment(
            source=a,
            new_id=uuid.uuid4(),
            new_title=f"{a.title} (copy)",
            now=now,
        )

    async def generate_brief(
        self,
        *,
        current_user: User,
        assignment_id: UUID,
        req: Dict[str, Any],
        idempotency_key: Optional[str],
    ) -> Tuple[TeacherAssignmentGenerationRun, TeacherAssignment, List[str]]:
        a = self.repo.get_assignment(current_user.tenant_id, assignment_id)
        if not a:
            raise not_found()

        if idempotency_key:
            prior = self.repo.find_generation_run_by_idempotency(a.id, idempotency_key)
            if prior and prior.status == "completed":
                refreshed = self.repo.get_assignment(current_user.tenant_id, assignment_id)
                if refreshed:
                    a = refreshed
                return prior, a, list(prior.retrieval_warnings or [])

        difficulty = req.get("difficulty") or a.difficulty
        teacher_notes = req.get("teacherNotes") or a.teacher_notes
        topic_count = int(req.get("topicCount") or 3)
        rigor_profile = req.get("rigorProfile") or a.rigor_profile or "Standard"

        context_text = ""
        citations: list = []
        retrieval_warnings: List[str] = []
        retrieval_meta: Dict[str, Any] = {}

        if not a.generate_without_sources:
            context_text, citations, retrieval_warnings, retrieval_meta = _assignment_retrieval(
                self,
                assignment=a,
                tenant_id=current_user.tenant_id,
                max_chunks=18,
            )
        else:
            retrieval_warnings.append("Generation without sources (grounding off).")

        input_payload = {
            "assignment_id": str(a.id),
            "subject": a.subject,
            "grade": a.grade,
            "assignment_type": a.assignment_type,
            "rigor_profile": rigor_profile,
            "topic_label": a.topic_summary
            or _topic_summary(list(a.scope_topics or []), a.scope_refinement),
            "scope_topics": list(a.scope_topics or []),
            "difficulty": difficulty,
            "topic_count": topic_count,
            "grounded": not a.generate_without_sources,
        }
        input_hash = self.generator.build_input_hash(input_payload)

        timeout_s = float(getattr(settings, "QUIZ_GENERATION_TIMEOUT_SECONDS", 180.0))
        try:
            gen_topics, gen_warnings, gen_meta = await asyncio.wait_for(
                self.generator.generate_brief(
                    subject=a.subject,
                    grade=a.grade,
                    assignment_type=a.assignment_type,
                    rigor_profile=rigor_profile,
                    topic_label=input_payload["topic_label"],
                    scope_topics=list(a.scope_topics or []),
                    difficulty=difficulty,
                    topic_count=topic_count,
                    teacher_notes=teacher_notes,
                    context_text=context_text,
                ),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError as e:
            run = TeacherAssignmentGenerationRun(
                assignment_id=a.id,
                run_type="full",
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
            raise AssignmentError(
                code="GENERATION_TIMEOUT",
                message="Generation timed out",
                http_status=504,
            ) from e
        except Exception as e:
            run = TeacherAssignmentGenerationRun(
                assignment_id=a.id,
                run_type="full",
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
            raise generation_failed("Assignment generation failed") from e

        warnings = retrieval_warnings + gen_warnings
        brief = _materialize_brief_topics(gen_topics)
        tc, lc = _compute_counts(brief)

        a.brief_topics = brief
        a.topics_count = tc
        a.lines_count = lc
        a.difficulty = difficulty or a.difficulty
        a.rigor_profile = rigor_profile
        a.teacher_notes = teacher_notes if teacher_notes is not None else a.teacher_notes
        a.topic_summary = a.topic_summary or input_payload["topic_label"]
        a.content_version = int(a.content_version or 1) + 1
        a.updated_at = datetime.now(timezone.utc)
        self.repo.update_assignment(a)

        run = TeacherAssignmentGenerationRun(
            assignment_id=a.id,
            run_type="full",
            status="completed",
            input_hash=input_hash,
            idempotency_key=idempotency_key,
            retrieval_warnings=warnings,
            retrieval_metadata={
                "citations": citations,
                **retrieval_meta,
                "llm": gen_meta,
            },
            llm_model=str(gen_meta.get("model_used")) if gen_meta.get("model_used") else None,
        )
        run = self.repo.create_generation_run(run)

        logger.info(
            "assignment_generated",
            extra={
                "tenant_id": str(current_user.tenant_id),
                "assignment_id": str(a.id),
                "topics_count": tc,
                "lines_count": lc,
            },
        )
        return run, a, warnings

    async def regenerate_topic(
        self,
        *,
        current_user: User,
        assignment_id: UUID,
        topic_id: str,
        topic_title: str,
    ) -> Tuple[Dict[str, Any], List[str]]:
        a = self.repo.get_assignment(current_user.tenant_id, assignment_id)
        if not a:
            raise not_found()

        # Pull the current topic snapshot so regeneration can avoid repeating it.
        existing_lines: List[str] = []
        other_titles: List[str] = []
        try:
            for t in (a.brief_topics or []):
                if not isinstance(t, dict):
                    continue
                tt = str(t.get("title") or "").strip()
                if tt:
                    other_titles.append(tt)
                if str(t.get("id") or "") == topic_id:
                    raw_lines = t.get("lines") or []
                    for ln in raw_lines:
                        if isinstance(ln, dict):
                            txt = str(ln.get("text") or "").strip()
                        else:
                            txt = str(ln or "").strip()
                        if txt:
                            existing_lines.append(txt)
        except Exception:
            existing_lines = []
            other_titles = []

        context_text = ""
        if not a.generate_without_sources:
            context_text, _, _, _ = _assignment_retrieval(
                self,
                assignment=a,
                tenant_id=current_user.tenant_id,
                max_chunks=6,
            )

        timeout_s = float(getattr(settings, "QUIZ_GENERATION_TIMEOUT_SECONDS", 180.0))
        try:
            gen_topic, warnings, _ = await asyncio.wait_for(
                self.generator.regenerate_topic(
                    subject=a.subject,
                    grade=a.grade,
                    assignment_type=a.assignment_type,
                    rigor_profile=a.rigor_profile or "Standard",
                    topic_title=topic_title,
                    difficulty=a.difficulty,
                    teacher_notes=a.teacher_notes,
                    context_text=context_text,
                    existing_lines=existing_lines,
                    other_titles=[t for t in other_titles if t and t != topic_title],
                ),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError as e:
            raise AssignmentError(
                code="GENERATION_TIMEOUT",
                message="Topic regeneration timed out",
                http_status=504,
            ) from e
        except Exception as e:
            raise generation_failed("Topic regeneration failed") from e

        topic_stub = {
            "id": topic_id,
            "title": gen_topic.title,
            "lines": [
                {"id": str(uuid.uuid4()), "text": ln}
                for ln in gen_topic.lines
            ],
        }
        return topic_stub, warnings

    async def regenerate_line(
        self,
        *,
        current_user: User,
        assignment_id: UUID,
        topic_id: str,
        topic_title: str,
        line_index: int,
    ) -> Tuple[str, str, List[str]]:
        a = self.repo.get_assignment(current_user.tenant_id, assignment_id)
        if not a:
            raise not_found()

        existing_lines: List[str] = []
        objective_text: Optional[str] = None
        tasks_text: Optional[str] = None
        evidence_text: Optional[str] = None
        try:
            for t in (a.brief_topics or []):
                if not isinstance(t, dict):
                    continue
                if str(t.get("id") or "") != topic_id:
                    continue
                raw_lines = t.get("lines") or []
                for ln in raw_lines:
                    if isinstance(ln, dict):
                        txt = str(ln.get("text") or "").strip()
                    else:
                        txt = str(ln or "").strip()
                    if txt:
                        existing_lines.append(txt)
                # Best-effort extraction by expected ordering (Objective/Tasks/Evidence)
                if len(raw_lines) >= 1 and isinstance(raw_lines[0], dict):
                    objective_text = str(raw_lines[0].get("text") or "").strip()
                if len(raw_lines) >= 2 and isinstance(raw_lines[1], dict):
                    tasks_text = str(raw_lines[1].get("text") or "").strip()
                if len(raw_lines) >= 3 and isinstance(raw_lines[2], dict):
                    evidence_text = str(raw_lines[2].get("text") or "").strip()
        except Exception:
            existing_lines = []
            objective_text = None
            tasks_text = None
            evidence_text = None

        context_text = ""
        if not a.generate_without_sources:
            context_text, _, _, _ = _assignment_retrieval(
                self,
                assignment=a,
                tenant_id=current_user.tenant_id,
                max_chunks=4,
            )

        timeout_s = float(getattr(settings, "QUIZ_GENERATION_TIMEOUT_SECONDS", 180.0))
        try:
            gen_line, warnings, _ = await asyncio.wait_for(
                self.generator.regenerate_line(
                    subject=a.subject,
                    grade=a.grade,
                    assignment_type=a.assignment_type,
                    rigor_profile=a.rigor_profile or "Standard",
                    topic_title=topic_title,
                    line_index=line_index,
                    difficulty=a.difficulty,
                    teacher_notes=a.teacher_notes,
                    context_text=context_text,
                    existing_lines=existing_lines,
                    objective_text=objective_text,
                    tasks_text=tasks_text,
                    evidence_text=evidence_text,
                ),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError as e:
            raise AssignmentError(
                code="GENERATION_TIMEOUT",
                message="Line regeneration timed out",
                http_status=504,
            ) from e
        except Exception as e:
            raise generation_failed("Line regeneration failed") from e

        return gen_line.line_id, gen_line.line_text, warnings
