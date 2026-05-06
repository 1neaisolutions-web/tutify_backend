"""Service to create and manage personalization snapshots."""
from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domains.personalization.models import PersonalizationSnapshot, UserPersonalizationProfile

logger = get_logger(__name__)


class PersonalizationSnapshotService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        profile: UserPersonalizationProfile,
        trigger: str,
        ranking_signals: Optional[dict[str, Any]] = None,
        feature_snapshot_id: Optional[uuid.UUID] = None,
        ml_output_id: Optional[uuid.UUID] = None,
    ) -> PersonalizationSnapshot:
        # Mark previous snapshots as not current
        self.db.query(PersonalizationSnapshot).filter(
            PersonalizationSnapshot.personalization_profile_id == profile.id,
            PersonalizationSnapshot.is_current == True,  # noqa: E712
        ).update({"is_current": False})

        snapshot = PersonalizationSnapshot(
            personalization_profile_id=profile.id,
            user_id=profile.user_id,
            personalization_version=profile.personalization_version,
            trigger=trigger,
            feature_snapshot_id=feature_snapshot_id,
            ml_output_id=ml_output_id,
            ranking_signals=ranking_signals or {},
            is_current=True,
        )
        self.db.add(snapshot)
        self.db.flush()
        logger.info(
            "personalization.snapshot_created",
            extra={"user_id": str(profile.user_id), "trigger": trigger, "snapshot_id": str(snapshot.id)},
        )
        return snapshot

    def get_current(self, profile_id: uuid.UUID) -> Optional[PersonalizationSnapshot]:
        return (
            self.db.query(PersonalizationSnapshot)
            .filter(
                PersonalizationSnapshot.personalization_profile_id == profile_id,
                PersonalizationSnapshot.is_current == True,  # noqa: E712
            )
            .first()
        )
