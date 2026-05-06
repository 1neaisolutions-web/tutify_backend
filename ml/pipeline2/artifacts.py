from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import joblib

BASE_DIR = Path(__file__).resolve().parents[2]
REGISTRY_BASE = BASE_DIR / "model_registry" / "pipeline2"


def ensure_registry_dir() -> None:
    REGISTRY_BASE.mkdir(parents=True, exist_ok=True)


def get_version_path(version: str) -> Path:
    ensure_registry_dir()
    return REGISTRY_BASE / version


def resolve_latest_version() -> Optional[str]:
    """
    Return the latest version directory name, if any.
    """
    if not REGISTRY_BASE.exists():
        return None
    versions = sorted(
        [p.name for p in REGISTRY_BASE.iterdir() if p.is_dir()],
        reverse=True,
    )
    return versions[0] if versions else None


def resolve_version_arg(version: str) -> Optional[str]:
    """
    Resolve a version argument, supporting the special value 'latest'.
    """
    if version == "latest":
        return resolve_latest_version()
    return version


def save_model_artifacts(
    version: str,
    model_obj: Any,
    feature_spec: Dict[str, Any],
    metrics: Dict[str, Any],
    manifest: Dict[str, Any],
) -> Path:
    """
    Persist all model artifacts for a training run.

    Files written:
      - model.pkl
      - feature_spec.json
      - metrics.json
      - manifest.json
    """
    version_dir = get_version_path(version)
    version_dir.mkdir(parents=True, exist_ok=True)

    joblib.dump(model_obj, version_dir / "model.pkl")

    with (version_dir / "feature_spec.json").open("w", encoding="utf-8") as f:
        json.dump(feature_spec, f, indent=2, default=str)

    with (version_dir / "metrics.json").open("w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, default=str)

    with (version_dir / "manifest.json").open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, default=str)

    return version_dir


def load_model_artifacts(version: str) -> Tuple[Any, Dict[str, Any]]:
    """
    Load the model object and feature spec for a given version.

    Returns:
        (model_obj, feature_spec_dict)
    """
    version_dir = get_version_path(version)
    model_obj = joblib.load(version_dir / "model.pkl")

    with (version_dir / "feature_spec.json").open("r", encoding="utf-8") as f:
        feature_spec = json.load(f)

    return model_obj, feature_spec

