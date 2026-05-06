"""Video library load, recommendations with cache, and lookup by id."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, List
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domains.external_context.service import TeacherContextService
from app.domains.video_library import cache as rec_cache
from app.domains.video_library.mapping import library_keys_for_profile_slugs
from app.domains.video_library.quiz_merge import build_overrides_from_video, find_video_in_library
from app.domains.video_library.schemas import (
    RecommendationsResponse,
    RecommendationChannel,
    VideoDetailResponse,
    VideoLibraryFile,
)
from app.domains.video_library.selector import select_recommendations

logger = get_logger(__name__)

_DATA_PATH = Path(__file__).resolve().parent / "data" / "video_library.json"
_CACHE_TTL = timedelta(days=7)


@lru_cache(maxsize=1)
def _load_library_raw() -> str:
    if not _DATA_PATH.is_file():
        raise FileNotFoundError(f"Video library missing: {_DATA_PATH}")
    return _DATA_PATH.read_text(encoding="utf-8")


def load_library() -> VideoLibraryFile:
    return VideoLibraryFile.model_validate_json(_load_library_raw())


def reload_library_for_tests() -> None:
    """Clear LRU cache (tests only)."""
    _load_library_raw.cache_clear()


def _fingerprint(slugs: List[str]) -> tuple[str, ...]:
    return tuple(sorted({(s or "").strip().lower() for s in slugs if (s or "").strip()}))


class VideoLibraryService:
    def get_recommendations(self, db: Session, user_id: UUID, now: datetime | None = None) -> RecommendationsResponse:
        now = now or datetime.now(timezone.utc)
        ctx_service = TeacherContextService(db)
        ctx = ctx_service.get_by_user_id(user_id)
        if not ctx or not ctx.subjects:
            raise ValueError(
                "Teaching profile subjects are required for video recommendations. "
                "Complete your profile subjects in Settings."
            )
        slugs = [str(s) for s in (ctx.subjects or [])]
        fp = _fingerprint(slugs)
        now_epoch = now.timestamp()
        cached = rec_cache.get_cached(user_id, fp, now_epoch)
        if cached is not None:
            return RecommendationsResponse.model_validate(cached)

        library = load_library()
        lib_keys = library_keys_for_profile_slugs(slugs)
        channels = select_recommendations(library, lib_keys, user_id, now)
        payload = RecommendationsResponse(channels=channels).model_dump(mode="json")
        expires = now_epoch + _CACHE_TTL.total_seconds()
        rec_cache.set_cached(user_id, fp, expires, payload)
        return RecommendationsResponse.model_validate(payload)

    def get_video_detail(self, video_id: str) -> VideoDetailResponse:
        library = load_library()
        found = find_video_in_library(library, video_id)
        if not found:
            raise LookupError("Video not found")
        video, ch_id, ch_name = found
        lib_subject = ""
        for sk, bucket in library.subjects.items():
            if any(c.id == ch_id for c in bucket.channels):
                lib_subject = sk
                break
        return VideoDetailResponse(
            id=video.id,
            title=video.title,
            youtubeUrl=video.youtubeUrl,
            gradeBand=video.gradeBand,
            subject=video.subject,
            duration=video.duration,
            tags=video.tags,
            transcript=video.transcript,
            bestQuizType=video.bestQuizType,
            channelId=ch_id,
            channelName=ch_name,
            librarySubjectKey=lib_subject,
        )

    def build_quiz_request_overrides(self, video_id: str) -> dict[str, Any]:
        library = load_library()
        found = find_video_in_library(library, video_id)
        if not found:
            raise ValueError(f"Unknown video library id: {video_id}")
        video, _, _ = found
        return build_overrides_from_video(video)


video_library_service = VideoLibraryService()


def validate_library_file_on_disk() -> None:
    """Lightweight structural check (used by tests)."""
    lib = load_library()
    for sk, bucket in lib.subjects.items():
        assert len(bucket.channels) >= 10, f"{sk} needs >=10 channels"
        for ch in bucket.channels:
            assert len(ch.videos) >= 15, f"{sk}/{ch.id} needs >=15 videos"
