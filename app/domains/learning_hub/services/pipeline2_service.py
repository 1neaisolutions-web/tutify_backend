from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from ml.pipeline2 import dataset as pipeline2_dataset
from ml.pipeline2 import model as pipeline2_model


class Pipeline2Service:
    """
    Service layer wrapper around the pipeline2 clustering model.

    For now this reads from a local CSV file. The interface is designed so
    that future implementations can source data from the database instead.
    """

    def __init__(self, model_version: str = "latest") -> None:
        self.model_version = model_version
        self._model = pipeline2_model.load_model(version=model_version)

    def predict_from_csv(
        self,
        csv_path: str | Path,
        persist_profile_path: Optional[str | Path] = None,
    ) -> List[Dict[str, Any]]:
        """
        Run clustering predictions for the given CSV file.

        Returns a list of records containing identifiers (if present) and
        the assigned cluster label for each row.
        """
        df = pipeline2_dataset.load_dataset(csv_path)

        if persist_profile_path is not None:
            out_path = Path(persist_profile_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(out_path, index=False)

        labels = self._model.predict(df)
        df_with_preds = df.copy()
        df_with_preds["cluster_label"] = labels

        records: List[Dict[str, Any]] = []

        id_column = None
        for candidate in ("Teacher_ID", "id", "teacher_id"):
            if candidate in df_with_preds.columns:
                id_column = candidate
                break

        for idx, row in df_with_preds.iterrows():
            record: Dict[str, Any] = {
                "row_index": int(idx),
                "cluster_label": int(row["cluster_label"]),
            }
            if id_column is not None:
                record[id_column] = row[id_column]
            records.append(record)

        return records

