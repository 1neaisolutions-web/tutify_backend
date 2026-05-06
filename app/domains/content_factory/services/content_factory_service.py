"""
Content Factory Service: main entry for generating micro-courses.
Creates job and runs orchestrator.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import case, desc, func
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domains.content_factory.enums import ContentGenerationStrategy, JobStatus
from app.domains.content_factory.models import ContentGenerationJob
from app.domains.content_factory.services.generation_orchestrator_service import (
    GenerationOrchestratorService,
)

logger = get_logger(__name__)


class ContentFactoryServiceError(Exception):
    """Raised when content factory operation fails."""
    pass


class ContentFactoryService:
    """Main service: create generation job and run micro-course workflow."""

    def __init__(self, db: Session):
        self.db = db

    def create_job(
        self,
        content_type: str,
        topic: str,
        subject: Optional[str] = None,
        grade_band: Optional[str] = None,
        difficulty: Optional[str] = None,
        locale: str = "en",
        requested_by_user_id: Optional[UUID] = None,
        generation_strategy: str = ContentGenerationStrategy.TOPIC_BASED.value,
        source: Optional[str] = None,
    ) -> ContentGenerationJob:
        """Create a pending content generation job."""
        job = ContentGenerationJob(
            requested_by_user_id=requested_by_user_id,
            content_type=content_type,
            generation_strategy=generation_strategy,
            topic=topic,
            subject=subject,
            grade_band=grade_band,
            difficulty=difficulty,
            locale=locale,
            status=JobStatus.PENDING.value,
            current_step=None,
            retry_count=0,
            source=source,
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        logger.info("Created content generation job id=%s topic=%s", job.id, topic)
        return job

    def get_job(self, job_id: UUID) -> Optional[ContentGenerationJob]:
        """Get job by id."""
        return self.db.query(ContentGenerationJob).filter(ContentGenerationJob.id == job_id).first()

    def delete_job(self, job_id: UUID) -> bool:
        """Delete a job by id. Returns True when deleted."""
        job = self.get_job(job_id)
        if not job:
            return False
        self.db.delete(job)
        self.db.commit()
        return True

    def list_jobs(
        self,
        status: Optional[str] = None,
        content_type: Optional[str] = None,
        locale: Optional[str] = None,
        source: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
        sort: Optional[str] = None,
    ) -> List[ContentGenerationJob]:
        """List jobs with optional filters.

        sort:
            - recent: newest created_at first (default).
            - ops: surface awaiting_human_approval, failed, running, pending first, then by updated_at.
        """
        q = self.db.query(ContentGenerationJob)
        if status is not None:
            q = q.filter(ContentGenerationJob.status == status)
        if content_type is not None:
            q = q.filter(ContentGenerationJob.content_type == content_type)
        if locale is not None:
            q = q.filter(ContentGenerationJob.locale == locale)
        if source is not None:
            q = q.filter(ContentGenerationJob.source == source)

        mode = (sort or "recent").strip().lower()
        if mode == "ops":
            priority = case(
                (ContentGenerationJob.status == JobStatus.AWAITING_HUMAN_APPROVAL.value, 0),
                (ContentGenerationJob.status == JobStatus.FAILED.value, 1),
                (ContentGenerationJob.status == JobStatus.REJECTED.value, 2),
                (ContentGenerationJob.status == JobStatus.RUNNING.value, 3),
                (ContentGenerationJob.status == JobStatus.PUBLISHING.value, 4),
                (ContentGenerationJob.status == JobStatus.PENDING.value, 5),
                (ContentGenerationJob.status == JobStatus.REVIEWING.value, 6),
                (ContentGenerationJob.status == JobStatus.COMPLETED.value, 7),
                else_=8,
            )
            q = q.order_by(
                priority.asc(),
                desc(ContentGenerationJob.updated_at),
                desc(ContentGenerationJob.created_at),
            )
        else:
            q = q.order_by(desc(ContentGenerationJob.created_at))

        return q.offset(skip).limit(limit).all()

    def get_jobs_summary(self) -> Dict[str, Any]:
        """
        Aggregate counts for admin operations dashboard.

        stuck_count: jobs in pending or running with no update for >= 2 hours (UTC).
        published_generated_count: registry rows published and sourced from content factory.
        """
        rows = (
            self.db.query(ContentGenerationJob.status, func.count(ContentGenerationJob.id))
            .group_by(ContentGenerationJob.status)
            .all()
        )
        by_status = {str(s): int(c) for s, c in rows}

        def _c(key: str) -> int:
            return int(by_status.get(key, 0))

        now = datetime.now(timezone.utc)
        stuck_threshold = now - timedelta(hours=2)
        stuck_count = (
            self.db.query(func.count(ContentGenerationJob.id))
            .filter(
                ContentGenerationJob.status.in_(
                    [JobStatus.PENDING.value, JobStatus.RUNNING.value]
                ),
                ContentGenerationJob.updated_at < stuck_threshold,
            )
            .scalar()
        )
        stuck_count = int(stuck_count or 0)

        from app.domains.content_registry.models import ContentRegistryItem

        published_generated = (
            self.db.query(func.count(ContentRegistryItem.id))
            .filter(
                ContentRegistryItem.source_type == "content_factory",
                ContentRegistryItem.status == "published",
            )
            .scalar()
        )
        published_generated = int(published_generated or 0)

        return {
            "pending_count": _c(JobStatus.PENDING.value),
            "running_count": _c(JobStatus.RUNNING.value),
            "reviewing_count": _c(JobStatus.REVIEWING.value),
            "awaiting_human_approval_count": _c(JobStatus.AWAITING_HUMAN_APPROVAL.value),
            "publishing_count": _c(JobStatus.PUBLISHING.value),
            "failed_count": _c(JobStatus.FAILED.value),
            "rejected_count": _c(JobStatus.REJECTED.value),
            "completed_count": _c(JobStatus.COMPLETED.value),
            "stuck_count": stuck_count,
            "stuck_threshold_hours": 2,
            "published_generated_count": published_generated,
        }

    async def generate_micro_course(
        self,
        topic: str,
        subject: Optional[str] = None,
        grade_band: Optional[str] = None,
        difficulty: Optional[str] = None,
        locale: str = "en",
        requested_by_user_id: Optional[UUID] = None,
        generation_mode: str = "on_demand",
    ) -> ContentGenerationJob:
        """
        Create a micro-course generation job.

        - `on_demand`: run the workflow synchronously (blocking) and return the completed job.
        - `gap_detection`: enqueue an async `gap_detection` job for the background worker.
        """
        job = self.create_job(
            content_type="micro_course",
            topic=topic,
            subject=subject,
            grade_band=grade_band,
            difficulty=difficulty,
            locale=locale,
            requested_by_user_id=requested_by_user_id,
            generation_strategy=ContentGenerationStrategy.TOPIC_BASED.value,
            source="gap_detection" if generation_mode == "gap_detection" else None,
        )
        if generation_mode == "gap_detection":
            # Topic consistency: gap jobs are usually "Foundational teaching strategies for {subject}".
            if subject:
                job.topic = f"Foundational teaching strategies for {subject}"
                self.db.commit()
                self.db.refresh(job)
            return job

        orchestrator = GenerationOrchestratorService(self.db)
        return await orchestrator.run_micro_course_job(job.id)

    async def retry_job(self, job_id: UUID, requested_by_user_id: Optional[UUID] = None) -> ContentGenerationJob:
        """
        Retry a failed/rejected job by creating a fresh job with copied inputs.

        For `source=gap_detection`, returns a new pending async job.
        For other sources, runs orchestrator immediately and returns final state.
        """
        original = self.get_job(job_id)
        if not original:
            raise ContentFactoryServiceError(f"Job not found: {job_id}")
        if original.status not in (JobStatus.FAILED.value, JobStatus.REJECTED.value):
            raise ContentFactoryServiceError(
                f"Retry allowed only for failed/rejected jobs (current={original.status})"
            )

        new_job = ContentGenerationJob(
            requested_by_user_id=requested_by_user_id or original.requested_by_user_id,
            content_type=original.content_type,
            job_type=original.job_type or "micro_course",
            generation_strategy=original.generation_strategy or ContentGenerationStrategy.TOPIC_BASED.value,
            topic=original.topic,
            subject=original.subject,
            target_subject=original.target_subject,
            grade_band=original.grade_band,
            difficulty=original.difficulty,
            locale=original.locale,
            status=JobStatus.PENDING.value,
            current_step=None,
            retry_count=0,
            priority=original.priority or 0,
            source=original.source,
        )
        self.db.add(new_job)
        self.db.commit()
        self.db.refresh(new_job)

        if original.source == "gap_detection":
            return new_job

        orchestrator = GenerationOrchestratorService(self.db)
        return await orchestrator.run_micro_course_job(new_job.id)
