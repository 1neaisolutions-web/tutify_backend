import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Optional


BASE_DIR = Path(__file__).resolve().parents[2]
LOGS_DIR = BASE_DIR / "logs"
LOG_FILE = LOGS_DIR / "pipeline2.log"


@dataclass
class RunLogContext:
    run_id: str
    model_version: Optional[str]
    dataset_hash: Optional[str]
    start_time: float

    @property
    def runtime(self) -> float:
        return time.time() - self.start_time


def _ensure_log_dir() -> None:
    os.makedirs(LOGS_DIR, exist_ok=True)


def get_logger() -> logging.Logger:
    """
    Return a shared logger for the pipeline2 workflows.

    The logger writes structured JSON lines to logs/pipeline2.log.
    """
    _ensure_log_dir()
    logger = logging.getLogger("pipeline2")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    formatter = logging.Formatter("%(message)s")
    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.propagate = False
    return logger


def start_run(model_version: Optional[str], dataset_hash: Optional[str]) -> RunLogContext:
    """
    Create a new run context with a unique run_id and start time.
    """
    return RunLogContext(
        run_id=str(uuid.uuid4()),
        model_version=model_version,
        dataset_hash=dataset_hash,
        start_time=time.time(),
    )


def log_event(
    context: RunLogContext,
    status: str,
    message: str,
    error: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Write a single structured log event.

    Required fields:
      - run_id
      - model_version
      - dataset_hash
      - runtime
      - status
      - error (if any)
    """
    logger = get_logger()
    payload: Dict[str, Any] = {
        "run_id": context.run_id,
        "model_version": context.model_version,
        "dataset_hash": context.dataset_hash,
        "runtime": context.runtime,
        "status": status,
        "error": error,
        "message": message,
    }
    if extra:
        payload.update(extra)

    logger.info(json.dumps(payload, default=str))

