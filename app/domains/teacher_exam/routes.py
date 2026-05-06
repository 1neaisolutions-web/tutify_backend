"""
Teacher Tools exam HTTP routes.
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.session import get_db
from app.domains.auth.dependencies import require_any_role
from app.domains.auth.models import User
from app.domains.teacher_exam.errors import ExamError
from app.domains.teacher_exam.models import TeacherExam
from app.domains.teacher_exam.repository import ExamListFilters
from app.domains.teacher_exam.schemas import (
    DuplicateResponse,
    ExamApiResponse,
    ExamCreateRequest,
    ExamGenerateRequest,
    ExamGenerateResponse,
    ExamListResponse,
    ExamLongCreateRequest,
    ExamLongPatchRequest,
    ExamMcqCreateRequest,
    ExamMcqPatchRequest,
    ExamPaperConfigSchema,
    ExamPatchRequest,
    ExamQuestionsReorderRequest,
    ExamSectionResponse,
    ExamShortCreateRequest,
    ExamShortPatchRequest,
    ExamMcqResponse,
    ExamShortResponse,
    ExamLongResponse,
)
from app.domains.teacher_exam.service import TeacherExamService, _source_summary
from app.domains.subscriptions.credit_errors import insufficient_credits_detail
from app.domains.subscriptions.feature_keys import (
    EXAM_GENERATE,
    EXAM_REGENERATE_LONG,
    EXAM_REGENERATE_MCQ,
    EXAM_REGENERATE_SHORT,
)
from app.domains.subscriptions.services.credit_service import CreditService
from app.domains.subscriptions.services.subscription_service import SubscriptionService
from app.domains.user_history.quota_service import check_and_enforce

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/teacher-tools/exams", tags=["teacher-exam"])

_ALLOWED_ROLES = ("teacher", "school_admin", "super_admin", "org_admin")


def _to_exam_response(e: TeacherExam) -> ExamApiResponse:
    mcqs = [q for q in (e.questions or []) if q.question_type == "mcq"]
    shorts = [q for q in (e.questions or []) if q.question_type == "short"]
    longs = [q for q in (e.questions or []) if q.question_type == "long"]

    paper_raw = e.paper_config or {}
    try:
        paper = ExamPaperConfigSchema.model_validate(paper_raw)
    except Exception:
        paper = ExamPaperConfigSchema()

    return ExamApiResponse(
        id=str(e.id),
        title=e.title,
        subject=e.subject,
        grade=e.grade,
        examType=e.exam_type,
        term=e.term,
        internationalStandard=e.international_standard,
        durationMinutes=int(e.duration_minutes or 60),
        totalMarks=float(e.total_marks or 0.0),
        scheduleStart=e.schedule_start,
        scheduleEnd=e.schedule_end,
        classes=list(e.class_keys or []),
        status=e.status,  # type: ignore[arg-type]
        completionPct=float(e.completion_pct or 0.0),
        sectionTargetCount=int(e.section_target_count or 4),
        sourceBookIds=[str(x) for x in (e.source_pack_ids or [])],
        scopeTopics=list(e.scope_topics or []),
        scopeRefinement=e.scope_refinement,
        sourceSummary=_source_summary(e),
        generateWithoutSources=bool(e.generate_without_sources),
        paper=paper,
        sections=[
            ExamSectionResponse(
                id=str(s.id),
                sortOrder=s.sort_order,
                title=s.title,
                marks=float(s.marks),
                description=s.description,
            )
            for s in sorted(e.sections or [], key=lambda x: x.sort_order)
        ],
        mcqs=[
            ExamMcqResponse(
                id=str(q.id),
                sortOrder=q.sort_order,
                stem=q.stem,
                options=list(q.options or []),
                marksPer=float(q.marks_per),
            )
            for q in sorted(mcqs, key=lambda x: x.sort_order)
        ],
        shorts=[
            ExamShortResponse(
                id=str(q.id),
                sortOrder=q.sort_order,
                stem=q.stem,
                marksPer=float(q.marks_per),
            )
            for q in sorted(shorts, key=lambda x: x.sort_order)
        ],
        longs=[
            ExamLongResponse(
                id=str(q.id),
                sortOrder=q.sort_order,
                stem=q.stem,
                subparts=list(q.subparts or []),
                marksPer=float(q.marks_per),
            )
            for q in sorted(longs, key=lambda x: x.sort_order)
        ],
        handoutLayout=e.handout_layout,
        studentInstructions=e.student_instructions,
        teacherNotes=e.teacher_notes,
        createdAt=e.created_at,
        updatedAt=e.updated_at,
    )


def _raise_domain_error(e: ExamError) -> None:
    raise HTTPException(status_code=e.http_status, detail={"code": e.code, "message": e.message})


@router.get("/", response_model=ExamListResponse)
def list_exams(
    q: Optional[str] = None,
    subject: Optional[str] = None,
    grade: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    class_key: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    exam_type: Optional[str] = None,
    term: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
) -> ExamListResponse:
    svc = TeacherExamService(db)
    items, total = svc.list_exams(
        current_user=current_user,
        filters=ExamListFilters(
            q=q,
            subject=subject,
            grade=grade,
            status=status_filter,
            class_key=class_key,
            date_from=date_from,
            date_to=date_to,
            exam_type=exam_type,
            term=term,
        ),
        page=page,
        page_size=page_size,
    )
    return ExamListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[_to_exam_response(x) for x in items],
    )


@router.post("/", response_model=ExamApiResponse, status_code=status.HTTP_201_CREATED)
def create_exam(
    body: ExamCreateRequest,
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
    response: Response = None,  # type: ignore[assignment]
) -> ExamApiResponse:
    quota = None
    if response is not None:
        tier = SubscriptionService(db).get_user_tier(current_user.id).value
        quota = check_and_enforce(db, user_id=str(current_user.id), source_type="exam", tier=tier)
    svc = TeacherExamService(db)
    exam = svc.create_exam(current_user=current_user, payload=body.model_dump())
    if response is not None and quota is not None:
        response.headers["X-History-Warning-Level"] = quota.warning_level
        response.headers["X-History-Count"] = str(quota.current_count + 1)
        response.headers["X-History-Limit"] = str(quota.limit)
        if quota.evicted_id:
            response.headers["X-History-Eviction-Title"] = quota.evicted_title or ""
            response.headers["X-History-Eviction-Type"] = "exam"
    return _to_exam_response(exam)


@router.get("/{exam_id}", response_model=ExamApiResponse)
def get_exam(
    exam_id: UUID,
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
) -> ExamApiResponse:
    svc = TeacherExamService(db)
    try:
        exam = svc.get_exam(current_user=current_user, exam_id=exam_id)
        return _to_exam_response(exam)
    except ExamError as e:
        _raise_domain_error(e)
        raise


@router.patch("/{exam_id}", response_model=ExamApiResponse)
def patch_exam(
    exam_id: UUID,
    body: ExamPatchRequest,
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
) -> ExamApiResponse:
    svc = TeacherExamService(db)
    try:
        exam = svc.patch_exam(current_user=current_user, exam_id=exam_id, patch=body.model_dump(exclude_unset=True))
        return _to_exam_response(exam)
    except ExamError as e:
        _raise_domain_error(e)
        raise


@router.delete("/{exam_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_exam(
    exam_id: UUID,
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
) -> Response:
    svc = TeacherExamService(db)
    try:
        svc.delete_exam(current_user=current_user, exam_id=exam_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ExamError as e:
        _raise_domain_error(e)
        raise


@router.post("/{exam_id}/duplicate", response_model=DuplicateResponse)
def duplicate_exam(
    exam_id: UUID,
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
) -> DuplicateResponse:
    svc = TeacherExamService(db)
    try:
        copy = svc.duplicate_exam(current_user=current_user, exam_id=exam_id)
        return DuplicateResponse(ok=True, id=str(copy.id))
    except ExamError as e:
        _raise_domain_error(e)
        raise


@router.post("/{exam_id}/generate", response_model=ExamGenerateResponse)
async def generate_exam(
    exam_id: UUID,
    body: ExamGenerateRequest,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
) -> ExamGenerateResponse:
    credit_service = CreditService(db)
    check = credit_service.check_balance(current_user.id)
    cost = credit_service.get_feature_cost(EXAM_GENERATE)
    if not check.allowed or check.balance < cost:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=insufficient_credits_detail(
                check,
                cost,
                "You don't have enough credits to generate an exam.",
            ),
        )

    svc = TeacherExamService(db)
    try:
        run, exam, warnings = await svc.generate_full_exam(
            current_user=current_user,
            exam_id=exam_id,
            req=body.model_dump(),
            idempotency_key=idempotency_key,
        )
        try:
            credit_service.charge(
                user_id=current_user.id,
                feature_key=EXAM_GENERATE,
                description=f"Exam generation · {exam.title or exam_id}",
                metadata={
                    "exam_id": str(exam_id),
                    "generation_run_id": str(run.id),
                },
            )
        except Exception:
            logger.exception("credit_charge_failed", extra={"feature_key": EXAM_GENERATE})
        return ExamGenerateResponse(
            ok=True,
            generation_run_id=str(run.id),
            warnings=list(warnings),
            exam=_to_exam_response(exam),
        )
    except ExamError as e:
        _raise_domain_error(e)
        raise
    except Exception as e:
        logger.error("exam_generate_unexpected", exc_info=True)
        raise HTTPException(status_code=500, detail={"code": "INTERNAL_ERROR", "message": str(e)})


@router.post("/{exam_id}/questions/mcq", response_model=ExamApiResponse, status_code=status.HTTP_201_CREATED)
def add_mcq(
    exam_id: UUID,
    body: ExamMcqCreateRequest,
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
) -> ExamApiResponse:
    svc = TeacherExamService(db)
    try:
        exam = svc.add_mcq(current_user=current_user, exam_id=exam_id, payload=body.model_dump())
        return _to_exam_response(exam)
    except ExamError as e:
        _raise_domain_error(e)
        raise


@router.post("/{exam_id}/questions/short", response_model=ExamApiResponse, status_code=status.HTTP_201_CREATED)
def add_short(
    exam_id: UUID,
    body: ExamShortCreateRequest,
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
) -> ExamApiResponse:
    svc = TeacherExamService(db)
    try:
        exam = svc.add_short(current_user=current_user, exam_id=exam_id, payload=body.model_dump())
        return _to_exam_response(exam)
    except ExamError as e:
        _raise_domain_error(e)
        raise


@router.post("/{exam_id}/questions/long", response_model=ExamApiResponse, status_code=status.HTTP_201_CREATED)
def add_long(
    exam_id: UUID,
    body: ExamLongCreateRequest,
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
) -> ExamApiResponse:
    svc = TeacherExamService(db)
    try:
        exam = svc.add_long(current_user=current_user, exam_id=exam_id, payload=body.model_dump())
        return _to_exam_response(exam)
    except ExamError as e:
        _raise_domain_error(e)
        raise


@router.patch("/{exam_id}/questions/mcq/reorder", response_model=ExamApiResponse)
def reorder_mcq(
    exam_id: UUID,
    body: ExamQuestionsReorderRequest,
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
) -> ExamApiResponse:
    svc = TeacherExamService(db)
    try:
        exam = svc.reorder_questions(
            current_user=current_user,
            exam_id=exam_id,
            question_type="mcq",
            order=[item.model_dump() for item in body.order],
        )
        return _to_exam_response(exam)
    except ExamError as e:
        _raise_domain_error(e)
        raise


@router.patch("/{exam_id}/questions/short/reorder", response_model=ExamApiResponse)
def reorder_short(
    exam_id: UUID,
    body: ExamQuestionsReorderRequest,
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
) -> ExamApiResponse:
    svc = TeacherExamService(db)
    try:
        exam = svc.reorder_questions(
            current_user=current_user,
            exam_id=exam_id,
            question_type="short",
            order=[item.model_dump() for item in body.order],
        )
        return _to_exam_response(exam)
    except ExamError as e:
        _raise_domain_error(e)
        raise


@router.patch("/{exam_id}/questions/long/reorder", response_model=ExamApiResponse)
def reorder_long(
    exam_id: UUID,
    body: ExamQuestionsReorderRequest,
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
) -> ExamApiResponse:
    svc = TeacherExamService(db)
    try:
        exam = svc.reorder_questions(
            current_user=current_user,
            exam_id=exam_id,
            question_type="long",
            order=[item.model_dump() for item in body.order],
        )
        return _to_exam_response(exam)
    except ExamError as e:
        _raise_domain_error(e)
        raise


@router.patch("/{exam_id}/questions/mcq/{question_id}", response_model=ExamApiResponse)
def patch_mcq(
    exam_id: UUID,
    question_id: UUID,
    body: ExamMcqPatchRequest,
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
) -> ExamApiResponse:
    svc = TeacherExamService(db)
    try:
        exam = svc.patch_mcq(
            current_user=current_user,
            exam_id=exam_id,
            question_id=question_id,
            patch=body.model_dump(exclude_unset=True),
        )
        return _to_exam_response(exam)
    except ExamError as e:
        _raise_domain_error(e)
        raise


@router.patch("/{exam_id}/questions/short/{question_id}", response_model=ExamApiResponse)
def patch_short(
    exam_id: UUID,
    question_id: UUID,
    body: ExamShortPatchRequest,
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
) -> ExamApiResponse:
    svc = TeacherExamService(db)
    try:
        exam = svc.patch_short(
            current_user=current_user,
            exam_id=exam_id,
            question_id=question_id,
            patch=body.model_dump(exclude_unset=True),
        )
        return _to_exam_response(exam)
    except ExamError as e:
        _raise_domain_error(e)
        raise


@router.patch("/{exam_id}/questions/long/{question_id}", response_model=ExamApiResponse)
def patch_long(
    exam_id: UUID,
    question_id: UUID,
    body: ExamLongPatchRequest,
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
) -> ExamApiResponse:
    svc = TeacherExamService(db)
    try:
        exam = svc.patch_long(
            current_user=current_user,
            exam_id=exam_id,
            question_id=question_id,
            patch=body.model_dump(exclude_unset=True),
        )
        return _to_exam_response(exam)
    except ExamError as e:
        _raise_domain_error(e)
        raise


@router.delete("/{exam_id}/questions/mcq/{question_id}", response_model=ExamApiResponse)
def delete_mcq(
    exam_id: UUID,
    question_id: UUID,
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
) -> ExamApiResponse:
    svc = TeacherExamService(db)
    try:
        exam = svc.delete_mcq(current_user=current_user, exam_id=exam_id, question_id=question_id)
        return _to_exam_response(exam)
    except ExamError as e:
        _raise_domain_error(e)
        raise


@router.delete("/{exam_id}/questions/short/{question_id}", response_model=ExamApiResponse)
def delete_short(
    exam_id: UUID,
    question_id: UUID,
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
) -> ExamApiResponse:
    svc = TeacherExamService(db)
    try:
        exam = svc.delete_short(current_user=current_user, exam_id=exam_id, question_id=question_id)
        return _to_exam_response(exam)
    except ExamError as e:
        _raise_domain_error(e)
        raise


@router.delete("/{exam_id}/questions/long/{question_id}", response_model=ExamApiResponse)
def delete_long(
    exam_id: UUID,
    question_id: UUID,
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
) -> ExamApiResponse:
    svc = TeacherExamService(db)
    try:
        exam = svc.delete_long(current_user=current_user, exam_id=exam_id, question_id=question_id)
        return _to_exam_response(exam)
    except ExamError as e:
        _raise_domain_error(e)
        raise


@router.post("/{exam_id}/questions/mcq/{question_id}/regenerate", response_model=ExamApiResponse)
async def regenerate_mcq(
    exam_id: UUID,
    question_id: UUID,
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
) -> ExamApiResponse:
    credit_service = CreditService(db)
    check = credit_service.check_balance(current_user.id)
    cost = credit_service.get_feature_cost(EXAM_REGENERATE_MCQ)
    if not check.allowed or check.balance < cost:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=insufficient_credits_detail(
                check,
                cost,
                "You don't have enough credits to regenerate this question.",
            ),
        )

    svc = TeacherExamService(db)
    try:
        exam = await svc.regenerate_mcq(current_user=current_user, exam_id=exam_id, question_id=question_id)
        try:
            credit_service.charge(
                user_id=current_user.id,
                feature_key=EXAM_REGENERATE_MCQ,
                description="Exam · regenerate MCQ",
                metadata={"exam_id": str(exam_id), "question_id": str(question_id)},
            )
        except Exception:
            logger.exception(
                "credit_charge_failed",
                extra={"feature_key": EXAM_REGENERATE_MCQ},
            )
        return _to_exam_response(exam)
    except ExamError as e:
        _raise_domain_error(e)
        raise
    except Exception as e:
        logger.error("exam_regen_mcq_unexpected", exc_info=True)
        raise HTTPException(status_code=500, detail={"code": "INTERNAL_ERROR", "message": str(e)})


@router.post("/{exam_id}/questions/short/{question_id}/regenerate", response_model=ExamApiResponse)
async def regenerate_short(
    exam_id: UUID,
    question_id: UUID,
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
) -> ExamApiResponse:
    credit_service = CreditService(db)
    check = credit_service.check_balance(current_user.id)
    cost = credit_service.get_feature_cost(EXAM_REGENERATE_SHORT)
    if not check.allowed or check.balance < cost:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=insufficient_credits_detail(
                check,
                cost,
                "You don't have enough credits to regenerate this question.",
            ),
        )

    svc = TeacherExamService(db)
    try:
        exam = await svc.regenerate_short(current_user=current_user, exam_id=exam_id, question_id=question_id)
        try:
            credit_service.charge(
                user_id=current_user.id,
                feature_key=EXAM_REGENERATE_SHORT,
                description="Exam · regenerate short answer",
                metadata={"exam_id": str(exam_id), "question_id": str(question_id)},
            )
        except Exception:
            logger.exception(
                "credit_charge_failed",
                extra={"feature_key": EXAM_REGENERATE_SHORT},
            )
        return _to_exam_response(exam)
    except ExamError as e:
        _raise_domain_error(e)
        raise
    except Exception as e:
        logger.error("exam_regen_short_unexpected", exc_info=True)
        raise HTTPException(status_code=500, detail={"code": "INTERNAL_ERROR", "message": str(e)})


@router.post("/{exam_id}/questions/long/{question_id}/regenerate", response_model=ExamApiResponse)
async def regenerate_long_route(
    exam_id: UUID,
    question_id: UUID,
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
) -> ExamApiResponse:
    credit_service = CreditService(db)
    check = credit_service.check_balance(current_user.id)
    cost = credit_service.get_feature_cost(EXAM_REGENERATE_LONG)
    if not check.allowed or check.balance < cost:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=insufficient_credits_detail(
                check,
                cost,
                "You don't have enough credits to regenerate this question.",
            ),
        )

    svc = TeacherExamService(db)
    try:
        exam = await svc.regenerate_long(current_user=current_user, exam_id=exam_id, question_id=question_id)
        try:
            credit_service.charge(
                user_id=current_user.id,
                feature_key=EXAM_REGENERATE_LONG,
                description="Exam · regenerate long answer",
                metadata={"exam_id": str(exam_id), "question_id": str(question_id)},
            )
        except Exception:
            logger.exception(
                "credit_charge_failed",
                extra={"feature_key": EXAM_REGENERATE_LONG},
            )
        return _to_exam_response(exam)
    except ExamError as e:
        _raise_domain_error(e)
        raise
    except Exception as e:
        logger.error("exam_regen_long_unexpected", exc_info=True)
        raise HTTPException(status_code=500, detail={"code": "INTERNAL_ERROR", "message": str(e)})
