from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WorksheetError(Exception):
    code: str
    message: str
    http_status: int = 400


def not_found(message: str = "Worksheet not found") -> WorksheetError:
    return WorksheetError(code="NOT_FOUND", message=message, http_status=404)


def forbidden(message: str = "Access denied") -> WorksheetError:
    return WorksheetError(code="FORBIDDEN", message=message, http_status=403)


def validation_failed(message: str) -> WorksheetError:
    return WorksheetError(code="VALIDATION_FAILED", message=message, http_status=422)


def min_session() -> WorksheetError:
    return WorksheetError(code="MIN_SESSION", message="At least one session required", http_status=400)


def min_block() -> WorksheetError:
    return WorksheetError(code="MIN_BLOCK", message="Keep at least one block", http_status=400)


def invalid_block_type(message: str = "Unknown block type") -> WorksheetError:
    return WorksheetError(code="INVALID_BLOCK_TYPE", message=message, http_status=400)


def generation_failed(message: str = "LLM generation failed") -> WorksheetError:
    return WorksheetError(code="GENERATION_FAILED", message=message, http_status=502)


def generation_timeout(message: str = "Generation timed out") -> WorksheetError:
    return WorksheetError(code="GENERATION_TIMEOUT", message=message, http_status=504)
