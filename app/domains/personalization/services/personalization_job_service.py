"""Job lifecycle management for personalization jobs."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domains.personalization.models import PersonalizationJob, UserPersonalizationProfile

logger = get_logger(__name__)

# Retry policies per job type: (max_retries, timeout_seconds)
JOB_RETRY_POLICY: dict[str, tuple[int, int]] = {
    "start": (3, 120),
    "recompute": (3, 60),
    "reset": (2, 180),
    "expand_assignments": (3, 60),
    "rebuild_slate": (3, 30),
    "reconcile_unlocks": (2, 30),
}


class PersonalizationJobService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        profile: UserPersonalizationProfile,
        job_type: str,
        section: Optional[str] = None,
        trigger: Optional[str] = None,
    ) -> PersonalizationJob:
        max_retries, _ = JOB_RETRY_POLICY.get(job_type, (3, 60))
        job = PersonalizationJob(
            personalization_profile_id=profile.id,
            user_id=profile.user_id,
            job_type=job_type,
            status="queued",
            section=section,
            trigger=trigger,
            max_retries=max_retries,
        )
        self.db.add(job)
        self.db.flush()
        logger.info(
            "personalization.job_created",
            extra={"user_id": str(profile.user_id), "job_type": job_type, "job_id": str(job.id)},
        )
        return job

    def mark_running(self, job: PersonalizationJob) -> PersonalizationJob:
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        job.updated_at = datetime.now(timezone.utc)
        self.db.flush()
        return job

    def mark_completed(self, job: PersonalizationJob) -> PersonalizationJob:
        now = datetime.now(timezone.utc)
        job.status = "completed"
        job.completed_at = now
        if job.started_at:
            job.duration_ms = int((now - job.started_at).total_seconds() * 1000)
        job.updated_at = now
        self.db.flush()
        return job

    def mark_failed(self, job: PersonalizationJob, error: str) -> PersonalizationJob:
        now = datetime.now(timezone.utc)
        job.status = "failed"
        job.error_message = error
        job.completed_at = now
        if job.started_at:
            job.duration_ms = int((now - job.started_at).total_seconds() * 1000)
        job.updated_at = now
        self.db.flush()
        logger.error(
            "personalization.job_failed",
            extra={"user_id": str(job.user_id), "job_type": job.job_type, "error": error, "retry_count": job.retry_count},
        )
        return job

    def increment_retry(self, job: PersonalizationJob) -> PersonalizationJob:
        job.retry_count += 1
        job.status = "queued"
        job.updated_at = datetime.now(timezone.utc)
        self.db.flush()
        return job

    def get_active_jobs(self, user_id: uuid.UUID) -> list[PersonalizationJob]:
        return (
            self.db.query(PersonalizationJob)
            .filter(
                PersonalizationJob.user_id == user_id,
                PersonalizationJob.status.in_(["queued", "running"]),
            )
            .order_by(PersonalizationJob.created_at.desc())
            .all()
        )

    def get_jobs(self, user_id: uuid.UUID, limit: int = 20) -> list[PersonalizationJob]:
        return (
            self.db.query(PersonalizationJob)
            .filter(PersonalizationJob.user_id == user_id)
            .order_by(PersonalizationJob.created_at.desc())
            .limit(limit)
            .all()
        )
