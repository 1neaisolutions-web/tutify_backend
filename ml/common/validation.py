from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable, List

import pandas as pd


def compute_dataset_hash(path: str | Path) -> str:
    """
    Compute a stable hash for the dataset file.

    Uses SHA256 over the raw file bytes to avoid depending on
    pandas/version-specific serialization details.
    """
    file_path = Path(path)
    h = hashlib.sha256()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_required_columns(df: pd.DataFrame, required_columns: Iterable[str]) -> None:
    """
    Ensure all required columns exist in the dataframe.

    Raises:
        ValueError: if any required columns are missing.
    """
    required: List[str] = list(required_columns)
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")

