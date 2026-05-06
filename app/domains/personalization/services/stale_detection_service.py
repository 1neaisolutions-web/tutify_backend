"""
Stale detection service.

Identifies users whose personalization profile has not been recomputed
within their configured staleness_threshold_days. Queues recompute jobs.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domains.personalization.enums import SectionReadinessStatus
from app.domains.personalization.models import SectionReadiness, UserPersonalizationProfile

logger = get_logger(__name__)


class StaleDetectionService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def detect_stale_profiles(self, max_users: int = 100) -> list[UserPersonalizationProfile]:
        """
        Return active profiles that are stale (not recomputed within threshold).
        Limits to max_users to avoid overwhelming the job queue.
        """
        now = datetime.now(timezone.utc)
        stale_profiles: list[UserPersonalizationProfile] = []

        profiles = (
            self.db.query(UserPersonalizationProfile)
            .filter(
                UserPersonalizationProfile.status == "active",
                UserPersonalizationProfile.personalization_started_at.isnot(None),
            )
            .limit(max_users * 3)
            .all()
        )

        for profile in profiles:
            if len(stale_profiles) >= max_users:
                break

            last_check = profile.last_recomputed_at or profile.personalization_started_at
            if not last_check:
                continue

            threshold_days = profile.staleness_threshold_days or 7
            if (now - last_check).days >= threshold_days:
                stale_profiles.append(profile)

        return stale_profiles

    def mark_sections_stale(self, user_id, version: int) -> int:
        """Mark all ready sections as stale for a user. Returns count updated."""
        from datetime import datetime
        now = datetime.now(timezone.utc)
        count = (
            self.db.query(SectionReadiness)
            .filter(
                SectionReadiness.user_id == user_id,
                SectionReadiness.personalization_version == version,
                SectionReadiness.status == SectionReadinessStatus.READY,
            )
            .update({"status": SectionReadinessStatus.STALE, "updated_at": now})
        )
        self.db.flush()
        return count

    def trigger_stale_recompute(self, dry_run: bool = False) -> dict:
        """
        Detect stale profiles and enqueue recompute jobs for them.
        Returns a summary dict.
        """
        from app.domains.personalization.services.personalization_job_service import PersonalizationJobService

        stale = self.detect_stale_profiles()
        queued = 0
        skipped = 0

        for profile in stale:
            try:
                if not dry_run:
                    job_svc = PersonalizationJobService(self.db)
                    # Check if a recompute job is already queued/running
                    active = job_svc.get_active_jobs(profile.user_id)
                    already_running = any(j.job_type == "recompute" for j in active)
                    if not already_running:
                        job_svc.create(profile, "recompute", trigger="scheduled_stale_detection")
                        self.mark_sections_stale(profile.user_id, profile.personalization_version)
                        queued += 1
                    else:
                        skipped += 1
                else:
                    queued += 1
            except Exception as exc:
                logger.error(
                    "stale_detection.recompute_queue_failed",
                    extra={"user_id": str(profile.user_id), "error": str(exc)},
                )
                skipped += 1

        self.db.flush()
        logger.info(
            "stale_detection.complete",
            extra={"stale_detected": len(stale), "queued": queued, "skipped": skipped, "dry_run": dry_run},
        )
        return {"stale_detected": len(stale), "queued": queued, "skipped": skipped}
