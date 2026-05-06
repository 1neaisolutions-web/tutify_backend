"""
Content Review Service: manage human review / approval for content generation jobs.
"""
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domains.content_factory.enums import JobStatus
from app.domains.content_factory.models import (
    ContentGenerationJob,
    ContentGenerationReview,
)
from app.domains.content_factory.services.publishing_service import PublishingService

logger = get_logger(__name__)


class ContentReviewServiceError(Exception):
    """Raised when review operation is invalid."""

    pass


class ContentReviewService:
    """Create and read human review records, and drive approval / rejection flow."""

    def __init__(self, db: Session):
        self.db = db
        self._publishing = PublishingService(db)

    def _get_job(self, job_id: UUID) -> ContentGenerationJob:
        job = (
            self.db.query(ContentGenerationJob)
            .filter(ContentGenerationJob.id == job_id)
            .first()
        )
        if not job:
            raise ContentReviewServiceError(f"Job not found: {job_id}")
        return job

    def get_latest_review(self, job_id: UUID) -> Optional[ContentGenerationReview]:
        return (
            self.db.query(ContentGenerationReview)
            .filter(ContentGenerationReview.job_id == job_id)
            .order_by(ContentGenerationReview.created_at.desc())
            .first()
        )

    def list_reviews(self, job_id: UUID) -> List[ContentGenerationReview]:
        return (
            self.db.query(ContentGenerationReview)
            .filter(ContentGenerationReview.job_id == job_id)
            .order_by(ContentGenerationReview.created_at.asc())
            .all()
        )

    def _create_review(
        self,
        *,
        job_id: UUID,
        reviewer_user_id: UUID,
        decision: str,
        notes: Optional[str] = None,
        review_metadata: Optional[dict] = None,
    ) -> ContentGenerationReview:
        review = ContentGenerationReview(
            job_id=job_id,
            reviewer_user_id=reviewer_user_id,
            decision=decision,
            notes=notes,
            review_metadata=review_metadata or {},
        )
        self.db.add(review)
        self.db.commit()
        self.db.refresh(review)
        return review

    def approve_job(
        self,
        job_id: UUID,
        reviewer_user_id: UUID,
        notes: Optional[str] = None,
    ) -> ContentGenerationJob:
        job = self._get_job(job_id)
        if job.status != JobStatus.AWAITING_HUMAN_APPROVAL.value:
            raise ContentReviewServiceError(
                f"Job {job_id} is not awaiting human approval (status={job.status})"
            )

        review = self._create_review(
            job_id=job.id,
            reviewer_user_id=reviewer_user_id,
            decision="approved",
            notes=notes,
        )

        if job.result_content_id:
            # Already published; keep idempotent
            logger.info(
                "Approve job called but job already has result_content_id; job_id=%s content_id=%s",
                job.id,
                job.result_content_id,
            )
            job.status = JobStatus.COMPLETED.value
            job.review_required = 0
            job.approved_by_user_id = reviewer_user_id
            job.approved_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(job)
            return job

        logger.info(
            "Human approval granted, starting publish; job_id=%s reviewer_user_id=%s review_id=%s",
            job.id,
            reviewer_user_id,
            review.id,
        )
        job.status = JobStatus.PUBLISHING.value
        self.db.commit()
        self.db.refresh(job)

        content_id = self._publishing.publish_micro_course(
            full_content=job.step_outputs,
            topic=job.topic,
            subject=job.subject,
            grade_band=job.grade_band,
            difficulty=job.difficulty,
            locale=job.locale,
            job_id=job.id,
        )

        job.status = JobStatus.COMPLETED.value
        job.result_content_id = content_id
        job.review_required = 0
        job.approved_by_user_id = reviewer_user_id
        job.approved_at = datetime.now(timezone.utc)
        job.rejection_reason = None
        job.completed_at = job.completed_at or datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(job)
        logger.info(
            "Job approved and published; job_id=%s content_id=%s reviewer_user_id=%s",
            job.id,
            content_id,
            reviewer_user_id,
        )
        return job

    def reject_job(
        self,
        job_id: UUID,
        reviewer_user_id: UUID,
        notes: Optional[str] = None,
    ) -> ContentGenerationJob:
        job = self._get_job(job_id)
        if job.status != JobStatus.AWAITING_HUMAN_APPROVAL.value:
            raise ContentReviewServiceError(
                f"Job {job_id} is not awaiting human approval (status={job.status})"
            )

        review = self._create_review(
            job_id=job.id,
            reviewer_user_id=reviewer_user_id,
            decision="rejected",
            notes=notes,
        )
        job.status = JobStatus.REJECTED.value
        job.rejection_reason = notes
        job.review_required = 0
        job.completed_at = job.completed_at or datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(job)
        logger.info(
            "Job rejected; job_id=%s reviewer_user_id=%s review_id=%s reason=%s",
            job.id,
            reviewer_user_id,
            review.id,
            notes,
        )
        return job

    def request_changes(
        self,
        job_id: UUID,
        reviewer_user_id: UUID,
        notes: Optional[str] = None,
    ) -> ContentGenerationJob:
        """
        Request changes: job remains not published, and status is moved back to REVIEWING.
        This allows a future regeneration or manual adjustments.
        """
        job = self._get_job(job_id)
        if job.status != JobStatus.AWAITING_HUMAN_APPROVAL.value:
            raise ContentReviewServiceError(
                f"Job {job_id} is not awaiting human approval (status={job.status})"
            )

        review = self._create_review(
            job_id=job.id,
            reviewer_user_id=reviewer_user_id,
            decision="needs_changes",
            notes=notes,
        )
        job.status = JobStatus.REVIEWING.value
        job.rejection_reason = notes
        job.review_required = 1
        self.db.commit()
        self.db.refresh(job)
        logger.info(
            "Job changes requested; job_id=%s reviewer_user_id=%s review_id=%s notes=%s",
            job.id,
            reviewer_user_id,
            review.id,
            notes,
        )
        return job

