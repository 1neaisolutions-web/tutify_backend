"""
ML Output Service: save pipeline results, link to feature snapshot, manage is_latest.
"""
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.domains.teacher_intelligence.models import MLOutput
from app.core.logging import get_logger

logger = get_logger(__name__)


class MLOutputService:
    """Save and retrieve ML pipeline outputs."""

    def __init__(self, db: Session):
        self.db = db

    def save_output(
        self,
        teacher_id: UUID,
        pipeline_name: str,
        pipeline_version: str,
        model_version: str,
        results: Dict[str, Any],
        feature_snapshot_id: Optional[UUID] = None,
        confidence_score: Optional[float] = None,
    ) -> MLOutput:
        """
        Save new ML output, mark previous outputs for this teacher+pipeline as is_latest=False.
        """
        self.db.query(MLOutput).filter(
            MLOutput.teacher_id == teacher_id,
            MLOutput.pipeline_name == pipeline_name,
        ).update({"is_latest": False})

        generated_at = datetime.now(timezone.utc)
        output = MLOutput(
            teacher_id=teacher_id,
            pipeline_name=pipeline_name,
            pipeline_version=pipeline_version,
            model_version=model_version,
            feature_snapshot_id=feature_snapshot_id,
            generated_at=generated_at,
            results=results,
            confidence_score=confidence_score,
            is_latest=True,
        )
        self.db.add(output)
        self.db.commit()
        self.db.refresh(output)
        logger.info(
            "ML output saved id=%s teacher_id=%s pipeline=%s",
            output.id,
            teacher_id,
            pipeline_name,
        )
        return output

    def get_latest(
        self, teacher_id: UUID, pipeline_name: Optional[str] = None
    ) -> Optional[MLOutput]:
        """Get latest ML output for teacher, optionally filtered by pipeline_name."""
        q = self.db.query(MLOutput).filter(
            MLOutput.teacher_id == teacher_id,
            MLOutput.is_latest == True,
        )
        if pipeline_name:
            q = q.filter(MLOutput.pipeline_name == pipeline_name)
        return q.first()
