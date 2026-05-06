"""Batch-ingest user activity events with idempotency dedup."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domains.personalization.models import UserActivityEvent

logger = get_logger(__name__)


class ActivityIngestionService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def ingest(
        self,
        user_id: uuid.UUID,
        events: list[dict[str, Any]],
    ) -> tuple[int, int]:
        """
        Ingest a batch of events.

        Returns (accepted_count, duplicate_skipped_count).
        Dedup is by (user_id, client_event_id).
        """
        accepted = 0
        skipped = 0

        for raw in events:
            client_event_id = raw.get("client_event_id")
            if not client_event_id:
                continue

            # Check duplicate
            exists = (
                self.db.query(UserActivityEvent)
                .filter(
                    UserActivityEvent.user_id == user_id,
                    UserActivityEvent.client_event_id == client_event_id,
                )
                .first()
            )
            if exists:
                skipped += 1
                continue

            event = UserActivityEvent(
                user_id=user_id,
                client_event_id=client_event_id,
                event_type=raw.get("event_type", "unknown"),
                section=raw.get("section"),
                content_id=raw.get("content_id"),
                content_type=raw.get("content_type"),
                assignment_id=raw.get("assignment_id"),
                slate_id=raw.get("slate_id"),
                session_id=raw.get("session_id"),
                dwell_ms=raw.get("dwell_ms"),
                event_metadata=raw.get("metadata", {}),
            )
            try:
                self.db.add(event)
                self.db.flush()
                accepted += 1
            except IntegrityError:
                self.db.rollback()
                skipped += 1

        return accepted, skipped

    def count_events(
        self,
        user_id: uuid.UUID,
        section: str,
        event_types: list[str],
    ) -> int:
        return (
            self.db.query(UserActivityEvent)
            .filter(
                UserActivityEvent.user_id == user_id,
                UserActivityEvent.section == section,
                UserActivityEvent.event_type.in_(event_types),
            )
            .count()
        )
