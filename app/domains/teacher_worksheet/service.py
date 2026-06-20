from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

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
from app.domains.teacher_worksheet.errors import (
    generation_failed,
    generation_timeout,
    invalid_block_type,
    min_block,
    min_session,
    not_found,
    retrieval_scope_failed,
    validation_failed,
)
from app.domains.teacher_worksheet.generation import GeneratedBlock, WorksheetGenerationService
from app.domains.teacher_worksheet.models import (
    TeacherWorksheet,
    TeacherWorksheetBlock,
    TeacherWorksheetGenerationRun,
    TeacherWorksheetSession,
)
from app.domains.teacher_worksheet.repository import TeacherWorksheetRepository, WorksheetListFilters
from app.domains.teacher_worksheet.retrieval import WorksheetRetrievalService

logger = get_logger(__name__)


def _topic_summary(scope_topics: List[str], scope_refinement: Optional[str]) -> str:
    base = " · ".join([t for t in scope_topics if t and t.strip()])
    if scope_refinement and scope_refinement.strip():
        return f"{base} — {scope_refinement.strip()}" if base else scope_refinement.strip()
    return base or "General scope"


def _source_summary(ws: TeacherWorksheet) -> Optional[str]:
    if ws.generate_without_sources:
        return "Generation without catalog retrieval (grounding off)"
    pack_count = len(ws.source_pack_ids or [])
    topic_count = len(ws.scope_topics or [])
    refine = " · scope hint applied" if (ws.scope_refinement or "").strip() else ""
    return f"Catalog retrieval · {pack_count} source{'s' if pack_count != 1 else ''} · {topic_count} topic strand{'s' if topic_count != 1 else ''}{refine}"


def _block_data_from_generated(g: GeneratedBlock) -> Dict[str, Any]:
    if g.btype == "mcq":
        return {"options": list(g.options or []), "answer": g.answer or ""}
    if g.btype == "fill_blank":
        return {"answer": g.answer or ""}
    if g.btype == "short":
        return {"sample_answer": g.sample_answer or "", "response_lines": int(g.response_lines or 4)}
    return {"left": list(g.left or []), "right": list(g.right or [])}


def _payload_to_block_data(btype: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    if btype == "mcq":
        opts = list(payload.get("options") or [])
        return {"options": opts, "answer": str(payload.get("answer") or "")}
    if btype == "fill_blank":
        return {"answer": str(payload.get("answer") or "")}
    if btype == "short":
        return {
            "sample_answer": str(payload.get("sampleAnswer") or ""),
            "response_lines": int(payload.get("responseLines") or 4),
        }
    return {"left": list(payload.get("left") or []), "right": list(payload.get("right") or [])}


def _validate_block_payload(btype: str, payload: Dict[str, Any]) -> None:
    if btype == "mcq":
        opts = payload.get("options")
        ans = str(payload.get("answer") or "")
        if not isinstance(opts, list) or len(opts) < 2:
            raise validation_failed("MCQ requires at least two options.")
        if ans not in opts:
            raise validation_failed("MCQ answer must match one of the options.")
    elif btype == "fill_blank":
        if not str(payload.get("answer") or "").strip():
            raise validation_failed("Fill-in-the-blank requires an answer.")
    elif btype == "short":
        rl = int(payload.get("responseLines") or 4)
        if rl < 1 or rl > 12:
            raise validation_failed("responseLines must be between 1 and 12.")
    elif btype == "match":
        left = payload.get("left") or []
        right = payload.get("right") or []
        if not isinstance(left, list) or not isinstance(right, list) or len(left) != len(right) or len(left) < 2:
            raise validation_failed("Match blocks require left/right lists of equal length (min 2).")
    else:
        raise invalid_block_type()


def _total_blocks(ws: TeacherWorksheet) -> int:
    return sum(len(list(s.blocks or [])) for s in (ws.sessions or []))


def _block_signature_for_avoid(b: TeacherWorksheetBlock) -> Optional[str]:
    """Stable text signature for duplicate-avoidance (prompt or match rows)."""
    t = b.type
    d = b.data if isinstance(b.data, dict) else {}
    if t == "match":
        left = d.get("left") or []
        right = d.get("right") or []
        if isinstance(left, list) and isinstance(right, list) and len(left) == len(right) and len(left) >= 2:
            parts = [f"{str(l).strip()}::{str(r).strip()}" for l, r in zip(left, right)]
            return "MATCH " + " | ".join(parts)[:900]
    p = (b.prompt or "").strip()
    return p if p else None


def _worksheet_existing_signatures(ws: TeacherWorksheet) -> List[str]:
    out: List[str] = []
    for s in ws.sessions or []:
        for b in s.blocks or []:
            sig = _block_signature_for_avoid(b)
            if sig:
                out.append(sig)
    return out


def _worksheet_retrieval(
    service: "TeacherWorksheetService",
    *,
    worksheet: TeacherWorksheet,
    tenant_id: UUID,
    max_chunks: int,
) -> Tuple[str, list, List[str], Dict[str, Any]]:
    if worksheet.generate_without_sources:
        return "", [], [], {}
    try:
        validate_sourced_scope(
            service.db,
            tenant_id=tenant_id,
            generate_without_sources=False,
            source_pack_ids=list(worksheet.source_pack_ids or []),
            scope_topic_ids=list(worksheet.scope_topic_ids or []),
        )
    except SourcedScopeValidationError as e:
        raise validation_failed(e.message) from e
    try:
        pack_ids = [UUID(x) for x in (worksheet.source_pack_ids or []) if x]
    except Exception:
        raise validation_failed("Invalid pack IDs on worksheet.")
    scope_ids = parse_scope_topic_ids(worksheet.scope_topic_ids)
    try:
        rr = service.retrieval.retrieve(
            tenant_id=tenant_id,
            pack_ids=pack_ids,
            topics=list(worksheet.scope_topics or []),
            scope_topic_ids=scope_ids,
            refinement=worksheet.scope_refinement,
            max_chunks=max_chunks,
            generate_without_sources=False,
            seed=str(worksheet.id),
        )
    except RetrievalScopeError as e:
        raise retrieval_scope_failed(
            e.message,
            topic_ids=e.topic_ids,
            fallback_available=e.fallback_available,
        ) from e
    return rr.context_text, rr.citations, list(rr.warnings), dict(rr.metadata or {})


class TeacherWorksheetService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = TeacherWorksheetRepository(db)
        self.retrieval = WorksheetRetrievalService(db)
        self.generator = WorksheetGenerationService()

    def list_worksheets(
        self,
        *,
        current_user: User,
        filters: WorksheetListFilters,
        page: int,
        page_size: int,
    ) -> Tuple[List[TeacherWorksheet], int]:
        return self.repo.list_worksheets(current_user.tenant_id, filters, page=page, page_size=page_size,
                                          owner_user_id=current_user.id)

    def get_worksheet(self, *, current_user: User, worksheet_id: UUID) -> TeacherWorksheet:
        ws = self.repo.get_worksheet(current_user.tenant_id, worksheet_id, with_children=True)
        if not ws:
            raise not_found()
        return ws

    def create_worksheet(self, *, current_user: User, payload: Dict[str, Any]) -> TeacherWorksheet:
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
        ws = TeacherWorksheet(
            id=uuid4(),
            tenant_id=current_user.tenant_id,
            owner_user_id=current_user.id,
            title=payload["title"],
            subject=payload["subject"],
            grade=payload["grade"],
            output_format=payload.get("outputFormat") or "interactive_digital",
            class_keys=list(payload.get("classes") or []),
            student_instructions=payload.get("studentInstructions"),
            teacher_notes=payload.get("teacherNotes"),
            status=payload.get("status") or "draft",
            assigned_at=payload.get("assignedAt"),
            due_at=payload.get("dueAt"),
            source_pack_ids=list(payload.get("sourceBookIds") or []),
            scope_topics=list(payload.get("scopeTopics") or []),
            scope_topic_ids=list(payload.get("scopeTopicIds") or []),
            scope_refinement=payload.get("scopeRefinement"),
            topic_summary=_topic_summary(list(payload.get("scopeTopics") or []), payload.get("scopeRefinement")),
            generate_without_sources=bool(payload.get("generateWithoutSources") or False),
            difficulty=payload.get("difficulty"),
            handout_layout=payload.get("handoutLayout"),
            sessions_count=0,
            blocks_count=0,
            submission_count=0,
            avg_score=0.0,
            content_version=1,
            created_at=now,
            updated_at=now,
        )
        return self.repo.create_worksheet(ws)

    def patch_worksheet(self, *, current_user: User, worksheet_id: UUID, patch: Dict[str, Any]) -> TeacherWorksheet:
        ws = self.repo.get_worksheet(current_user.tenant_id, worksheet_id, with_children=True)
        if not ws:
            raise not_found()
        mapping = [
            ("title", "title"),
            ("subject", "subject"),
            ("grade", "grade"),
            ("outputFormat", "output_format"),
            ("classes", "class_keys"),
            ("studentInstructions", "student_instructions"),
            ("teacherNotes", "teacher_notes"),
            ("status", "status"),
            ("assignedAt", "assigned_at"),
            ("dueAt", "due_at"),
            ("sourceBookIds", "source_pack_ids"),
            ("scopeTopics", "scope_topics"),
            ("scopeTopicIds", "scope_topic_ids"),
            ("scopeRefinement", "scope_refinement"),
            ("generateWithoutSources", "generate_without_sources"),
            ("difficulty", "difficulty"),
            ("handoutLayout", "handout_layout"),
        ]
        for key, attr in mapping:
            if key in patch and patch[key] is not None:
                setattr(ws, attr, patch[key])
        if "scopeTopics" in patch or "scopeRefinement" in patch or "scopeTopicIds" in patch:
            ws.topic_summary = _topic_summary(list(ws.scope_topics or []), ws.scope_refinement)

        if not ws.generate_without_sources and (
            "scopeTopicIds" in patch or "scopeTopics" in patch or "sourceBookIds" in patch
        ):
            try:
                validate_sourced_scope(
                    self.db,
                    tenant_id=current_user.tenant_id,
                    generate_without_sources=False,
                    source_pack_ids=list(ws.source_pack_ids or []),
                    scope_topic_ids=list(ws.scope_topic_ids or []),
                )
            except SourcedScopeValidationError as e:
                raise validation_failed(e.message) from e

        ws.updated_at = datetime.now(timezone.utc)
        return self.repo.update_worksheet(ws)

    def delete_worksheet(self, *, current_user: User, worksheet_id: UUID) -> None:
        ws = self.repo.get_worksheet(current_user.tenant_id, worksheet_id, with_children=False)
        if not ws:
            raise not_found()
        self.repo.delete_worksheet(ws)

    def duplicate_worksheet(self, *, current_user: User, worksheet_id: UUID) -> TeacherWorksheet:
        ws = self.repo.get_worksheet(current_user.tenant_id, worksheet_id, with_children=True)
        if not ws:
            raise not_found()
        now = datetime.now(timezone.utc)
        return self.repo.duplicate_worksheet(source=ws, new_id=uuid4(), new_title=f"{ws.title} (copy)", now=now)

    def add_session(self, *, current_user: User, worksheet_id: UUID, title: str) -> TeacherWorksheet:
        ws = self.repo.get_worksheet(current_user.tenant_id, worksheet_id, with_children=True)
        if not ws:
            raise not_found()
        return self.repo.add_session(ws, title)

    def patch_session(
        self,
        *,
        current_user: User,
        worksheet_id: UUID,
        session_id: UUID,
        patch: Dict[str, Any],
    ) -> TeacherWorksheet:
        ws = self.repo.get_worksheet(current_user.tenant_id, worksheet_id, with_children=True)
        if not ws:
            raise not_found()
        session = self.repo.get_session(current_user.tenant_id, worksheet_id, session_id)
        if not session:
            raise not_found("Session not found")
        return self.repo.patch_session(ws, session, patch)

    def delete_session(self, *, current_user: User, worksheet_id: UUID, session_id: UUID) -> TeacherWorksheet:
        ws = self.repo.get_worksheet(current_user.tenant_id, worksheet_id, with_children=True)
        if not ws:
            raise not_found()
        if len(ws.sessions or []) <= 1:
            raise min_session()
        session = self.repo.get_session(current_user.tenant_id, worksheet_id, session_id)
        if not session:
            raise not_found("Session not found")
        return self.repo.delete_session(ws, session)

    def reorder_sessions(self, *, current_user: User, worksheet_id: UUID, order: List[Dict[str, Any]]) -> TeacherWorksheet:
        ws = self.repo.get_worksheet(current_user.tenant_id, worksheet_id, with_children=True)
        if not ws:
            raise not_found()
        return self.repo.reorder_sessions(ws, order)

    def add_block(
        self,
        *,
        current_user: User,
        worksheet_id: UUID,
        session_id: UUID,
        payload: Dict[str, Any],
    ) -> TeacherWorksheet:
        ws = self.repo.get_worksheet(current_user.tenant_id, worksheet_id, with_children=True)
        if not ws:
            raise not_found()
        session = self.repo.get_session(current_user.tenant_id, worksheet_id, session_id)
        if not session:
            raise not_found("Session not found")
        btype = str(payload.get("type") or "")
        if btype not in ("mcq", "fill_blank", "short", "match"):
            raise invalid_block_type()
        _validate_block_payload(btype, payload)
        data = _payload_to_block_data(btype, payload)
        prompt = payload.get("prompt")
        if btype == "match":
            prompt = None
        block = TeacherWorksheetBlock(
            id=uuid4(),
            worksheet_id=ws.id,
            session_id=session.id,
            sort_order=0,
            type=btype,
            prompt=prompt,
            points=float(payload.get("points") or 1.0),
            data=data,
        )
        return self.repo.add_block(ws, session, block)

    def patch_block(
        self,
        *,
        current_user: User,
        worksheet_id: UUID,
        session_id: UUID,
        block_id: UUID,
        patch: Dict[str, Any],
    ) -> TeacherWorksheet:
        ws = self.repo.get_worksheet(current_user.tenant_id, worksheet_id, with_children=True)
        if not ws:
            raise not_found()
        session = self.repo.get_session(current_user.tenant_id, worksheet_id, session_id)
        if not session:
            raise not_found("Session not found")
        block = self.repo.get_block(current_user.tenant_id, worksheet_id, session_id, block_id)
        if not block:
            raise not_found("Block not found")
        btype = block.type
        merged = {
            "options": (patch["options"] if "options" in patch else (block.data or {}).get("options")),
            "answer": (patch["answer"] if "answer" in patch else (block.data or {}).get("answer")),
            "sampleAnswer": (patch["sampleAnswer"] if "sampleAnswer" in patch else (block.data or {}).get("sample_answer")),
            "responseLines": (
                patch["responseLines"] if "responseLines" in patch else (block.data or {}).get("response_lines")
            ),
            "left": (patch["left"] if "left" in patch else (block.data or {}).get("left")),
            "right": (patch["right"] if "right" in patch else (block.data or {}).get("right")),
        }
        payload = {
            "type": btype,
            "prompt": patch.get("prompt", block.prompt),
            "points": patch.get("points", block.points),
            "options": merged["options"],
            "answer": merged["answer"],
            "sampleAnswer": merged["sampleAnswer"],
            "responseLines": merged["responseLines"],
            "left": merged["left"],
            "right": merged["right"],
        }
        _validate_block_payload(btype, payload)
        new_data = _payload_to_block_data(btype, payload)
        new_prompt = patch.get("prompt", block.prompt)
        if btype == "match":
            new_prompt = None
        data_patch = {
            "prompt": new_prompt,
            "points": float(patch["points"]) if "points" in patch and patch["points"] is not None else block.points,
            "data": new_data,
        }
        return self.repo.patch_block(ws, block, data_patch)

    def delete_block(self, *, current_user: User, worksheet_id: UUID, session_id: UUID, block_id: UUID) -> TeacherWorksheet:
        ws = self.repo.get_worksheet(current_user.tenant_id, worksheet_id, with_children=True)
        if not ws:
            raise not_found()
        if _total_blocks(ws) <= 1:
            raise min_block()
        block = self.repo.get_block(current_user.tenant_id, worksheet_id, session_id, block_id)
        if not block:
            raise not_found("Block not found")
        return self.repo.delete_block(ws, block)

    def reorder_blocks(
        self,
        *,
        current_user: User,
        worksheet_id: UUID,
        session_id: UUID,
        order: List[Dict[str, Any]],
    ) -> TeacherWorksheet:
        ws = self.repo.get_worksheet(current_user.tenant_id, worksheet_id, with_children=True)
        if not ws:
            raise not_found()
        session = self.repo.get_session(current_user.tenant_id, worksheet_id, session_id)
        if not session:
            raise not_found("Session not found")
        return self.repo.reorder_blocks(ws, session, order)

    async def regenerate_block(
        self,
        *,
        current_user: User,
        worksheet_id: UUID,
        session_id: UUID,
        block_id: UUID,
    ) -> TeacherWorksheet:
        ws = self.repo.get_worksheet(current_user.tenant_id, worksheet_id, with_children=True)
        if not ws:
            raise not_found()
        block = self.repo.get_block(current_user.tenant_id, worksheet_id, session_id, block_id)
        if not block:
            raise not_found("Block not found")
        btype = block.type
        if btype not in ("mcq", "fill_blank", "short", "match"):
            raise invalid_block_type()

        context_text = ""
        if not ws.generate_without_sources:
            context_text, _, _, _ = _worksheet_retrieval(
                self,
                worksheet=ws,
                tenant_id=current_user.tenant_id,
                max_chunks=8,
            )

        avoid = _worksheet_existing_signatures(ws)

        timeout_s = float(getattr(settings, "QUIZ_GENERATION_TIMEOUT_SECONDS", 180.0))
        try:
            gen = await asyncio.wait_for(
                self.generator.regenerate_block(
                    block_type=btype,
                    subject=ws.subject,
                    grade=ws.grade,
                    topic_label=ws.topic_summary or "General scope",
                    difficulty=ws.difficulty,
                    teacher_notes=ws.teacher_notes,
                    retrieved_chunks=context_text,
                    avoid_prompts=avoid,
                ),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError as e:
            raise generation_timeout() from e
        except Exception as e:
            raise generation_failed("Block regeneration failed") from e

        data = _block_data_from_generated(gen)
        new_prompt = gen.prompt if btype != "match" else None
        block.prompt = new_prompt
        block.points = float(gen.points or 1.0)
        block.data = data
        self.db.add(block)
        self.db.commit()
        self.repo._update_denorm_counts(ws.tenant_id, ws.id)
        return self.repo.get_worksheet(current_user.tenant_id, worksheet_id) or ws

    async def generate_for_worksheet(
        self,
        *,
        current_user: User,
        worksheet_id: UUID,
        req: Dict[str, Any],
        idempotency_key: Optional[str],
    ) -> Tuple[TeacherWorksheetGenerationRun, TeacherWorksheet, List[str]]:
        ws = self.repo.get_worksheet(current_user.tenant_id, worksheet_id, with_children=True)
        if not ws:
            raise not_found()

        if idempotency_key:
            prior = self.repo.find_generation_run_by_idempotency(ws.id, idempotency_key)
            if prior and prior.status == "completed":
                fresh = self.repo.get_worksheet(current_user.tenant_id, worksheet_id, with_children=True)
                if not fresh:
                    raise not_found()
                return prior, fresh, list(prior.retrieval_warnings or [])

        difficulty = req.get("difficulty") or ws.difficulty
        teacher_notes = req.get("teacherNotes") or ws.teacher_notes
        question_count = int(req.get("questionCount") or 10)
        mix_mode = str(req.get("mixMode") or "balanced")
        include_mcq = bool(req.get("includeMcq", True))
        include_fill_blank = bool(req.get("includeFillBlank", True))
        include_short = bool(req.get("includeShort", True))
        include_match = bool(req.get("includeMatch", True))
        counts_by_type = req.get("countsByType")

        context_text = ""
        citations: List[Dict[str, str]] = []
        retrieval_warnings: List[str] = []
        retrieval_meta: Dict[str, Any] = {}

        if not ws.generate_without_sources:
            context_text, citations, retrieval_warnings, retrieval_meta = _worksheet_retrieval(
                self,
                worksheet=ws,
                tenant_id=current_user.tenant_id,
                max_chunks=18,
            )
        else:
            retrieval_warnings.append("Generation without sources (grounding off).")

        timeout_s = float(getattr(settings, "QUIZ_GENERATION_TIMEOUT_SECONDS", 180.0))
        input_payload = {
            "worksheet_id": str(ws.id),
            "subject": ws.subject,
            "grade": ws.grade,
            "topic": ws.topic_summary or _topic_summary(list(ws.scope_topics or []), ws.scope_refinement),
            "difficulty": difficulty,
            "questionCount": question_count,
            "mixMode": mix_mode,
            "includeMcq": include_mcq,
            "includeFillBlank": include_fill_blank,
            "includeShort": include_short,
            "includeMatch": include_match,
            "countsByType": counts_by_type,
            "teacherNotes": teacher_notes or "",
            "grounded": not ws.generate_without_sources,
        }
        input_hash = self.generator.build_input_hash(input_payload)

        try:
            # Full-sheet replace: do not pass prior block text as avoid — same topic legitimately
            # reuses vocabulary and caused false positives + stub placeholders. Within-batch
            # uniqueness is enforced in WorksheetGenerationService.generate_blocks (salvage path).
            gen_blocks, gen_warnings, gen_meta = await asyncio.wait_for(
                self.generator.generate_blocks(
                    subject=ws.subject,
                    grade=ws.grade,
                    topic_label=ws.topic_summary or input_payload["topic"],
                    difficulty=difficulty,
                    question_count=question_count,
                    mix_mode=mix_mode,
                    include_mcq=include_mcq,
                    include_fill_blank=include_fill_blank,
                    include_short=include_short,
                    include_match=include_match,
                    counts_by_type=counts_by_type,
                    teacher_notes=teacher_notes,
                    retrieved_chunks=context_text,
                    avoid_prompts=[],
                ),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError as e:
            run = TeacherWorksheetGenerationRun(
                worksheet_id=ws.id,
                scope="all",
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
            run = TeacherWorksheetGenerationRun(
                worksheet_id=ws.id,
                scope="all",
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
            raise generation_failed("Worksheet generation failed") from e

        warnings = retrieval_warnings + gen_warnings
        llm_model = gen_meta.get("model_used")

        sessions_sorted = sorted(ws.sessions or [], key=lambda s: s.sort_order)
        if not sessions_sorted:
            first = TeacherWorksheetSession(
                id=uuid4(),
                worksheet_id=ws.id,
                sort_order=0,
                title="Session 1",
            )
            self.db.add(first)
            self.db.commit()
            self.db.refresh(ws)
            ws = self.repo.get_worksheet(current_user.tenant_id, worksheet_id, with_children=True) or ws
            sessions_sorted = sorted(ws.sessions or [], key=lambda s: s.sort_order)

        first_session = sessions_sorted[0]
        db_blocks: List[TeacherWorksheetBlock] = []
        for i, g in enumerate(gen_blocks):
            db_blocks.append(
                TeacherWorksheetBlock(
                    id=uuid4(),
                    worksheet_id=ws.id,
                    session_id=first_session.id,
                    sort_order=i,
                    type=g.btype,
                    prompt=None if g.btype == "match" else g.prompt,
                    points=float(g.points or 1.0),
                    data=_block_data_from_generated(g),
                )
            )

        ws = self.repo.replace_session_blocks(ws, first_session, db_blocks)
        ws.difficulty = difficulty or ws.difficulty
        if teacher_notes is not None:
            ws.teacher_notes = teacher_notes
        ws.topic_summary = ws.topic_summary or input_payload["topic"]
        ws.content_version = int(ws.content_version or 1) + 1
        ws.updated_at = datetime.now(timezone.utc)
        self.repo.update_worksheet(ws)

        run = TeacherWorksheetGenerationRun(
            worksheet_id=ws.id,
            scope="all",
            status="completed",
            input_hash=input_hash,
            idempotency_key=idempotency_key,
            retrieval_warnings=warnings,
            retrieval_metadata={"citations": citations, **retrieval_meta, "llm": gen_meta},
            llm_model=str(llm_model) if llm_model else None,
        )
        run = self.repo.create_generation_run(run)
        ws = self.repo.get_worksheet(current_user.tenant_id, worksheet_id, with_children=True) or ws

        logger.info(
            "worksheet_generated",
            extra={
                "tenant_id": str(current_user.tenant_id),
                "worksheet_id": str(ws.id),
                "blocks": ws.blocks_count,
            },
        )
        return run, ws, warnings
