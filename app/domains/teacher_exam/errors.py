from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ExamError(Exception):
    code: str
    message: str
    http_status: int = 400


def not_found(message: str = "Exam not found") -> ExamError:
    return ExamError(code="NOT_FOUND", message=message, http_status=404)


def generation_failed(msg: str = "") -> ExamError:
    return ExamError(code="GENERATION_FAILED", message=msg or "LLM generation failed", http_status=502)


def validation_failed(msg: str) -> ExamError:
    return ExamError(code="VALIDATION_FAILED", message=msg, http_status=422)


def generation_timeout(message: str = "Generation timed out") -> ExamError:
    return ExamError(code="GENERATION_TIMEOUT", message=message, http_status=504)
