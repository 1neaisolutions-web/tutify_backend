from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional
import sys

# Ensure project root is on sys.path so that the `ml` package is importable
BASE_DIR = Path(__file__).resolve().parents[2]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from ml.pipeline2.cli import main as pipeline2_main


DEFAULT_INPUT = BASE_DIR / "Dummy_Teachers_Data_version2.csv"
DEFAULT_PREDICTIONS = BASE_DIR / "outputs" / "pipeline2" / "predictions.json"


def _default_version_prefix() -> str:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    return f"pipeline2-{today}-001"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_pipeline2_local",
        description="Convenience wrapper for running pipeline2 locally.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    train_parser = subparsers.add_parser("train", help="Train clustering model locally")
    train_parser.add_argument(
        "--input",
        type=str,
        default=str(DEFAULT_INPUT),
        help="Path to input CSV (default: Dummy_Teachers_Data_version2.csv)",
    )
    train_parser.add_argument(
        "--version",
        type=str,
        default=_default_version_prefix(),
        help="Model version identifier (default: pipeline2-YYYY-MM-DD-001)",
    )

    predict_parser = subparsers.add_parser("predict", help="Predict clusters locally")
    predict_parser.add_argument(
        "--input",
        type=str,
        default=str(DEFAULT_INPUT),
        help="Path to input CSV (default: Dummy_Teachers_Data_version2.csv)",
    )
    predict_parser.add_argument(
        "--version",
        type=str,
        default="latest",
        help="Model version identifier or 'latest' (default: latest)",
    )
    predict_parser.add_argument(
        "--out",
        type=str,
        default=str(DEFAULT_PREDICTIONS),
        help="Path to output predictions.json (default: outputs/pipeline2/predictions.json)",
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
        pipeline2_main(
            [
                "train",
                "--input",
                args.input,
                "--version",
                args.version,
            ]
        )
    elif args.command == "predict":
        cli_args = [
            "predict",
            "--input",
            args.input,
            "--version",
            args.version,
            "--out",
            args.out,
        ]
        if args.persist_profile:
            cli_args.extend(["--persist-profile", args.persist_profile])
        pipeline2_main(cli_args)
    else:
        parser.error(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()

