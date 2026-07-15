"""
Teacher Tools Quiz HTTP routes.

These routes are designed so the existing frontend UI can be wired to them
without changing UI structure (responses are DemoQuiz-shaped).
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.session import get_db
from app.domains.auth.dependencies import require_any_role
from app.domains.auth.models import User
from app.domains.teacher_quiz.errors import QuizError
from app.domains.teacher_quiz.models import TeacherQuiz
from app.domains.teacher_quiz.repository import QuizListFilters
from app.domains.teacher_quiz.schemas import (
    DuplicateResponse,
    GenerateResponse,
    QuizCreateRequest,
    QuizGenerateRequest,
    QuizListResponse,
    QuizPatchRequest,
    QuizQuestionCreateRequest,
    QuizQuestionPatchRequest,
    QuizQuestionsReorderRequest,
    QuizResponse,
)
from app.domains.teacher_quiz.service import TeacherQuizService
from app.domains.subscriptions.credit_errors import insufficient_credits_detail
from app.domains.subscriptions.feature_keys import QUIZ_GENERATE, QUIZ_REGENERATE_QUESTION
from app.domains.subscriptions.services.credit_service import CreditService
from app.domains.subscriptions.services.subscription_service import SubscriptionService
from app.domains.user_history.quota_service import check_and_enforce

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/teacher-tools", tags=["teacher-quiz"])

_ALLOWED_ROLES = ("teacher", "school_admin", "super_admin", "org_admin")


def _topic_for_response(q: TeacherQuiz) -> str:
    return q.topic_summary or "General scope"


def _source_summary(q: TeacherQuiz) -> Optional[str]:
    if q.generate_without_sources:
        return "Generation without catalog retrieval (grounding off)"
    pack_count = len(q.source_pack_ids or [])
    topic_count = len(q.scope_topics or [])
    refine = " · scope hint applied" if (q.scope_refinement or "").strip() else ""
    return f"Catalog retrieval · {pack_count} source{'s' if pack_count != 1 else ''} · {topic_count} topic strand{'s' if topic_count != 1 else ''}{refine}"


def _to_quiz_response(q: TeacherQuiz) -> QuizResponse:
    stubs = []
    for row in (q.questions or []):
        stub = {
            "id": str(row.id),
            "type": row.type,
            "prompt": row.prompt,
            "points": row.points,
        }
        if row.options is not None:
            stub["options"] = row.options
        if row.response_lines is not None:
            stub["response_lines"] = row.response_lines
        if row.extra and isinstance(row.extra, dict):
            rb = row.extra.get("reviewBadges")
            if isinstance(rb, dict):
                stub["reviewBadges"] = rb
        stubs.append(stub)

    return QuizResponse(
        id=str(q.id),
        title=q.title,
        subject=q.subject,
        grade=q.grade,
        classes=list(q.class_keys or []),
        questions=int(q.questions_count or len(stubs)),
        totalMarks=float(q.total_marks or 0.0),
        timeLimitMinutes=int(q.time_limit_minutes or 30),
        status=q.status,  # type: ignore[arg-type]
        assignedAt=q.assigned_at,
        dueAt=q.due_at,
        createdAt=q.created_at,
        updatedAt=q.updated_at,
        submissionCount=int(q.submission_count or 0),
        avgScore=float(q.avg_score or 0.0),
        topic=_topic_for_response(q),
        sourceBookIds=[str(x) for x in (q.source_pack_ids or [])],
        scopeTopics=list(q.scope_topics or []),
        scopeTopicIds=[str(x) for x in (q.scope_topic_ids or [])],
        scopeRefinement=q.scope_refinement,
        sourceSummary=_source_summary(q),
        questionStubs=stubs,  # type: ignore[arg-type]
        studentInstructions=q.student_instructions,
        difficulty=q.difficulty,
        shuffleQuestions=q.shuffle_questions,
        shuffleAnswers=q.shuffle_answers,
        negativeMarking=q.negative_marking,
        handoutLayout=q.handout_layout,
    )


def _raise_domain_error(e: QuizError) -> None:
    detail: dict = {"code": e.code, "message": e.message}
    if e.extra:
        detail.update(e.extra)
    raise HTTPException(status_code=e.http_status, detail=detail)


@router.get("/quizzes", response_model=QuizListResponse)
def list_quizzes(
    q: Optional[str] = None,
    subject: Optional[str] = None,
    grade: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    class_key: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
) -> QuizListResponse:
    svc = TeacherQuizService(db)
    items, total = svc.list_quizzes(
        current_user=current_user,
        filters=QuizListFilters(
            q=q,
            subject=subject,
            grade=grade,
            status=status_filter,
            class_key=class_key,
            date_from=date_from,
            date_to=date_to,
        ),
        page=page,
        page_size=page_size,
    )
    return QuizListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[_to_quiz_response(x) for x in items],
    )


@router.post("/quizzes", response_model=QuizResponse, status_code=status.HTTP_201_CREATED)
def create_quiz(
    body: QuizCreateRequest,
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
    response: Response = None,  # type: ignore[assignment]
) -> QuizResponse:
    quota = None
    if response is not None:
        tier = SubscriptionService(db).get_user_tier(current_user.id).value
        quota = check_and_enforce(db, user_id=str(current_user.id), source_type="quiz", tier=tier)
    svc = TeacherQuizService(db)
    quiz = svc.create_quiz(current_user=current_user, payload=body.model_dump())
    if response is not None and quota is not None:
        response.headers["X-History-Warning-Level"] = quota.warning_level
        response.headers["X-History-Count"] = str(quota.current_count + 1)
        response.headers["X-History-Limit"] = str(quota.limit)
        if quota.evicted_id:
            response.headers["X-History-Eviction-Title"] = quota.evicted_title or ""
            response.headers["X-History-Eviction-Type"] = "quiz"
    return _to_quiz_response(quiz)


@router.get("/quizzes/{quiz_id}", response_model=QuizResponse)
def get_quiz(
    quiz_id: UUID,
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
) -> QuizResponse:
    svc = TeacherQuizService(db)
    try:
        quiz = svc.get_quiz(current_user=current_user, quiz_id=quiz_id)
        return _to_quiz_response(quiz)
    except QuizError as e:
        _raise_domain_error(e)
        raise


@router.patch("/quizzes/{quiz_id}", response_model=QuizResponse)
def patch_quiz(
    quiz_id: UUID,
    body: QuizPatchRequest,
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
) -> QuizResponse:
    svc = TeacherQuizService(db)
    try:
        quiz = svc.patch_quiz(current_user=current_user, quiz_id=quiz_id, patch=body.model_dump(exclude_unset=True))
        return _to_quiz_response(quiz)
    except QuizError as e:
        _raise_domain_error(e)
        raise


@router.delete("/quizzes/{quiz_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_quiz(
    quiz_id: UUID,
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
) -> Response:
    svc = TeacherQuizService(db)
    try:
        svc.delete_quiz(current_user=current_user, quiz_id=quiz_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except QuizError as e:
        _raise_domain_error(e)
        raise


@router.post("/quizzes/{quiz_id}/duplicate", response_model=DuplicateResponse)
def duplicate_quiz(
    quiz_id: UUID,
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
) -> DuplicateResponse:
    svc = TeacherQuizService(db)
    try:
        copy = svc.duplicate_quiz(current_user=current_user, quiz_id=quiz_id)
        return DuplicateResponse(ok=True, id=str(copy.id))
    except QuizError as e:
        _raise_domain_error(e)
        raise


@router.post(
    "/quizzes/{quiz_id}/questions",
    response_model=QuizResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_question(
    quiz_id: UUID,
    body: QuizQuestionCreateRequest,
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
) -> QuizResponse:
    svc = TeacherQuizService(db)
    try:
        quiz = svc.add_question(
            current_user=current_user,
            quiz_id=quiz_id,
            payload=body.model_dump(),
        )
        return _to_quiz_response(quiz)
    except QuizError as e:
        _raise_domain_error(e)
        raise


@router.patch(
    "/quizzes/{quiz_id}/questions/reorder",
    response_model=QuizResponse,
)
def reorder_questions(
    quiz_id: UUID,
    body: QuizQuestionsReorderRequest,
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
) -> QuizResponse:
    svc = TeacherQuizService(db)
    try:
        quiz = svc.reorder_questions(
            current_user=current_user,
            quiz_id=quiz_id,
            order=[item.model_dump() for item in body.order],
        )
        return _to_quiz_response(quiz)
    except QuizError as e:
        _raise_domain_error(e)
        raise


@router.patch(
    "/quizzes/{quiz_id}/questions/{question_id}",
    response_model=QuizResponse,
)
def patch_question(
    quiz_id: UUID,
    question_id: UUID,
    body: QuizQuestionPatchRequest,
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
) -> QuizResponse:
    svc = TeacherQuizService(db)
    try:
        quiz = svc.patch_question(
            current_user=current_user,
            quiz_id=quiz_id,
            question_id=question_id,
            patch=body.model_dump(exclude_unset=True),
        )
        return _to_quiz_response(quiz)
    except QuizError as e:
        _raise_domain_error(e)
        raise


@router.delete(
    "/quizzes/{quiz_id}/questions/{question_id}",
    response_model=QuizResponse,
)
def delete_question(
    quiz_id: UUID,
    question_id: UUID,
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
) -> QuizResponse:
    svc = TeacherQuizService(db)
    try:
        quiz = svc.delete_question(
            current_user=current_user,
            quiz_id=quiz_id,
            question_id=question_id,
        )
        return _to_quiz_response(quiz)
    except QuizError as e:
        _raise_domain_error(e)
        raise


@router.post(
    "/quizzes/{quiz_id}/questions/{question_id}/regenerate",
    response_model=QuizResponse,
)
async def regenerate_question(
    quiz_id: UUID,
    question_id: UUID,
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
) -> QuizResponse:
    credit_service = CreditService(db)
    check = credit_service.check_balance(current_user.id)
    cost = credit_service.get_feature_cost(QUIZ_REGENERATE_QUESTION)
    if not check.allowed or check.balance < cost:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=insufficient_credits_detail(
                check,
                cost,
                "You don't have enough credits to regenerate this question.",
            ),
        )

    svc = TeacherQuizService(db)
    try:
        quiz = await svc.regenerate_question(
            current_user=current_user,
            quiz_id=quiz_id,
            question_id=question_id,
        )
        try:
            credit_service.charge(
                user_id=current_user.id,
                feature_key=QUIZ_REGENERATE_QUESTION,
                description=f"Quiz · regenerate question · {quiz.title or quiz_id}",
                metadata={"quiz_id": str(quiz_id), "question_id": str(question_id)},
            )
        except Exception:
            logger.exception(
                "credit_charge_failed",
                extra={"feature_key": QUIZ_REGENERATE_QUESTION},
            )
        return _to_quiz_response(quiz)
    except QuizError as e:
        _raise_domain_error(e)
        raise
    except Exception as e:
        logger.error("question_regenerate_unexpected", exc_info=True)
        raise HTTPException(status_code=500, detail={"code": "INTERNAL_ERROR", "message": str(e)})


@router.post("/quizzes/{quiz_id}/generate", response_model=GenerateResponse)
async def generate_quiz(
    quiz_id: UUID,
    body: QuizGenerateRequest,
    response: Response,
    request: Request,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
) -> GenerateResponse:
    credit_service = CreditService(db)
    check = credit_service.check_balance(current_user.id)
    cost = credit_service.get_feature_cost(QUIZ_GENERATE)
    if not check.allowed or check.balance < cost:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=insufficient_credits_detail(
                check,
                cost,
                "You don't have enough credits to generate a quiz.",
            ),
        )

    svc = TeacherQuizService(db)
    try:
        run, quiz, warnings = await svc.generate_for_quiz(
            current_user=current_user,
            quiz_id=quiz_id,
            req=body.model_dump(),
            idempotency_key=idempotency_key,
        )
        try:
            credit_service.charge(
                user_id=current_user.id,
                feature_key=QUIZ_GENERATE,
                description=f"Quiz generation · {quiz.title or quiz_id}",
                metadata={"quiz_id": str(quiz_id), "generation_run_id": str(run.id)},
            )
        except Exception:
            logger.exception("credit_charge_failed", extra={"feature_key": QUIZ_GENERATE})
        response.headers["X-Request-Id"] = request.headers.get("X-Request-Id", str(run.id))
        return GenerateResponse(
            ok=True,
            generation_run_id=str(run.id),
            warnings=list(warnings),
            quiz=_to_quiz_response(quiz),
        )
    except QuizError as e:
        _raise_domain_error(e)
        raise
    except Exception as e:
        logger.error("quiz_generate_unexpected", exc_info=True)
        raise HTTPException(status_code=500, detail={"code": "INTERNAL_ERROR", "message": str(e)})

