"""Shared topic scoping helpers and retrieval errors."""
from __future__ import annotations

from typing import List
from uuid import UUID

from sqlalchemy.orm import Session

from app.domains.content_ingestion.document_topics_service import resolve_topic_ids_with_descendants


class RetrievalScopeError(Exception):
    """Raised when scoped topic IDs match zero indexed chunks."""

    def __init__(
        self,
        message: str,
        topic_ids: List[UUID],
        *,
        fallback_available: bool = False,
    ):
        super().__init__(message)
        self.message = message
        self.topic_ids = topic_ids
        self.fallback_available = fallback_available


def expand_scope_topic_ids(
    db: Session,
    topic_ids: List[UUID],
    *,
    include_sub_topics: bool = True,
) -> List[UUID]:
    return resolve_topic_ids_with_descendants(
        db, topic_ids, include_sub_topics=include_sub_topics
    )
