"""Learning Progress API routes."""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domains.auth.dependencies import get_current_user
from app.domains.auth.models import User
from app.domains.learning_progress import schemas as lp_schemas
from app.domains.learning_progress.services import (
    ContentFeedbackService,
    LearningEventService,
    LearningSessionService,
    ProgressAggregationService,
    RecommendationEventService,
)

router = APIRouter(prefix="/api/v1/learning-progress", tags=["learning-progress"])


@router.post(
    "/sessions/start",
    response_model=lp_schemas.LearningSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def start_session(
    data: lp_schemas.LearningSessionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = LearningSessionService(db)
    session = service.start_session(current_user.id, data)
    return session


@router.get(
    "/sessions",
    response_model=List[lp_schemas.LearningSessionListItem],
)
def list_sessions(
    content_id: Optional[str] = None,
    status_value: Optional[str] = Query(None, alias="status"),
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = LearningSessionService(db)
    sessions = service.list_sessions(
        teacher_id=current_user.id,
        content_id=content_id,
        status=status_value,
        skip=skip,
        limit=limit,
    )
    return sessions


@router.get(
    "/sessions/{id}",
    response_model=lp_schemas.LearningSessionResponse,
)
def get_session(
    id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = LearningSessionService(db)
    session = service.get_session(id, current_user.id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session


@router.patch(
    "/sessions/{id}",
    response_model=lp_schemas.LearningSessionResponse,
)
def update_session(
    id: UUID,
    data: lp_schemas.LearningSessionUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = LearningSessionService(db)
    session = service.update_session(id, current_user.id, data)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session


@router.post(
    "/sessions/{id}/complete",
    response_model=lp_schemas.LearningSessionResponse,
)
def complete_session(
    id: UUID,
    progress_percent: float = 100.0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = LearningSessionService(db)
    session = service.complete_session(id, current_user.id, progress_percent=progress_percent)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session


@router.post(
    "/events",
    response_model=lp_schemas.LearningEventResponse,
    status_code=status.HTTP_201_CREATED,
)
def record_learning_event(
    data: lp_schemas.LearningEventCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = LearningEventService(db)
    try:
        event = service.record_event(current_user.id, data)
        return event
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/sessions/{id}/events",
    response_model=List[lp_schemas.LearningEventResponse],
)
def list_session_events(
    id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = LearningEventService(db)
    events = service.list_events_for_session(id, current_user.id)
    return events


@router.post(
    "/recommendations/events",
    response_model=lp_schemas.RecommendationEventResponse,
    status_code=status.HTTP_201_CREATED,
)
def record_recommendation_event(
    data: lp_schemas.RecommendationEventCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = RecommendationEventService(db)
    event = service.record_event(current_user.id, data)
    return event


@router.get(
    "/recommendations/events",
    response_model=List[lp_schemas.RecommendationEventResponse],
)
def list_recommendation_events(
    content_id: Optional[str] = None,
    event_type: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = RecommendationEventService(db)
    events = service.list_events(
        teacher_id=current_user.id,
        content_id=content_id,
        event_type=event_type,
        skip=skip,
        limit=limit,
    )
    return events


@router.post(
    "/feedback",
    response_model=lp_schemas.ContentFeedbackResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_feedback(
    data: lp_schemas.ContentFeedbackCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ContentFeedbackService(db)
    feedback = service.create_feedback(current_user.id, data)
    return feedback


@router.get(
    "/feedback/me",
    response_model=List[lp_schemas.ContentFeedbackResponse],
)
def list_my_feedback(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ContentFeedbackService(db)
    feedback = service.list_feedback_for_teacher(current_user.id, skip=skip, limit=limit)
    return feedback


@router.get(
    "/feedback/content/{content_id}",
    response_model=List[lp_schemas.ContentFeedbackResponse],
)
def list_content_feedback(
    content_id: str,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ContentFeedbackService(db)
    feedback = service.list_feedback_for_content(content_id, skip=skip, limit=limit)
    return feedback


@router.get(
    "/overview",
    response_model=lp_schemas.LearningProgressOverview,
)
def get_overview(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ProgressAggregationService(db)
    overview = service.get_progress_overview(current_user.id)
    return overview


@router.get(
    "/content/{content_id}/progress",
    response_model=lp_schemas.ContentProgressSummary,
)
def get_content_progress(
    content_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ProgressAggregationService(db)
    summary = service.get_content_progress(current_user.id, content_id)
    return summary

