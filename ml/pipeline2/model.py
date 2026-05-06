from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.preprocessing import normalize

from ml.common.logging import log_event, start_run
from ml.common.validation import compute_dataset_hash
from ml.pipeline2 import dataset as dataset_module
from ml.pipeline2.artifacts import (
    load_model_artifacts,
    resolve_latest_version,
    resolve_version_arg,
)
from ml.pipeline2.feature_spec import EMBEDDING_MODEL_NAME, TEXT_COLUMN


class Pipeline2Model:
    """
    In-memory wrapper for the trained clustering model.
    """

    def __init__(self, model_obj: Dict[str, Any], feature_spec: Dict[str, Any]) -> None:
        self._kmeans = model_obj["kmeans"]
        self._embedding_model_name = model_obj.get(
            "embedding_model_name",
            EMBEDDING_MODEL_NAME,
        )
        self._feature_spec = feature_spec
        self._encoder = SentenceTransformer(self._embedding_model_name)

    @property
    def feature_spec(self) -> Dict[str, Any]:
        return self._feature_spec

    def predict(self, df) -> List[int]:
        """
        Predict cluster assignments for the given dataframe.

        The dataframe must already contain a Teacher_profile column.
        """
        texts = df[self._feature_spec.get("text_column", TEXT_COLUMN)].astype(str).tolist()
        embeddings = self._encoder.encode(
            texts,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        embeddings = normalize(embeddings)
        labels = self._kmeans.predict(embeddings)
        return [int(label) for label in labels]

    def predict_from_profile_text(self, profile_text: str) -> int:
        """
        Predict cluster assignment for a single Teacher_profile text string.

        Used by DB integration (e.g. Learning Hub) when the input is a
        feature snapshot converted to profile text via snapshot_adapter.
        Does not change existing CSV/CLI behavior.
        """
        import pandas as pd

        text_col = self._feature_spec.get("text_column", TEXT_COLUMN)
        df = pd.DataFrame([{text_col: profile_text}])
        labels = self.predict(df)
        return labels[0]


def load_model(version: str = "latest") -> Pipeline2Model:
    """
    Load a trained model version into memory.
    """
    resolved = resolve_version_arg(version)
    if resolved is None:
        raise ValueError("No trained pipeline2 model version found.")

    model_obj, feature_spec = load_model_artifacts(resolved)
    return Pipeline2Model(model_obj=model_obj, feature_spec=feature_spec)


def predict(
    input_path: str | Path,
    version: str = "latest",
    persist_profile_path: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """
    High-level prediction API used by CLI and service layer.

    Loads the specified model version (or latest), prepares the dataset,
    and returns cluster assignments.
    """
    resolved_version = resolve_version_arg(version)
    if resolved_version is None:
        raise ValueError("No trained pipeline2 model version found.")

    dataset_hash = compute_dataset_hash(input_path)
    context = start_run(model_version=resolved_version, dataset_hash=dataset_hash)

    log_event(context, status="STARTED", message="pipeline2 prediction started")

    try:
        df = dataset_module.load_dataset(input_path)

        if persist_profile_path is not None:
            out_path = Path(persist_profile_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(out_path, index=False)

        model = load_model(resolved_version)
        labels = model.predict(df)

        # Attach predictions to df for convenience
        df_with_preds = df.copy()
        df_with_preds["cluster_label"] = labels

        extra = {
            "num_rows": len(df),
        }
        log_event(
            context,
            status="SUCCESS",
            message="pipeline2 prediction completed",
            extra=extra,
        )

        return {
            "version": resolved_version,
            "num_rows": len(df),
            "cluster_labels": labels,
        }
    except Exception as exc:
        log_event(
            context,
            status="FAILURE",
            message="pipeline2 prediction failed",
            error=str(exc),
        )
        raise

