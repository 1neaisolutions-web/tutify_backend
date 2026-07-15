"""Shared scope validation for teacher tools (assignment, worksheet, exam).

Quiz keeps its inline helpers unchanged; other domains import from here.
"""

from __future__ import annotations

from typing import Any, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.domains.content_ingestion.scope_query import validate_scope_topic_ids_for_tenant


class SourcedScopeValidationError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def parse_scope_topic_ids(raw: Optional[List[Any]]) -> List[UUID]:
    out: List[UUID] = []
    for item in raw or []:
        try:
            out.append(UUID(str(item)))
        except (ValueError, TypeError):
            continue
    return out


def validate_sourced_scope(
    db: Session,
    *,
    tenant_id: UUID,
    generate_without_sources: bool,
    source_pack_ids: List[Any],
    scope_topic_ids: Optional[List[Any]],
) -> None:
    if generate_without_sources:
        return
    strict = bool(getattr(settings, "QUIZ_STRICT_SCOPE_ONLY", True))
    if not strict:
        return
    ids = parse_scope_topic_ids(scope_topic_ids)
    if not ids:
        raise SourcedScopeValidationError("Select at least one chapter or topic.")
    try:
        pack_ids = [UUID(str(x)) for x in (source_pack_ids or []) if x]
    except (ValueError, TypeError) as e:
        raise SourcedScopeValidationError("Invalid pack IDs on resource.") from e
    if not pack_ids:
        raise SourcedScopeValidationError("Select at least one source book.")
    valid = validate_scope_topic_ids_for_tenant(
        db, tenant_id=tenant_id, pack_ids=pack_ids, topic_ids=ids
    )
    if len(valid) != len(ids):
        raise SourcedScopeValidationError(
            "One or more selected topics are invalid for the chosen books."
        )
