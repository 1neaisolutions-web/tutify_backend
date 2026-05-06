"""
Pipeline Run Service: track ML pipeline execution (start, status, runtime, errors).
"""
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.domains.teacher_intelligence.models import PipelineRun
from app.domains.teacher_intelligence.enums import PipelineRunStatus
from app.core.logging import get_logger

logger = get_logger(__name__)


class PipelineRunService:
    """Track pipeline runs for reproducibility and debugging."""

    def __init__(self, db: Session):
        self.db = db

    def start_run(
        self,
        teacher_id: UUID,
        pipeline_name: str,
        pipeline_version: str,
        model_version: str,
        feature_snapshot_id: Optional[UUID] = None,
    ) -> PipelineRun:
        """Create a new pipeline run with status=RUNNING, started_at=now."""
        started_at = datetime.now(timezone.utc)
        run = PipelineRun(
            teacher_id=teacher_id,
            pipeline_name=pipeline_name,
            pipeline_version=pipeline_version,
            model_version=model_version,
            feature_snapshot_id=feature_snapshot_id,
            status=PipelineRunStatus.RUNNING.value,
            started_at=started_at,
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        logger.info(
            "Pipeline run started id=%s teacher_id=%s pipeline=%s",
            run.id,
            teacher_id,
            pipeline_name,
        )
        return run

    def complete_run(
        self,
        run_id: UUID,
        runtime_ms: Optional[int] = None,
    ) -> Optional[PipelineRun]:
        """Set status=COMPLETED, completed_at=now, optional runtime_ms."""
        run = self.db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
        if not run:
            return None
        run.status = PipelineRunStatus.COMPLETED.value
        run.completed_at = datetime.now(timezone.utc)
        if runtime_ms is not None:
            run.runtime_ms = runtime_ms
        self.db.commit()
        self.db.refresh(run)
        logger.info("Pipeline run completed id=%s runtime_ms=%s", run_id, runtime_ms)
        return run

    def fail_run(
        self,
        run_id: UUID,
        error_message: Optional[str] = None,
        runtime_ms: Optional[int] = None,
    ) -> Optional[PipelineRun]:
        """Set status=FAILED, completed_at=now, error_message and optional runtime_ms."""
        run = self.db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
        if not run:
            return None
        run.status = PipelineRunStatus.FAILED.value
        run.completed_at = datetime.now(timezone.utc)
        if error_message is not None:
            run.error_message = error_message
        if runtime_ms is not None:
            run.runtime_ms = runtime_ms
        self.db.commit()
        self.db.refresh(run)
        logger.warning("Pipeline run failed id=%s error=%s", run_id, error_message)
        return run

    def get_run(self, run_id: UUID, teacher_id: Optional[UUID] = None) -> Optional[PipelineRun]:
        """Get a pipeline run by id, optionally scoped to teacher_id."""
        q = self.db.query(PipelineRun).filter(PipelineRun.id == run_id)
        if teacher_id is not None:
            q = q.filter(PipelineRun.teacher_id == teacher_id)
        return q.first()
