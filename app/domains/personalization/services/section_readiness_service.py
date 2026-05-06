"""Strict state-machine service for section_readiness."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domains.personalization.enums import SectionKey, SectionReadinessStatus
from app.domains.personalization.models import (
    SectionInventoryConfig,
    SectionReadiness,
    UserPersonalizationProfile,
)

logger = get_logger(__name__)

# Valid state transitions
VALID_TRANSITIONS: dict[str, list[str]] = {
    SectionReadinessStatus.NOT_STARTED: [SectionReadinessStatus.PREPARING],
    SectionReadinessStatus.PREPARING: [
        SectionReadinessStatus.PARTIAL_READY,
        SectionReadinessStatus.READY,
        SectionReadinessStatus.FAILED,
    ],
    SectionReadinessStatus.PARTIAL_READY: [SectionReadinessStatus.READY, SectionReadinessStatus.FAILED],
    SectionReadinessStatus.READY: [SectionReadinessStatus.STALE, SectionReadinessStatus.PREPARING],
    SectionReadinessStatus.STALE: [SectionReadinessStatus.READY, SectionReadinessStatus.FAILED],
    SectionReadinessStatus.FAILED: [SectionReadinessStatus.PREPARING],
}

DEFAULT_VISIBLE_COUNTS: dict[str, int] = {
    SectionKey.MICRO_COURSES: 5,
    SectionKey.GROWTH_RECOMMENDATIONS: 3,
    SectionKey.TUTORIALS: 3,
    SectionKey.RESEARCH_INSIGHTS: 5,
    SectionKey.SPECIALIST_TRACKS: 3,
}
DEFAULT_LOCKED_PREVIEW_COUNTS: dict[str, int] = {
    SectionKey.MICRO_COURSES: 5,
    SectionKey.GROWTH_RECOMMENDATIONS: 3,
    SectionKey.TUTORIALS: 3,
    SectionKey.RESEARCH_INSIGHTS: 5,
    SectionKey.SPECIALIST_TRACKS: 3,
}


class SectionReadinessService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _get_visible_target(self, section: str) -> int:
        config = self.db.query(SectionInventoryConfig).filter(SectionInventoryConfig.section == section).first()
        if config:
            return max(config.visible_count, DEFAULT_VISIBLE_COUNTS.get(section, 3))
        return DEFAULT_VISIBLE_COUNTS.get(section, 3)

    def _get_locked_preview_target(self, section: str) -> int:
        config = self.db.query(SectionInventoryConfig).filter(SectionInventoryConfig.section == section).first()
        if config:
            return max(config.locked_preview_count, DEFAULT_LOCKED_PREVIEW_COUNTS.get(section, 3))
        return DEFAULT_LOCKED_PREVIEW_COUNTS.get(section, 3)

    def initialize_all(
        self,
        profile: UserPersonalizationProfile,
        snapshot_id: Optional[uuid.UUID] = None,
        job_id: Optional[uuid.UUID] = None,
    ) -> list[SectionReadiness]:
        sections = list(SectionKey)
        records = []
        for section in sections:
            existing = self.get(profile.user_id, section.value, profile.personalization_version)
            if existing:
                records.append(existing)
                continue
            sr = SectionReadiness(
                user_id=profile.user_id,
                personalization_profile_id=profile.id,
                section=section.value,
                status=SectionReadinessStatus.NOT_STARTED,
                personalization_version=profile.personalization_version,
                snapshot_id=snapshot_id,
                job_id=job_id,
                visible_count_target=self._get_visible_target(section.value),
            )
            self.db.add(sr)
            records.append(sr)
        self.db.flush()
        return records

    def get(self, user_id: uuid.UUID, section: str, version: int) -> Optional[SectionReadiness]:
        return (
            self.db.query(SectionReadiness)
            .filter(
                SectionReadiness.user_id == user_id,
                SectionReadiness.section == section,
                SectionReadiness.personalization_version == version,
            )
            .first()
        )

    def get_all(self, user_id: uuid.UUID) -> list[SectionReadiness]:
        return (
            self.db.query(SectionReadiness)
            .filter(SectionReadiness.user_id == user_id)
            .order_by(SectionReadiness.personalization_version.desc(), SectionReadiness.section)
            .all()
        )

    def get_current_all(self, user_id: uuid.UUID, version: int) -> list[SectionReadiness]:
        return (
            self.db.query(SectionReadiness)
            .filter(
                SectionReadiness.user_id == user_id,
                SectionReadiness.personalization_version == version,
            )
            .all()
        )

    def transition(
        self,
        sr: SectionReadiness,
        new_status: str,
        visible_count_actual: Optional[int] = None,
        slate_id: Optional[uuid.UUID] = None,
        job_id: Optional[uuid.UUID] = None,
    ) -> SectionReadiness:
        current = sr.status
        allowed = VALID_TRANSITIONS.get(current, [])
        if new_status not in allowed:
            logger.warning(
                "personalization.invalid_readiness_transition",
                extra={"user_id": str(sr.user_id), "section": sr.section, "from": current, "to": new_status},
            )
            return sr

        old_status = sr.status
        sr.status = new_status
        now = datetime.now(timezone.utc)
        sr.updated_at = now

        if visible_count_actual is not None:
            sr.visible_count_actual = visible_count_actual
        if slate_id:
            sr.slate_id = slate_id
        if job_id:
            sr.job_id = job_id

        if new_status == SectionReadinessStatus.READY:
            sr.last_ready_at = now
        elif new_status == SectionReadinessStatus.FAILED:
            sr.last_failed_at = now
            sr.failure_count += 1

        self.db.flush()
        logger.info(
            "personalization.section_readiness_changed",
            extra={
                "user_id": str(sr.user_id),
                "section": sr.section,
                "from_status": old_status,
                "to_status": new_status,
                "visible_count": sr.visible_count_actual,
            },
        )
        return sr

    def update_visible_count(self, sr: SectionReadiness, actual: int, slate_id: Optional[uuid.UUID] = None) -> SectionReadiness:
        sr.visible_count_actual = actual
        if slate_id:
            sr.slate_id = slate_id
        sr.updated_at = datetime.now(timezone.utc)

        # Auto-transition if thresholds met
        if actual >= sr.visible_count_target and sr.status in (
            SectionReadinessStatus.PREPARING,
            SectionReadinessStatus.PARTIAL_READY,
        ):
            return self.transition(sr, SectionReadinessStatus.READY, actual, slate_id)
        elif actual > 0 and sr.status == SectionReadinessStatus.PREPARING:
            return self.transition(sr, SectionReadinessStatus.PARTIAL_READY, actual, slate_id)

        self.db.flush()
        return sr

    def update_inventory_readiness(
        self,
        sr: SectionReadiness,
        visible_actual: int,
        locked_preview_actual: int,
        slate_id: Optional[uuid.UUID] = None,
    ) -> SectionReadiness:
        """
        Production readiness contract:
        - READY only when both visible target and locked-preview target are met.
        - PARTIAL_READY when any visible content exists but inventory is incomplete.
        - PREPARING when no visible content yet.
        """
        sr.visible_count_actual = visible_actual
        if slate_id:
            sr.slate_id = slate_id
        sr.updated_at = datetime.now(timezone.utc)

        visible_target = self._get_visible_target(sr.section)
        locked_target = self._get_locked_preview_target(sr.section)

        if visible_actual >= visible_target and locked_preview_actual >= locked_target:
            return self.transition(sr, SectionReadinessStatus.READY, visible_actual, slate_id)
        if visible_actual > 0:
            return self.transition(sr, SectionReadinessStatus.PARTIAL_READY, visible_actual, slate_id)
        if sr.status != SectionReadinessStatus.PREPARING:
            return self.transition(sr, SectionReadinessStatus.PREPARING, visible_actual, slate_id)

        self.db.flush()
        return sr
