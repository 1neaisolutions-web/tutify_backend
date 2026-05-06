from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict


EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
TEXT_COLUMN = "Teacher_profile"
K_MIN = 2
K_MAX = 15
RANDOM_STATE = 42


@dataclass
class FeatureSpec:
    text_column: str = TEXT_COLUMN
    embedding_model: str = EMBEDDING_MODEL_NAME
    k_min: int = K_MIN
    k_max: int = K_MAX
    random_state: int = RANDOM_STATE
    normalization: str = "l2"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def default_feature_spec() -> FeatureSpec:
    return FeatureSpec()


def save_feature_spec(path: Path, spec: FeatureSpec) -> None:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(spec.to_dict(), f, indent=2)

