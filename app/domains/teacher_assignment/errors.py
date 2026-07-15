from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class AssignmentError(Exception):
    code: str
    message: str
    http_status: int = 400
    extra: Optional[dict] = None


def not_found(message: str = "Assignment not found") -> AssignmentError:
    return AssignmentError(code="ASSIGNMENT_NOT_FOUND", message=message, http_status=404)


def forbidden(message: str = "Forbidden") -> AssignmentError:
    return AssignmentError(code="FORBIDDEN", message=message, http_status=403)


def validation_failed(message: str) -> AssignmentError:
    return AssignmentError(code="VALIDATION_FAILED", message=message, http_status=422)


def retrieval_scope_failed(
    message: str,
    *,
    topic_ids: list,
    fallback_available: bool = False,
) -> AssignmentError:
    return AssignmentError(
        code="RETRIEVAL_SCOPE_ERROR",
        message=message,
        http_status=422,
        extra={
            "topic_ids": [str(x) for x in topic_ids],
            "fallback_available": fallback_available,
        },
    )


def generation_timeout(message: str = "Generation timed out") -> AssignmentError:
    return AssignmentError(code="GENERATION_TIMEOUT", message=message, http_status=504)


def generation_failed(message: str = "Generation failed") -> AssignmentError:
    return AssignmentError(code="GENERATION_FAILED", message=message, http_status=502)
