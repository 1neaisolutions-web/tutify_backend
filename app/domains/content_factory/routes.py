"""
Content Factory API routes.
"""
from datetime import datetime, timezone
from typing import List, Optional, Set
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domains.auth.dependencies import require_any_role
from app.domains.auth.models import User
from app.domains.content_factory import schemas as factory_schemas
from app.domains.content_factory.enums import JobStatus
from app.domains.content_factory.models import ContentGenerationJob
from app.domains.content_factory.services.content_factory_service import (
    ContentFactoryService,
    ContentFactoryServiceError,
)
from app.domains.content_factory.services.review_service import ContentReviewService
from app.domains.subscriptions.services.credit_service import CreditService
from app.domains.subscriptions.credit_errors import insufficient_credits_detail
from app.domains.subscriptions.feature_keys import CONTENT_GAP_FILL

router = APIRouter(prefix="/api/v1/content-factory", tags=["content-factory"])

_ALLOWED_JOB_SORT: Set[str] = {"recent", "ops"}
_ALLOWED_STATUSES: Set[str] = {s.value for s in JobStatus}


def _validate_job_list_params(
    job_status: Optional[str],
    content_type: Optional[str],
    locale: Optional[str],
    source: Optional[str],
    sort: Optional[str],
) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str], str]:
    if job_status is not None and job_status != "" and job_status not in _ALLOWED_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status filter. Allowed: {sorted(_ALLOWED_STATUSES)}",
        )
    if content_type is not None and len(content_type) > 50:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="content_type too long")
    if locale is not None and len(locale) > 20:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="locale too long")
    if source is not None and len(source) > 50:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="source filter too long")
    norm_status = job_status if job_status else None
    norm_ct = content_type if content_type else None
    norm_locale = locale if locale else None
    norm_source = source if source else None
    sort_val = (sort or "recent").strip().lower()
    if sort_val not in _ALLOWED_JOB_SORT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid sort. Use 'recent' or 'ops'.",
        )
    return norm_status, norm_ct, norm_locale, norm_source, sort_val


@router.post(
    "/generate/micro-course",
    response_model=factory_schemas.ContentGenerationJobResponse,
    status_code=status.HTTP_201_CREATED,
)
async def request_micro_course(
    data: factory_schemas.GenerateMicroCourseRequest,
    current_user: User = Depends(require_any_role("super_admin", "org_admin")),
    db: Session = Depends(get_db),
):
    """Request a new micro-course generation (admin). Runs workflow to completion and returns job."""
    credit_service = CreditService(db)
    check = credit_service.check_balance(current_user.id)
    cost = credit_service.get_feature_cost(CONTENT_GAP_FILL)
    if not check.allowed or check.balance < cost:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=insufficient_credits_detail(
                check,
                cost,
                "You don't have enough credits to run content generation.",
            ),
        )
    service = ContentFactoryService(db)
    job = await service.generate_micro_course(
        topic=data.topic,
        subject=data.subject,
        grade_band=data.grade_band,
        difficulty=data.difficulty,
        locale=data.locale,
        requested_by_user_id=current_user.id,
        generation_mode=data.generation_mode,
    )
    try:
        credit_service.charge(
            user_id=current_user.id,
            feature_key=CONTENT_GAP_FILL,
            llm_response=None,
            description="Content factory · micro-course",
        )
    except Exception:
        pass
    return job


@router.get(
    "/jobs/by-user/{user_id}",
    summary="Admin: job status summary for a specific teacher",
)
def jobs_by_user(
    user_id: UUID,
    current_user: User = Depends(require_any_role("super_admin", "org_admin")),
    db: Session = Depends(get_db),
):
    """
    Return generation job counts and recent jobs for a specific teacher user.
    Used by the admin dashboard to inspect per-user pipeline health.
    """
    from app.domains.content_factory.enums import JobStatus as JS
    from sqlalchemy import func

    counts_raw = (
        db.query(ContentGenerationJob.status, func.count(ContentGenerationJob.id))
        .filter(ContentGenerationJob.requested_by_user_id == user_id)
        .group_by(ContentGenerationJob.status)
        .all()
    )
    counts = {row[0]: row[1] for row in counts_raw}

    recent_jobs = (
        db.query(ContentGenerationJob)
        .filter(ContentGenerationJob.requested_by_user_id == user_id)
        .order_by(ContentGenerationJob.created_at.desc())
        .limit(10)
        .all()
    )

    from app.domains.learning_hub.services.learning_hub_home_service import get_profile_completion_status
    try:
        profile_status = get_profile_completion_status(db, user_id)
        profile_score = profile_status.score
        profile_missing = profile_status.missing_count
        profile_is_sufficient = profile_status.is_sufficient
    except Exception:
        profile_score = 0.0
        profile_missing = -1
        profile_is_sufficient = False

    return {
        "user_id": str(user_id),
        "profile_completeness_score": round(profile_score, 3),
        "profile_is_sufficient": profile_is_sufficient,
        "profile_missing_sections": profile_missing,
        "job_counts": {
            "pending": counts.get(JS.PENDING.value, 0),
            "running": counts.get(JS.RUNNING.value, 0),
            "completed": counts.get(JS.COMPLETED.value, 0),
            "failed": counts.get(JS.FAILED.value, 0),
            "reviewing": counts.get(JS.REVIEWING.value, 0),
        },
        "recent_jobs": [
            {
                "id": str(j.id),
                "status": j.status,
                "content_type": j.content_type,
                "topic": j.topic,
                "created_at": j.created_at.isoformat() if j.created_at else None,
                "error_message": j.error_message,
                "current_step": j.current_step,
            }
            for j in recent_jobs
        ],
    }


@router.get(
    "/jobs/summary",
    response_model=factory_schemas.ContentFactoryJobsSummaryResponse,
)
def jobs_summary(
    current_user: User = Depends(require_any_role("super_admin", "org_admin")),
    db: Session = Depends(get_db),
):
    """Aggregate job counts for Learning Hub admin operations (must be registered before /jobs/{id})."""
    service = ContentFactoryService(db)
    data = service.get_jobs_summary()
    return factory_schemas.ContentFactoryJobsSummaryResponse.model_validate(data)


@router.post(
    "/ops/stop",
    response_model=factory_schemas.StopGenerationResponse,
)
def stop_generation_jobs(
    request: Request,
    current_user: User = Depends(require_any_role("super_admin", "org_admin")),
    db: Session = Depends(get_db),
):
    """
    Stop background gap-detection processing and mark pending gap jobs as failed.

    Note: jobs already in-progress may still complete depending on whether their
    async LLM calls respond to cancellation.
    """
    worker_cancelled = False
    task = getattr(request.app.state, "gap_worker_task", None)
    if task:
        try:
            task.cancel()
            worker_cancelled = True
        except Exception:
            worker_cancelled = False

    now = datetime.now(timezone.utc)
    pending_q = (
        db.query(ContentGenerationJob)
        .filter(
            ContentGenerationJob.source == "gap_detection",
            ContentGenerationJob.status == JobStatus.PENDING.value,
        )
    )
    pending_jobs = pending_q.all()
    pending_jobs_stopped = len(pending_jobs)
    for job in pending_jobs:
        job.status = JobStatus.FAILED.value
        job.error_message = "Stopped by admin"
        job.completed_at = now
        job.current_step = "stopped_by_admin"
    if pending_jobs:
        db.commit()

    return factory_schemas.StopGenerationResponse(
        worker_cancelled=worker_cancelled,
        pending_jobs_stopped=pending_jobs_stopped,
        message="Gap generation stop requested",
    )


@router.get("/jobs", response_model=List[factory_schemas.ContentGenerationJobListItem])
def list_jobs(
    job_status: Optional[str] = Query(None, alias="status"),
    content_type: Optional[str] = None,
    locale: Optional[str] = None,
    source: Optional[str] = None,
    sort: Optional[str] = Query(
        None,
        description="recent (default) | ops (approval/failures first)",
    ),
    skip: int = Query(0, ge=0, le=10_000),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(require_any_role("super_admin", "org_admin")),
    db: Session = Depends(get_db),
):
    """List content generation jobs (admin)."""
    ns, nct, nl, nsrc, sort_val = _validate_job_list_params(
        job_status, content_type, locale, source, sort
    )
    service = ContentFactoryService(db)
    jobs = service.list_jobs(
        status=ns,
        content_type=nct,
        locale=nl,
        source=nsrc,
        skip=skip,
        limit=limit,
        sort=sort_val,
    )
    return jobs


@router.get(
    "/jobs/{id:uuid}",
    response_model=factory_schemas.ContentGenerationJobResponse,
)
def get_job(
    id: UUID,
    current_user: User = Depends(require_any_role("super_admin", "org_admin")),
    db: Session = Depends(get_db),
):
    """Get job details by id."""
    service = ContentFactoryService(db)
    job = service.get_job(id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


@router.post(
    "/jobs/{id:uuid}/retry",
    response_model=factory_schemas.ContentGenerationJobResponse,
)
async def retry_job(
    id: UUID,
    current_user: User = Depends(require_any_role("super_admin", "org_admin")),
    db: Session = Depends(get_db),
):
    """Retry a failed/rejected job by cloning inputs into a fresh job."""
    service = ContentFactoryService(db)
    try:
        return await service.retry_job(id, requested_by_user_id=current_user.id)
    except ContentFactoryServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/jobs/{id:uuid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(
    id: UUID,
    current_user: User = Depends(require_any_role("super_admin", "org_admin")),
    db: Session = Depends(get_db),
):
    """Delete a content generation job (admin)."""
    service = ContentFactoryService(db)
    ok = service.delete_job(id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")


@router.get(
    "/jobs/{id:uuid}/reviews",
    response_model=List[factory_schemas.ContentGenerationReviewResponse],
)
def list_job_reviews(
    id: UUID,
    current_user: User = Depends(require_any_role("super_admin", "org_admin")),
    db: Session = Depends(get_db),
):
    """List human reviews for a job."""
    review_service = ContentReviewService(db)
    # Ensure job exists
    _ = review_service._get_job(id)  # type: ignore[attr-defined]
    reviews = review_service.list_reviews(id)
    return reviews


@router.post(
    "/jobs/{id:uuid}/approve",
    response_model=factory_schemas.ContentGenerationJobResponse,
)
def approve_job(
    id: UUID,
    body: factory_schemas.ReviewActionRequest,
    current_user: User = Depends(require_any_role("super_admin", "org_admin")),
    db: Session = Depends(get_db),
):
    """Approve a job and publish content (admin)."""
    review_service = ContentReviewService(db)
    try:
        job = review_service.approve_job(
            job_id=id,
            reviewer_user_id=current_user.id,
            notes=body.notes,
        )
        return job
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/jobs/{id:uuid}/reject",
    response_model=factory_schemas.ContentGenerationJobResponse,
)
def reject_job(
    id: UUID,
    body: factory_schemas.ReviewActionRequest,
    current_user: User = Depends(require_any_role("super_admin", "org_admin")),
    db: Session = Depends(get_db),
):
    """Reject a job and do not publish (admin)."""
    review_service = ContentReviewService(db)
    try:
        job = review_service.reject_job(
            job_id=id,
            reviewer_user_id=current_user.id,
            notes=body.notes,
        )
        return job
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/jobs/{id:uuid}/request-changes",
    response_model=factory_schemas.ContentGenerationJobResponse,
)
def request_job_changes(
    id: UUID,
    body: factory_schemas.ReviewActionRequest,
    current_user: User = Depends(require_any_role("super_admin", "org_admin")),
    db: Session = Depends(get_db),
):
    """Request changes for a job (admin)."""
    review_service = ContentReviewService(db)
    try:
        job = review_service.request_changes(
            job_id=id,
            reviewer_user_id=current_user.id,
            notes=body.notes,
        )
        return job
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
