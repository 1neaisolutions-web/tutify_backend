from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Optional

from ml.pipeline2 import dataset as dataset_module
from ml.pipeline2 import model as model_module
from ml.pipeline2.train import train as train_pipeline

BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = BASE_DIR / "Dummy_Teachers_Data_version2.csv"
DEFAULT_OUTPUT_PREDICTIONS = BASE_DIR / "outputs" / "pipeline2" / "predictions.json"


def _ensure_output_dirs() -> None:
    (BASE_DIR / "outputs" / "pipeline2").mkdir(parents=True, exist_ok=True)


def _persist_profile_if_requested(df, persist_path: Optional[str | Path]) -> None:
    if not persist_path:
        return
    out_path = Path(persist_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)


def handle_train(args: argparse.Namespace) -> None:
    input_path: Path = Path(args.input or DEFAULT_INPUT)
    version: str = args.version

    result = train_pipeline(input_path=input_path, version=version)
    # CLI is intentionally quiet; structured info goes to logs and artifacts.


def handle_predict(args: argparse.Namespace) -> None:
    _ensure_output_dirs()

    input_path: Path = Path(args.input or DEFAULT_INPUT)
    version: str = args.version or "latest"
    out_path: Path = Path(args.out or DEFAULT_OUTPUT_PREDICTIONS)

    persist_profile_path: Optional[str | Path] = args.persist_profile

    # Use high-level prediction API
    prediction_result = model_module.predict(
        input_path=input_path,
        version=version,
        persist_profile_path=persist_profile_path,
    )

    # Reload dataset with profiles to build a structured predictions file
    df = dataset_module.load_dataset(input_path)
    labels = prediction_result["cluster_labels"]
    df_with_preds = df.copy()
    df_with_preds["cluster_label"] = labels

    records: Dict[str, Any] = {
        "version": prediction_result["version"],
        "num_rows": prediction_result["num_rows"],
        "predictions": [],
    }

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
        records["predictions"].append(record)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, default=str)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ml.pipeline2.cli", description="Pipeline2 clustering CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    train_parser = subparsers.add_parser("train", help="Train clustering model")
    train_parser.add_argument("--input", type=str, help="Path to input CSV")
    train_parser.add_argument(
        "--version",
        type=str,
        required=True,
        help="Model version identifier (e.g., pipeline2-YYYY-MM-DD-001)",
    )

    predict_parser = subparsers.add_parser("predict", help="Run clustering prediction")
    predict_parser.add_argument("--input", type=str, help="Path to input CSV")
    predict_parser.add_argument(
        "--version",
        type=str,
        default="latest",
        help="Model version identifier or 'latest'",
    )
    predict_parser.add_argument(
        "--out",
        type=str,
        help="Path to output predictions.json",
    )
    predict_parser.add_argument(
        "--persist-profile",
        dest="persist_profile",
        type=str,
        help="Optional path to persist CSV with Teacher_profile",
    )

    return parser


def main(argv: Optional[list[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "train":
        handle_train(args)
    elif args.command == "predict":
        handle_predict(args)
    else:
        parser.error(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()

