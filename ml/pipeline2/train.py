from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, Tuple

import numpy as np
from kneed import KneeLocator
from sentence_transformers import SentenceTransformer
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import normalize

from ml.common.logging import log_event, start_run
from ml.common.validation import compute_dataset_hash
from ml.pipeline2 import dataset as dataset_module
from ml.pipeline2.artifacts import save_model_artifacts
from ml.pipeline2.feature_spec import (
    EMBEDDING_MODEL_NAME,
    K_MAX,
    K_MIN,
    RANDOM_STATE,
    default_feature_spec,
)


def _compute_k_metrics(
    embeddings: np.ndarray,
    k_min: int = K_MIN,
    k_max: int = K_MAX,
) -> Tuple[int, Dict[str, Any]]:
    """
    Run KMeans for a range of K and select the optimal value.
    """
    inertias = []
    silhouettes = []
    k_values = list(range(k_min, k_max + 1))

    for k in k_values:
        kmeans = KMeans(
            n_clusters=k,
            random_state=RANDOM_STATE,
            n_init="auto",
            init="k-means++",
        )
        labels = kmeans.fit_predict(embeddings)
        inertias.append(float(kmeans.inertia_))

        # Silhouette score requires at least 2 clusters and less than n_samples.
        if len(set(labels)) > 1 and len(set(labels)) < len(labels):
            silhouettes.append(float(silhouette_score(embeddings, labels)))
        else:
            silhouettes.append(float("nan"))

    # Try KneeLocator on inertia
    kl = KneeLocator(
        k_values,
        inertias,
        curve="convex",
        direction="decreasing",
    )
    elbow_k = kl.elbow

    # Fallback: best silhouette
    if elbow_k is None:
        max_sil = max(
            (s for s in silhouettes if not np.isnan(s)),
            default=float("nan"),
        )
        # Choose smallest k among those with max silhouette
        candidate_indices = [
            idx
            for idx, s in enumerate(silhouettes)
            if not np.isnan(s) and s == max_sil
        ]
        if not candidate_indices:
            # As an extreme fallback, pick the smallest K
            best_k = k_values[0]
        else:
            best_k = k_values[min(candidate_indices)]
        k_reason = "silhouette"
    else:
        best_k = int(elbow_k)
        k_reason = "knee"

    metrics: Dict[str, Any] = {
        "k_values": k_values,
        "inertia": inertias,
        "silhouette": silhouettes,
        "selected_k": best_k,
        "k_selection_method": k_reason,
    }
    return best_k, metrics


def _build_manifest(
    dataset_hash: str,
    version: str,
) -> Dict[str, Any]:
    import datetime
    import platform

    try:
        import sentence_transformers as st_pkg
    except Exception:
        st_pkg = None

    try:
        import sklearn as sk_pkg
    except Exception:
        sk_pkg = None

    try:
        import pandas as pd_pkg
    except Exception:
        pd_pkg = None

    try:
        import numpy as np_pkg
    except Exception:
        np_pkg = None

    try:
        import kneed as kneed_pkg
    except Exception:
        kneed_pkg = None

    try:
        import joblib as joblib_pkg
    except Exception:
        joblib_pkg = None

    # Best-effort git commit hash
    git_commit_hash = None
    try:
        import subprocess

        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            text=True,
        )
        if result.returncode == 0:
            git_commit_hash = result.stdout.strip()
    except Exception:
        git_commit_hash = None

    timestamp = datetime.datetime.utcnow().isoformat() + "Z"

    return {
        "timestamp": timestamp,
        "model_version": version,
        "python_version": sys.version,
        "platform": platform.platform(),
        "library_versions": {
            "sentence-transformers": getattr(st_pkg, "__version__", None),
            "scikit-learn": getattr(sk_pkg, "__version__", None),
            "pandas": getattr(pd_pkg, "__version__", None),
            "numpy": getattr(np_pkg, "__version__", None),
            "kneed": getattr(kneed_pkg, "__version__", None),
            "joblib": getattr(joblib_pkg, "__version__", None),
        },
        "dataset_hash": dataset_hash,
        "git_commit_hash": git_commit_hash,
    }


def train(
    input_path: str | Path,
    version: str,
) -> Dict[str, Any]:
    """
    Train the clustering model for pipeline2.

    Returns training metadata including selected K and metrics.
    """
    dataset_hash = compute_dataset_hash(input_path)
    context = start_run(model_version=version, dataset_hash=dataset_hash)

    log_event(context, status="STARTED", message="pipeline2 training started")

    try:
        df = dataset_module.load_dataset(input_path)

        feature_spec_obj = default_feature_spec()
        texts = df[feature_spec_obj.text_column].astype(str).tolist()

        # Embeddings
        encoder = SentenceTransformer(EMBEDDING_MODEL_NAME)
        embeddings = encoder.encode(
            texts,
            show_progress_bar=False,
            convert_to_numpy=True,
        )

        # Normalize (L2) for cosine-like behavior
        embeddings = normalize(embeddings)

        # Determine best K
        best_k, k_metrics = _compute_k_metrics(embeddings)

        # Final model
        kmeans = KMeans(
            n_clusters=best_k,
            random_state=RANDOM_STATE,
            n_init="auto",
            init="k-means++",
        )
        labels = kmeans.fit_predict(embeddings)

        # Metrics
        final_silhouette = float(silhouette_score(embeddings, labels))
        final_inertia = float(kmeans.inertia_)
        cluster_counts: Dict[int, int] = {}
        for label in labels:
            cluster_counts[int(label)] = cluster_counts.get(int(label), 0) + 1

        metrics: Dict[str, Any] = {
            "final_silhouette_score": final_silhouette,
            "final_inertia": final_inertia,
            "cluster_counts": cluster_counts,
        }
        metrics.update(k_metrics)

        manifest = _build_manifest(dataset_hash=dataset_hash, version=version)

        model_obj = {
            "kmeans": kmeans,
            "embedding_model_name": EMBEDDING_MODEL_NAME,
            "feature_spec": feature_spec_obj.to_dict(),
        }

        feature_spec_dict = feature_spec_obj.to_dict()
        version_dir = save_model_artifacts(
            version=version,
            model_obj=model_obj,
            feature_spec=feature_spec_dict,
            metrics=metrics,
            manifest=manifest,
        )

        extra = {
            "version_dir": str(version_dir),
            "selected_k": best_k,
            "metrics": metrics,
        }
        log_event(
            context,
            status="SUCCESS",
            message="pipeline2 training completed",
            extra=extra,
        )

        return {
            "version": version,
            "version_dir": str(version_dir),
            "selected_k": best_k,
            "metrics": metrics,
        }
    except Exception as exc:
        log_event(
            context,
            status="FAILURE",
            message="pipeline2 training failed",
            error=str(exc),
        )
        raise

