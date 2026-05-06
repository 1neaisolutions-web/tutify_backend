"""
Teacher Intelligence Freshness Orchestrator.

Coordinates snapshot refresh and pipeline2 rerun so Learning Hub home
always uses fresh intelligence. Does not modify snapshot or ml_output schemas.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.domains.teacher_intelligence.models import (
    TeacherFeatureSnapshot,
    MLOutput,
    PipelineRun,
)
from app.domains.teacher_intelligence.services.ctp_assembler_service import CTPAssemblerService
from app.domains.teacher_intelligence.services.feature_snapshot_service import (
    FeatureSnapshotService,
    _source_hash,
)
from app.domains.teacher_intelligence.services.ml_output_service import MLOutputService
from app.domains.teacher_intelligence.enums import PipelineRunStatus

logger = get_logger(__name__)

PIPELINE2_NAME = "pipeline2"


def _snapshot_max_age_cutoff() -> datetime:
    """Return cutoff datetime; snapshot older than this is considered stale."""
    days = getattr(settings, "FEATURE_SNAPSHOT_MAX_AGE_DAYS", 7)
    return datetime.now(timezone.utc) - timedelta(days=days)


def _ml_output_max_age_cutoff() -> datetime:
    """Return cutoff datetime; ml_output older than this is considered stale."""
    days = getattr(settings, "ML_OUTPUT_MAX_AGE_DAYS", 7)
    return datetime.now(timezone.utc) - timedelta(days=days)


class IntelligenceRefreshService:
    """Orchestrates feature snapshot and ML output freshness for a teacher."""

    def __init__(self, db: Session):
        self.db = db

    def needs_feature_snapshot_refresh(self, teacher_id: UUID) -> bool:
        """
        True if no snapshot, or CTP hash changed, or snapshot older than threshold.
        Uses same hash logic as FeatureSnapshotService.
        """
        snapshot_svc = FeatureSnapshotService(self.db)
        snapshot = snapshot_svc.get_latest(teacher_id)
        if not snapshot:
            return True

        assembler = CTPAssemblerService(self.db)
        ctp = assembler.assemble(teacher_id)
        current_hash = _source_hash(ctp)
        if current_hash != snapshot.source_hash:
            return True

        cutoff = _snapshot_max_age_cutoff()
        snap_dt = snapshot.generated_at
        if snap_dt.tzinfo is None:
            snap_dt = snap_dt.replace(tzinfo=timezone.utc)
        if snap_dt < cutoff:
            return True

        return False

    def needs_ml_output_refresh(
        self, teacher_id: UUID, pipeline_name: str = PIPELINE2_NAME
    ) -> bool:
        """
        True if no ml_output, or snapshot is newer than ml_output, or ml_output older than threshold.
        """
        snapshot_svc = FeatureSnapshotService(self.db)
        output_svc = MLOutputService(self.db)

        snapshot = snapshot_svc.get_latest(teacher_id)
        ml_output = output_svc.get_latest(teacher_id, pipeline_name=pipeline_name)

        if not ml_output:
            return True
        if not snapshot:
            return False

        snap_at = snapshot.generated_at
        out_at = ml_output.generated_at
        if getattr(snap_at, "tzinfo", None) is None:
            snap_at = snap_at.replace(tzinfo=timezone.utc)
        if getattr(out_at, "tzinfo", None) is None:
            out_at = out_at.replace(tzinfo=timezone.utc)
        if snap_at > out_at:
            return True

        cutoff = _ml_output_max_age_cutoff()
        if out_at < cutoff:
            return True

        return False

    def ensure_feature_snapshot(self, teacher_id: UUID) -> TeacherFeatureSnapshot:
        """Return latest snapshot; generate new one if needs_feature_snapshot_refresh."""
        snapshot_svc = FeatureSnapshotService(self.db)
        if self.needs_feature_snapshot_refresh(teacher_id):
            logger.info("Refreshing feature snapshot for teacher %s", teacher_id)
            return snapshot_svc.generate_snapshot(teacher_id)
        snapshot = snapshot_svc.get_latest(teacher_id)
        if not snapshot:
            logger.info("Refreshing feature snapshot for teacher %s (no snapshot)", teacher_id)
            return snapshot_svc.generate_snapshot(teacher_id)
        return snapshot

    def ensure_pipeline2_output(self, teacher_id: UUID) -> Optional[MLOutput]:
        """
        Return latest pipeline2 ML output; run pipeline2 if needed.
        If a run is already in progress for this teacher+pipeline2, do NOT start another;
        return existing ml_output if present, else None.
        """
        output_svc = MLOutputService(self.db)

        running = (
            self.db.query(PipelineRun)
            .filter(
                PipelineRun.teacher_id == teacher_id,
                PipelineRun.pipeline_name == PIPELINE2_NAME,
                PipelineRun.status == PipelineRunStatus.RUNNING.value,
            )
            .first()
        )
        if running:
            existing = output_svc.get_latest(teacher_id, pipeline_name=PIPELINE2_NAME)
            return existing

        snapshot = self.ensure_feature_snapshot(teacher_id)
        if not self.needs_ml_output_refresh(teacher_id, pipeline_name=PIPELINE2_NAME):
            return output_svc.get_latest(teacher_id, pipeline_name=PIPELINE2_NAME)

        logger.info("Running pipeline2 for teacher %s", teacher_id)
        try:
            from app.domains.learning_hub.services.pipeline2_integration_service import (
                Pipeline2IntegrationService,
            )
            integration = Pipeline2IntegrationService(self.db)
            return integration.run_pipeline2_for_teacher(teacher_id)
        except Exception as e:
            logger.warning("Pipeline2 run failed for teacher %s: %s", teacher_id, e)
            return output_svc.get_latest(teacher_id, pipeline_name=PIPELINE2_NAME)

    def ensure_fresh_teacher_intelligence(
        self, teacher_id: UUID
    ) -> Dict[str, Any]:
        """
        Single orchestration entrypoint: ensure fresh snapshot and pipeline2 output.
        Returns {"feature_snapshot": snapshot, "ml_output": ml_output}.
        """
        snapshot = self.ensure_feature_snapshot(teacher_id)
        ml_output = self.ensure_pipeline2_output(teacher_id)
        return {
            "feature_snapshot": snapshot,
            "ml_output": ml_output,
        }
