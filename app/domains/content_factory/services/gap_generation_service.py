"""
Gap-aware job creation for platform-level content generation.

This service is called from recommendation/ranking layers when a content gap
is detected. It only enqueues jobs; it never runs generation synchronously.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Set

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.core.config import settings
from app.core.logging import get_logger
from app.domains.content_factory.enums import ContentGenerationStrategy, JobStatus
from app.domains.content_factory.models import ContentGenerationJob
from app.domains.content_registry.enums import ContentStatus, ContentType
from app.domains.content_registry.models import ContentRegistryItem

logger = get_logger(__name__)


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


class GapGenerationService:
    """Detect simple duplicates and enqueue generation jobs for missing content."""

    def __init__(self, db: Session):
        self.db = db

    def _has_enough_content(
        self,
        locale: str,
        subject: Optional[str],
        prefer_non_starter: bool = False,
    ) -> bool:
        """Return True if registry already has at least MIN_CONTENT_PER_LOCALE items for locale+subject."""
        q = self.db.query(ContentRegistryItem).filter(
            ContentRegistryItem.status == ContentStatus.PUBLISHED.value,
            ContentRegistryItem.locale == locale,
        )
        if subject:
            subj = _norm(subject)
            if subj:
                q = q.filter(ContentRegistryItem.category == subj)
        if prefer_non_starter:
            # Exclude starter-seed items from the "enough content" check so we actually backfill AI content.
            q = q.filter(
                or_(
                    ContentRegistryItem.source_type.is_(None),
                    ContentRegistryItem.source_type != "starter_seed",
                )
            )
            # Also exclude by content_id prefix (defensive against starter items not tagged correctly).
            q = q.filter(~ContentRegistryItem.content_id.startswith("starter-"))
        count = q.count()
        return count >= int(settings.MIN_CONTENT_PER_LOCALE)

    def _existing_gap_job(
        self,
        locale: str,
        subject: Optional[str],
        grade_band: Optional[str],
        job_type: str,
    ) -> bool:
        """Check if a similar pending/active gap_detection job already exists."""
        running_fresh_after = datetime.now(timezone.utc) - timedelta(hours=2)
        q = self.db.query(ContentGenerationJob).filter(
            ContentGenerationJob.source == "gap_detection",
            ContentGenerationJob.job_type == job_type,
            ContentGenerationJob.locale == locale,
            or_(
                ContentGenerationJob.status.in_(
                    [JobStatus.PENDING.value, JobStatus.AWAITING_HUMAN_APPROVAL.value]
                ),
                and_(
                    ContentGenerationJob.status == JobStatus.RUNNING.value,
                    ContentGenerationJob.updated_at >= running_fresh_after,
                ),
            ),
        )
        if subject:
            q = q.filter(ContentGenerationJob.target_subject == subject)
        if grade_band:
            q = q.filter(ContentGenerationJob.grade_band == grade_band)
        return self.db.query(q.exists()).scalar()  # type: ignore[no-any-return]

    def enqueue_gap_jobs(
        self,
        locale: str,
        subjects: Iterable[str],
        grade_band: Optional[str],
        mode: str,
        prefer_non_starter: bool = False,
    ) -> None:
        """
        Enqueue micro_course jobs for missing subjects in a locale.

        This is best-effort and non-blocking; errors are logged and swallowed.
        """
        subjects_norm: List[str] = sorted({s for s in (_norm(s) for s in subjects) if s})
        if not subjects_norm:
            return

        for subj in subjects_norm:
            try:
                if self._has_enough_content(locale=locale, subject=subj):
                    logger.info(
                        "Gap generation skipped (enough content) locale=%s subject=%s",
                        locale,
                        subj,
                    )
                    continue
                if self._existing_gap_job(locale=locale, subject=subj, grade_band=grade_band, job_type="micro_course"):
                    logger.info(
                        "Gap generation skipped (job exists) locale=%s subject=%s grade_band=%s",
                        locale,
                        subj,
                        grade_band,
                    )
                    continue

                topic = f"Foundational teaching strategies for {subj}"
                job = ContentGenerationJob(
                    requested_by_user_id=None,
                    content_type=ContentType.MICRO_COURSE.value,
                    job_type="micro_course",
                    generation_strategy=ContentGenerationStrategy.TOPIC_BASED.value,
                    topic=topic,
                    subject=subj,
                    target_subject=subj,
                    grade_band=grade_band,
                    difficulty="beginner",
                    locale=locale,
                    status=JobStatus.PENDING.value,
                    current_step=None,
                    retry_count=0,
                    priority=10,
                    source="gap_detection",
                )
                self.db.add(job)
                self.db.commit()
                logger.info(
                    "Gap generation job created id=%s locale=%s subject=%s grade_band=%s mode=%s",
                    job.id,
                    locale,
                    subj,
                    grade_band,
                    mode,
                )
            except Exception as exc:  # pragma: no cover - defensive
                self.db.rollback()
                logger.warning(
                    "Failed to enqueue gap generation job locale=%s subject=%s grade_band=%s error=%s",
                    locale,
                    subj,
                    grade_band,
                    exc,
                )

