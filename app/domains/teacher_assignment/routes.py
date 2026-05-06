"""
Teacher Tools Assignment HTTP routes.
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
from app.domains.teacher_assignment.errors import AssignmentError
from app.domains.teacher_assignment.models import TeacherAssignment
from app.domains.teacher_assignment.repository import AssignmentListFilters
from app.domains.teacher_assignment.schemas import (
    AssignmentCreateRequest,
    AssignmentDuplicateResponse,
    AssignmentGenerateRequest,
    AssignmentGenerateResponse,
    AssignmentListResponse,
    AssignmentPatchRequest,
    AssignmentRegenerateLineRequest,
    AssignmentRegenerateTopicRequest,
    AssignmentResponse,
    RegeneratedLineResponse,
    RegeneratedTopicResponse,
)
from app.domains.teacher_assignment.service import TeacherAssignmentService
from app.domains.subscriptions.credit_errors import insufficient_credits_detail
from app.domains.subscriptions.feature_keys import (
    ASSIGNMENT_GENERATE,
    ASSIGNMENT_REGENERATE_LINE,
    ASSIGNMENT_REGENERATE_TOPIC,
)
from app.domains.subscriptions.services.credit_service import CreditService
from app.domains.subscriptions.services.subscription_service import SubscriptionService
from app.domains.user_history.quota_service import check_and_enforce

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/teacher-tools", tags=["teacher-assignment"])

_ALLOWED_ROLES = ("teacher", "school_admin", "super_admin", "org_admin")


def _source_summary(a: TeacherAssignment) -> Optional[str]:
    if a.generate_without_sources:
        return "Generation without catalog retrieval (grounding off)"
    pack_count = len(a.source_pack_ids or [])
    topic_count = len(a.scope_topics or [])
    refine = " · scope hint applied" if (a.scope_refinement or "").strip() else ""
    return (
        f"Catalog retrieval · {pack_count} source{'s' if pack_count != 1 else ''} "
        f"· {topic_count} topic strand{'s' if topic_count != 1 else ''}{refine}"
    )


def _to_assignment_response(a: TeacherAssignment) -> AssignmentResponse:
    return AssignmentResponse(
        id=str(a.id),
        title=a.title,
        subject=a.subject,
        grade=a.grade,
        classes=list(a.class_keys or []),
        type=a.assignment_type,
        dueAt=a.due_at,
        createdAt=a.created_at,
        updatedAt=a.updated_at,
        assignedCount=int(a.assigned_count or 0),
        submitted=int(a.submitted_count or 0),
        pending=int(a.pending_count or 0),
        graded=int(a.graded_count or 0),
        status=a.status,
        topic=a.topic_summary or "General scope",
        sourceSummary=_source_summary(a),
        briefTopics=list(a.brief_topics or []),
        studentInstructions=a.student_instructions,
        handoutLayout=a.handout_layout,
        sourceBookIds=[str(x) for x in (a.source_pack_ids or [])],
        scopeTopics=list(a.scope_topics or []),
        scopeRefinement=a.scope_refinement,
        generateWithoutSources=bool(a.generate_without_sources),
        rigorProfile=a.rigor_profile or "Standard",
        teacherNotes=a.teacher_notes,
        difficulty=a.difficulty,
    )


def _raise_domain_error(e: AssignmentError) -> None:
    raise HTTPException(
        status_code=e.http_status,
        detail={"code": e.code, "message": e.message},
    )


@router.get("/assignments", response_model=AssignmentListResponse)
def list_assignments(
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
) -> AssignmentListResponse:
    svc = TeacherAssignmentService(db)
    items, total = svc.list_assignments(
        current_user=current_user,
        filters=AssignmentListFilters(
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
    return AssignmentListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[_to_assignment_response(x) for x in items],
    )


@router.post(
    "/assignments",
    response_model=AssignmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_assignment(
    body: AssignmentCreateRequest,
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
    response: Response = None,  # type: ignore[assignment]
) -> AssignmentResponse:
    quota = None
    if response is not None:
        tier = SubscriptionService(db).get_user_tier(current_user.id).value
        quota = check_and_enforce(db, user_id=str(current_user.id), source_type="assignment", tier=tier)
    svc = TeacherAssignmentService(db)
    a = svc.create_assignment(current_user=current_user, payload=body.model_dump())
    if response is not None and quota is not None:
        response.headers["X-History-Warning-Level"] = quota.warning_level
        response.headers["X-History-Count"] = str(quota.current_count + 1)
        response.headers["X-History-Limit"] = str(quota.limit)
        if quota.evicted_id:
            response.headers["X-History-Eviction-Title"] = quota.evicted_title or ""
            response.headers["X-History-Eviction-Type"] = "assignment"
    return _to_assignment_response(a)


@router.get("/assignments/{assignment_id}", response_model=AssignmentResponse)
def get_assignment(
    assignment_id: UUID,
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
) -> AssignmentResponse:
    svc = TeacherAssignmentService(db)
    try:
        a = svc.get_assignment(current_user=current_user, assignment_id=assignment_id)
        return _to_assignment_response(a)
    except AssignmentError as e:
        _raise_domain_error(e)
        raise


@router.patch("/assignments/{assignment_id}", response_model=AssignmentResponse)
def patch_assignment(
    assignment_id: UUID,
    body: AssignmentPatchRequest,
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
) -> AssignmentResponse:
    svc = TeacherAssignmentService(db)
    try:
        a = svc.patch_assignment(
            current_user=current_user,
            assignment_id=assignment_id,
            patch=body.model_dump(exclude_unset=True),
        )
        return _to_assignment_response(a)
    except AssignmentError as e:
        _raise_domain_error(e)
        raise


@router.delete(
    "/assignments/{assignment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_assignment(
    assignment_id: UUID,
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
) -> Response:
    svc = TeacherAssignmentService(db)
    try:
        svc.delete_assignment(current_user=current_user, assignment_id=assignment_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except AssignmentError as e:
        _raise_domain_error(e)
        raise


@router.post(
    "/assignments/{assignment_id}/duplicate",
    response_model=AssignmentDuplicateResponse,
)
def duplicate_assignment(
    assignment_id: UUID,
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
) -> AssignmentDuplicateResponse:
    svc = TeacherAssignmentService(db)
    try:
        copy = svc.duplicate_assignment(
            current_user=current_user, assignment_id=assignment_id
        )
        return AssignmentDuplicateResponse(ok=True, id=str(copy.id))
    except AssignmentError as e:
        _raise_domain_error(e)
        raise


@router.post(
    "/assignments/{assignment_id}/generate",
    response_model=AssignmentGenerateResponse,
)
async def generate_assignment(
    assignment_id: UUID,
    body: AssignmentGenerateRequest,
    response: Response,
    request: Request,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
) -> AssignmentGenerateResponse:
    credit_service = CreditService(db)
    check = credit_service.check_balance(current_user.id)
    cost = credit_service.get_feature_cost(ASSIGNMENT_GENERATE)
    if not check.allowed or check.balance < cost:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=insufficient_credits_detail(
                check,
                cost,
                "You don't have enough credits to generate an assignment.",
            ),
        )

    svc = TeacherAssignmentService(db)
    try:
        run, a, warnings = await svc.generate_brief(
            current_user=current_user,
            assignment_id=assignment_id,
            req=body.model_dump(),
            idempotency_key=idempotency_key,
        )
        try:
            credit_service.charge(
                user_id=current_user.id,
                feature_key=ASSIGNMENT_GENERATE,
                description=f"Assignment generation · {a.title or assignment_id}",
                metadata={
                    "assignment_id": str(assignment_id),
                    "generation_run_id": str(run.id),
                },
            )
        except Exception:
            logger.exception(
                "credit_charge_failed",
                extra={"feature_key": ASSIGNMENT_GENERATE},
            )
        response.headers["X-Request-Id"] = request.headers.get("X-Request-Id", str(run.id))
        return AssignmentGenerateResponse(
            ok=True,
            generation_run_id=str(run.id),
            warnings=list(warnings),
            assignment=_to_assignment_response(a),
        )
    except AssignmentError as e:
        _raise_domain_error(e)
        raise
    except Exception as e:
        logger.error("assignment_generate_unexpected", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"code": "INTERNAL_ERROR", "message": str(e)},
        )


@router.post(
    "/assignments/{assignment_id}/topics/regenerate",
    response_model=RegeneratedTopicResponse,
)
async def regenerate_topic(
    assignment_id: UUID,
    body: AssignmentRegenerateTopicRequest,
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
) -> RegeneratedTopicResponse:
    credit_service = CreditService(db)
    check = credit_service.check_balance(current_user.id)
    cost = credit_service.get_feature_cost(ASSIGNMENT_REGENERATE_TOPIC)
    if not check.allowed or check.balance < cost:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=insufficient_credits_detail(
                check,
                cost,
                "You don't have enough credits to regenerate this topic.",
            ),
        )

    svc = TeacherAssignmentService(db)
    try:
        topic_stub, warnings = await svc.regenerate_topic(
            current_user=current_user,
            assignment_id=assignment_id,
            topic_id=body.topicId,
            topic_title=body.topicTitle,
        )
        try:
            credit_service.charge(
                user_id=current_user.id,
                feature_key=ASSIGNMENT_REGENERATE_TOPIC,
                description="Assignment · regenerate topic",
                metadata={
                    "assignment_id": str(assignment_id),
                    "topic_id": body.topicId,
                },
            )
        except Exception:
            logger.exception(
                "credit_charge_failed",
                extra={"feature_key": ASSIGNMENT_REGENERATE_TOPIC},
            )
        return RegeneratedTopicResponse(ok=True, topic=topic_stub, warnings=list(warnings))
    except AssignmentError as e:
        _raise_domain_error(e)
        raise
    except Exception as e:
        logger.error("assignment_regen_topic_unexpected", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"code": "INTERNAL_ERROR", "message": str(e)},
        )


@router.post(
    "/assignments/{assignment_id}/lines/regenerate",
    response_model=RegeneratedLineResponse,
)
async def regenerate_line(
    assignment_id: UUID,
    body: AssignmentRegenerateLineRequest,
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
    db: Session = Depends(get_db),
) -> RegeneratedLineResponse:
    credit_service = CreditService(db)
    check = credit_service.check_balance(current_user.id)
    cost = credit_service.get_feature_cost(ASSIGNMENT_REGENERATE_LINE)
    if not check.allowed or check.balance < cost:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=insufficient_credits_detail(
                check,
                cost,
                "You don't have enough credits to regenerate this line.",
            ),
        )

    svc = TeacherAssignmentService(db)
    try:
        line_id, line_text, warnings = await svc.regenerate_line(
            current_user=current_user,
            assignment_id=assignment_id,
            topic_id=body.topicId,
            topic_title=body.topicTitle,
            line_index=body.lineIndex,
        )
        try:
            credit_service.charge(
                user_id=current_user.id,
                feature_key=ASSIGNMENT_REGENERATE_LINE,
                description="Assignment · regenerate line",
                metadata={
                    "assignment_id": str(assignment_id),
                    "topic_id": body.topicId,
                    "line_index": body.lineIndex,
                },
            )
        except Exception:
            logger.exception(
                "credit_charge_failed",
                extra={"feature_key": ASSIGNMENT_REGENERATE_LINE},
            )
        return RegeneratedLineResponse(
            ok=True, lineId=line_id, text=line_text, warnings=list(warnings)
        )
    except AssignmentError as e:
        _raise_domain_error(e)
        raise
    except Exception as e:
        logger.error("assignment_regen_line_unexpected", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"code": "INTERNAL_ERROR", "message": str(e)},
        )
