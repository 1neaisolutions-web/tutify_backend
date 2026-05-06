from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AssignmentError(Exception):
    code: str
    message: str
    http_status: int = 400


def not_found(message: str = "Assignment not found") -> AssignmentError:
    return AssignmentError(code="ASSIGNMENT_NOT_FOUND", message=message, http_status=404)


def forbidden(message: str = "Forbidden") -> AssignmentError:
    return AssignmentError(code="FORBIDDEN", message=message, http_status=403)


def validation_failed(message: str) -> AssignmentError:
    return AssignmentError(code="VALIDATION_FAILED", message=message, http_status=422)


def generation_timeout(message: str = "Generation timed out") -> AssignmentError:
    return AssignmentError(code="GENERATION_TIMEOUT", message=message, http_status=504)


def generation_failed(message: str = "Generation failed") -> AssignmentError:
    return AssignmentError(code="GENERATION_FAILED", message=message, http_status=502)
