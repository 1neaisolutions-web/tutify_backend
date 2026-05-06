from __future__ import annotations

from dataclasses import dataclass


@dataclass
class QuizError(Exception):
    code: str
    message: str
    http_status: int = 400


def not_found(message: str = "Quiz not found") -> QuizError:
    return QuizError(code="QUIZ_NOT_FOUND", message=message, http_status=404)


def forbidden(message: str = "Forbidden") -> QuizError:
    return QuizError(code="FORBIDDEN", message=message, http_status=403)


def validation_failed(message: str) -> QuizError:
    return QuizError(code="VALIDATION_FAILED", message=message, http_status=422)


def generation_timeout(message: str = "Generation timed out") -> QuizError:
    return QuizError(code="GENERATION_TIMEOUT", message=message, http_status=504)


def generation_failed(message: str = "Generation failed") -> QuizError:
    return QuizError(code="GENERATION_FAILED", message=message, http_status=502)

