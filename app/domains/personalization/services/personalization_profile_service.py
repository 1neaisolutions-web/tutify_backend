"""CRUD service for UserPersonalizationProfile."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domains.personalization.models import UserPersonalizationProfile

logger = get_logger(__name__)


class PersonalizationProfileService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, user_id: uuid.UUID) -> Optional[UserPersonalizationProfile]:
        return (
            self.db.query(UserPersonalizationProfile)
            .filter(UserPersonalizationProfile.user_id == user_id)
            .first()
        )

    def get_or_create(self, user_id: uuid.UUID, profile_completeness: float = 0.0) -> UserPersonalizationProfile:
        profile = self.get(user_id)
        if profile:
            return profile
        profile = UserPersonalizationProfile(
            user_id=user_id,
            profile_completeness=profile_completeness,
            status="active",
            personalization_version=1,
        )
        self.db.add(profile)
        self.db.flush()
        logger.info("personalization.profile_created", extra={"user_id": str(user_id)})
        return profile

    def update_status(self, profile: UserPersonalizationProfile, status: str) -> UserPersonalizationProfile:
        profile.status = status
        profile.updated_at = datetime.now(timezone.utc)
        self.db.flush()
        return profile

    def mark_started(self, profile: UserPersonalizationProfile) -> UserPersonalizationProfile:
        profile.personalization_started_at = datetime.now(timezone.utc)
        profile.updated_at = datetime.now(timezone.utc)
        self.db.flush()
        return profile

    def mark_recomputed(self, profile: UserPersonalizationProfile) -> UserPersonalizationProfile:
        profile.last_recomputed_at = datetime.now(timezone.utc)
        profile.updated_at = datetime.now(timezone.utc)
        self.db.flush()
        return profile

    def increment_version(self, profile: UserPersonalizationProfile) -> UserPersonalizationProfile:
        profile.personalization_version += 1
        profile.last_reset_at = datetime.now(timezone.utc)
        profile.updated_at = datetime.now(timezone.utc)
        self.db.flush()
        logger.info(
            "personalization.version_incremented",
            extra={"user_id": str(profile.user_id), "new_version": profile.personalization_version},
        )
        return profile

    def update_completeness(self, profile: UserPersonalizationProfile, completeness: float) -> UserPersonalizationProfile:
        profile.profile_completeness = completeness
        profile.updated_at = datetime.now(timezone.utc)
        self.db.flush()
        return profile
