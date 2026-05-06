"""
User history aggregation endpoints.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domains.auth.dependencies import require_any_role
from app.domains.auth.models import User
from app.domains.subscriptions.services.subscription_service import SubscriptionService
from app.domains.user_history import repository, schemas
from app.domains.user_history.quota_service import get_quota_status


router = APIRouter(prefix="/api/v1/history", tags=["history"])

_ALLOWED_ROLES = ("teacher", "school_admin", "super_admin", "org_admin")


@router.get("", response_model=schemas.HistoryListResponse)
def list_history(
    source_types: list[str] | None = Query(None),
    q: str | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    pinned_only: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
):
    total, items = repository.list_history(
        db=db,
        user_id=str(current_user.id),
        source_types=source_types,
        search=q,
        date_from=date_from,
        date_to=date_to,
        pinned_only=pinned_only,
        page=page,
        page_size=page_size,
    )
    return schemas.HistoryListResponse(total=total, page=page, page_size=page_size, items=items)


@router.get("/stats", response_model=schemas.HistoryStatsResponse)
def get_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
):
    stats = repository.get_stats(db, str(current_user.id))
    return schemas.HistoryStatsResponse(**stats)


@router.post("/pins", response_model=schemas.PinToggleResponse)
def toggle_pin(
    body: schemas.PinToggleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
):
    repository.toggle_pin(db, str(current_user.id), body.source_type, body.source_id, body.pinned)
    return schemas.PinToggleResponse(source_type=body.source_type, source_id=body.source_id, pinned=body.pinned)


@router.put("/feedback", response_model=schemas.FeedbackResponse)
def upsert_feedback(
    body: schemas.FeedbackUpsertRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
):
    now = datetime.now(timezone.utc)
    repository.upsert_feedback(db, str(current_user.id), body.source_type, body.source_id, body.hint, body.note)
    return schemas.FeedbackResponse(
        source_type=body.source_type,
        source_id=body.source_id,
        hint=body.hint,
        note=body.note,
        updated_at=now.isoformat(),
    )


@router.get("/quota", response_model=schemas.HistoryQuotaResponse)
def get_quota(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
):
    tier = SubscriptionService(db).get_user_tier(current_user.id).value
    return get_quota_status(db, user_id=str(current_user.id), tier=tier)


@router.post("/clear", response_model=schemas.ClearHistoryResponse)
def clear_history(
    body: schemas.ClearHistoryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_role(*_ALLOWED_ROLES)),
):
    """Hard-delete items matching the same filters as the list endpoint."""
    deleted = repository.clear_history(
        db=db,
        user_id=str(current_user.id),
        source_types=list(body.source_types) if body.source_types else None,
        search=body.q,
        date_from=body.date_from,
        date_to=body.date_to,
        keep_pinned=body.keep_pinned,
    )
    return schemas.ClearHistoryResponse(deleted_count=deleted)

