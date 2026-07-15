from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class QuizError(Exception):
    code: str
    message: str
    http_status: int = 400
    extra: Optional[Dict[str, Any]] = field(default=None)


def not_found(message: str = "Quiz not found") -> QuizError:
    return QuizError(code="QUIZ_NOT_FOUND", message=message, http_status=404)


def forbidden(message: str = "Forbidden") -> QuizError:
    return QuizError(code="FORBIDDEN", message=message, http_status=403)


def validation_failed(message: str, *, extra: Optional[Dict[str, Any]] = None) -> QuizError:
    return QuizError(code="VALIDATION_FAILED", message=message, http_status=422, extra=extra)


def retrieval_scope_failed(
    message: str,
    *,
    topic_ids: list,
    fallback_available: bool = False,
) -> QuizError:
    return QuizError(
        code="RETRIEVAL_SCOPE_ERROR",
        message=message,
        http_status=422,
        extra={
            "topic_ids": [str(x) for x in topic_ids],
            "fallback_available": fallback_available,
        },
    )


def generation_timeout(message: str = "Generation timed out") -> QuizError:
    return QuizError(code="GENERATION_TIMEOUT", message=message, http_status=504)


def generation_failed(message: str = "Generation failed") -> QuizError:
    return QuizError(code="GENERATION_FAILED", message=message, http_status=502)

