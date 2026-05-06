"""Authenticated video library API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.logging import get_logger
from app.domains.auth.dependencies import get_current_user
from app.domains.auth.models import User
from app.domains.video_library.schemas import RecommendationsResponse, VideoDetailResponse
from app.domains.video_library.service import video_library_service

logger = get_logger(__name__)

router = APIRouter(tags=["video-library"])


@router.get(
    "/api/v1/videos/recommendations",
    response_model=RecommendationsResponse,
    status_code=status.HTTP_200_OK,
)
async def get_video_recommendations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecommendationsResponse:
    try:
        return video_library_service.get_recommendations(db, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("video recommendations error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not load video recommendations.",
        ) from exc


@router.get(
    "/api/v1/videos/{video_id}",
    response_model=VideoDetailResponse,
    status_code=status.HTTP_200_OK,
)
async def get_video_by_id(
    video_id: str,
    _current_user: User = Depends(get_current_user),
) -> VideoDetailResponse:
    try:
        return video_library_service.get_video_detail(video_id)
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found") from None
    except Exception as exc:
        logger.error("video detail error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not load video metadata.",
        ) from exc
