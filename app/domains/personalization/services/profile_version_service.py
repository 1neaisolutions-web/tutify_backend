"""Append-only profile version history service."""
from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domains.personalization.models import ProfileVersion, UserPersonalizationProfile

logger = get_logger(__name__)


class ProfileVersionService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def record_version(
        self,
        profile: UserPersonalizationProfile,
        profile_snapshot: dict[str, Any],
        completeness: float,
        change_type: Optional[str] = None,
        changed_fields: Optional[list[str]] = None,
    ) -> ProfileVersion:
        version = ProfileVersion(
            personalization_profile_id=profile.id,
            user_id=profile.user_id,
            version_number=profile.personalization_version,
            profile_snapshot=profile_snapshot,
            completeness=completeness,
            change_type=change_type,
            changed_fields=changed_fields or [],
        )
        self.db.add(version)
        self.db.flush()
        logger.info(
            "personalization.profile_version_recorded",
            extra={"user_id": str(profile.user_id), "version": profile.personalization_version, "change_type": change_type},
        )
        return version

    def get_history(self, user_id: uuid.UUID, limit: int = 20) -> list[ProfileVersion]:
        return (
            self.db.query(ProfileVersion)
            .filter(ProfileVersion.user_id == user_id)
            .order_by(ProfileVersion.version_number.desc())
            .limit(limit)
            .all()
        )

    def get_latest(self, user_id: uuid.UUID) -> Optional[ProfileVersion]:
        return (
            self.db.query(ProfileVersion)
            .filter(ProfileVersion.user_id == user_id)
            .order_by(ProfileVersion.version_number.desc())
            .first()
        )
