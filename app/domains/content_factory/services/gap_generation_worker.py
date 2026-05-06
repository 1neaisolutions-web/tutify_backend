"""
Background worker utilities for processing gap_detection jobs.

This module is intended to be called from a scheduled task or CLI, not from
the request/response path. It pulls pending jobs and delegates to the
GenerationOrchestratorService, which publishes content into content_registry.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.config import settings
from app.llm.config import llm_settings
from app.db.session import SessionLocal
from app.domains.content_factory.enums import JobStatus
from app.domains.content_factory.models import ContentGenerationJob
from app.domains.content_factory.services.generation_orchestrator_service import (
    GenerationOrchestratorService,
)

logger = get_logger(__name__)


def pending_gap_worker_job_filters(personalization_llm_outbound_enabled: bool):
    """
    SQLAlchemy filter clauses for GapGenerationWorker pending-job selection.

    When personalization outbound LLM is disabled, drop personalization inventory jobs and
    user-attributed gap_detection jobs (created by personalization), but keep platform
    gap_detection jobs (requested_by_user_id is NULL).
    """
    base = [
        ContentGenerationJob.source.in_(["gap_detection", "inventory_expansion"]),
        ContentGenerationJob.status == JobStatus.PENDING.value,
    ]
    if personalization_llm_outbound_enabled:
        return base
    return base + [
        (ContentGenerationJob.source != "inventory_expansion")
        & (
            (ContentGenerationJob.source != "gap_detection")
            | (ContentGenerationJob.requested_by_user_id.is_(None))
        )
    ]


class GapGenerationWorker:
    """Simple async worker loop for gap-detection jobs."""

    def __init__(self, db: Session | None = None):
        """Pass a session when using sync helpers on this instance; ``process_once`` uses its own sessions."""
        self.db = db

    def _recover_stale_running_jobs(self, stale_after_hours: int = 2) -> int:
        """
        Mark stale running gap jobs as failed so they don't block future generation.
        A stale job is source=gap_detection, status=running, updated_at older than threshold.
        """
        threshold = datetime.now(timezone.utc) - timedelta(hours=stale_after_hours)
        stale = (
            self.db.query(ContentGenerationJob)
            .filter(
                ContentGenerationJob.source == "gap_detection",
                ContentGenerationJob.status == JobStatus.RUNNING.value,
                ContentGenerationJob.updated_at < threshold,
            )
            .all()
        )
        if not stale:
            return 0
        now = datetime.now(timezone.utc)
        for job in stale:
            job.status = JobStatus.FAILED.value
            job.error_message = (
                f"Marked failed by stale-job recovery after >{stale_after_hours}h without progress"
            )
            job.completed_at = now
            job.current_step = "stale_recovery"
        self.db.commit()
        logger.warning("Recovered stale running gap jobs count=%s", len(stale))
        return len(stale)

    def _next_pending_job(self) -> Optional[ContentGenerationJob]:
        q = self.db.query(ContentGenerationJob).filter(
            *pending_gap_worker_job_filters(llm_settings.PERSONALIZATION_LLM_OUTBOUND_ENABLED)
        )
        return q.order_by(ContentGenerationJob.created_at.asc()).first()

    def _sync_recover_and_pick_next_job_id(self) -> Optional[UUID]:
        """Run blocking DB work in a dedicated session (thread-safe)."""
        self._recover_stale_running_jobs()
        job = self._next_pending_job()
        return job.id if job else None

    async def process_once(self) -> Optional[ContentGenerationJob]:
        """
        Process a single pending gap_detection job, if any.

        Returns the job after orchestration completes or None if no job was found.

        Stale recovery + next-job lookup run in a thread pool so the asyncio event loop
        can still serve HTTP (demo / production stability).
        """
        if not settings.LEARNING_HUB_AUTO_LLM_ENABLED:
            # Hub automation off: never run gap/inventory LLM jobs (defense if worker is invoked manually).
            return None

        def _thread_pick_job() -> Optional[UUID]:
            db = SessionLocal()
            try:
                w = GapGenerationWorker(db)
                return w._sync_recover_and_pick_next_job_id()
            finally:
                db.close()

        job_id = await asyncio.to_thread(_thread_pick_job)
        if not job_id:
            return None

        logger.info("GapGenerationWorker starting job id=%s", job_id)
        db2 = SessionLocal()
        try:
            orch = GenerationOrchestratorService(db2)
            result = await orch.run_job(job_id)
        finally:
            db2.close()

        logger.info(
            "GapGenerationWorker completed job id=%s status=%s result_content_id=%s",
            result.id,
            result.status,
            result.result_content_id,
        )

        # Reconcile personalization inventory after new content is published.
        # Without this, content_registry can advance while personalized assignments/slates
        # remain stale, making the Learning Hub loader appear "stuck".
        try:
            if result.status == "completed" and getattr(result, "requested_by_user_id", None):
                from app.domains.personalization.services.inventory_expansion_worker import InventoryExpansionWorker

                InventoryExpansionWorker.run_in_background(
                    result.requested_by_user_id,
                    trigger=f"after_content_publish:{result.content_type}",
                )
        except Exception:
            # Best-effort only.
            pass
        return result

