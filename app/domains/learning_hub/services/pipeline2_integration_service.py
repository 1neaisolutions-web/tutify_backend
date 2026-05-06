"""
Pipeline2 DB integration: run inference from feature snapshot and persist run + output.
Uses teacher_intelligence services; does not duplicate their logic.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.domains.teacher_intelligence.models import MLOutput
from app.domains.teacher_intelligence.services import (
    FeatureSnapshotService,
    MLOutputService,
    PipelineRunService,
)
from app.core.logging import get_logger

logger = get_logger(__name__)

PIPELINE_NAME = "pipeline2"


def _build_v1_results(cluster_label: int) -> Dict[str, Any]:
    """Normalize Pipeline2 output to V1 ml_outputs.results shape, including persona enrichment."""
    from ml.pipeline2.snapshot_adapter import get_persona_for_cluster
    persona = get_persona_for_cluster(cluster_label)
    return {
        "cluster_id": str(cluster_label),
        "persona_tag": persona["tag"],
        "persona_description": persona["description"],
        "top_gaps": persona["top_gaps"],
        "recommended_targets": persona["recommended_targets"],
        "pipeline_source": "pipeline2",
    }


def _get_model_confidence(resolved_version: str) -> Optional[float]:
    """Load silhouette score for the selected K from metrics.json as confidence proxy."""
    try:
        from ml.pipeline2.artifacts import get_artifact_path
        import json, pathlib
        metrics_path = pathlib.Path(get_artifact_path(resolved_version, "metrics.json"))
        if not metrics_path.exists():
            return None
        metrics = json.loads(metrics_path.read_text())
        selected_k = metrics.get("selected_k")
        silhouette_scores = metrics.get("silhouette_scores") or []
        k_min = metrics.get("k_min", 2)
        if selected_k is None or not silhouette_scores:
            return None
        idx = int(selected_k) - int(k_min)
        if 0 <= idx < len(silhouette_scores):
            score = float(silhouette_scores[idx])
            return max(0.0, min(1.0, score))
    except Exception:
        pass
    return None


class Pipeline2IntegrationService:
    """Run Pipeline2 from DB feature snapshot and persist run + ML output."""

    def __init__(self, db: Session):
        self.db = db

    def run_pipeline2_for_teacher(self, teacher_id: UUID) -> MLOutput:
        """
        Load latest snapshot, start pipeline run, run inference, save output, complete run.
        Returns the saved MLOutput. Raises on failure (run is marked failed).
        """
        from ml.pipeline2.artifacts import resolve_version_arg
        from ml.pipeline2.model import load_model
        from ml.pipeline2.snapshot_adapter import snapshot_features_to_teacher_profile

        snapshot_svc = FeatureSnapshotService(self.db)
        run_svc = PipelineRunService(self.db)
        output_svc = MLOutputService(self.db)

        snapshot = snapshot_svc.get_latest(teacher_id)
        if not snapshot:
            raise ValueError("No feature snapshot found. Generate one via POST /teacher-intelligence/feature-snapshot first.")

        resolved_version = resolve_version_arg("latest")
        if not resolved_version:
            raise ValueError("No trained pipeline2 model version found. Train via: tools/ml/run_pipeline2_local.py train.")

        pipeline_version = resolved_version
        model_version = resolved_version

        run = run_svc.start_run(
            teacher_id=teacher_id,
            pipeline_name=PIPELINE_NAME,
            pipeline_version=pipeline_version,
            model_version=model_version,
            feature_snapshot_id=snapshot.id,
        )
        started = time.perf_counter()

        try:
            profile_text = snapshot_features_to_teacher_profile(snapshot.features)
            model = load_model(resolved_version)
            cluster_label = model.predict_from_profile_text(profile_text)
            results = _build_v1_results(cluster_label)
            confidence_score = _get_model_confidence(resolved_version)

            output = output_svc.save_output(
                teacher_id=teacher_id,
                pipeline_name=PIPELINE_NAME,
                pipeline_version=pipeline_version,
                model_version=model_version,
                results=results,
                feature_snapshot_id=snapshot.id,
                confidence_score=confidence_score,
            )
            logger.info(
                "Pipeline2 persona assigned teacher_id=%s cluster_id=%s persona_tag=%s confidence=%.3f",
                teacher_id,
                cluster_label,
                results.get("persona_tag"),
                confidence_score or 0.0,
            )

            runtime_ms = int((time.perf_counter() - started) * 1000)
            run_svc.complete_run(run.id, runtime_ms=runtime_ms)
            logger.info(
                "Pipeline2 completed teacher_id=%s cluster_id=%s runtime_ms=%s",
                teacher_id,
                cluster_label,
                runtime_ms,
            )
            return output
        except Exception as e:
            runtime_ms = int((time.perf_counter() - started) * 1000)
            run_svc.fail_run(run.id, error_message=str(e), runtime_ms=runtime_ms)
            logger.warning("Pipeline2 failed teacher_id=%s error=%s", teacher_id, e)
            raise
