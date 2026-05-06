"""Service to build and manage recommendation slates."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domains.personalization.models import (
    PersonalizedContentAssignment,
    RecommendationSlate,
    RecommendationSlateItem,
    UnlockState,
    UserPersonalizationProfile,
)

logger = get_logger(__name__)


class SlateService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def build_slate(
        self,
        profile: UserPersonalizationProfile,
        snapshot_id: Optional[uuid.UUID] = None,
    ) -> RecommendationSlate:
        """Build a current slate from active assignments. Per-section failures are isolated."""
        # Retire old current slate
        self.db.query(RecommendationSlate).filter(
            RecommendationSlate.user_id == profile.user_id,
            RecommendationSlate.is_current == True,  # noqa: E712
        ).update({"is_current": False})

        slate = RecommendationSlate(
            personalization_profile_id=profile.id,
            snapshot_id=snapshot_id,
            user_id=profile.user_id,
            personalization_version=profile.personalization_version,
            is_current=True,
        )
        self.db.add(slate)
        self.db.flush()

        # Fetch all active assignments
        assignments = (
            self.db.query(PersonalizedContentAssignment)
            .filter(
                PersonalizedContentAssignment.user_id == profile.user_id,
                PersonalizedContentAssignment.personalization_version == profile.personalization_version,
                PersonalizedContentAssignment.is_active == True,  # noqa: E712
                PersonalizedContentAssignment.bucket.in_(["visible", "locked_preview"]),
            )
            .order_by(
                PersonalizedContentAssignment.section,
                PersonalizedContentAssignment.position,
            )
            .all()
        )

        # Fetch unlock states keyed by assignment_id
        unlock_map: dict[uuid.UUID, bool] = {}
        if assignments:
            assignment_ids = [a.id for a in assignments]
            states = (
                self.db.query(UnlockState)
                .filter(UnlockState.assignment_id.in_(assignment_ids))
                .all()
            )
            unlock_map = {s.assignment_id: s.locked for s in states}

        items_created = 0
        for assignment in assignments:
            try:
                locked = unlock_map.get(assignment.id, assignment.bucket != "visible")
                item = RecommendationSlateItem(
                    slate_id=slate.id,
                    assignment_id=assignment.id,
                    user_id=profile.user_id,
                    section=assignment.section,
                    bucket=assignment.bucket,
                    position=assignment.position,
                    locked=locked,
                    content_id=assignment.content_id,
                    content_type=assignment.content_type,
                    route=assignment.route,
                    content_slug=assignment.content_slug,
                    score=assignment.score,
                    reason_codes=assignment.reason_codes,
                    display_meta={},
                )
                self.db.add(item)
                items_created += 1
            except Exception as exc:
                logger.error(
                    "personalization.slate_item_build_failed",
                    extra={"assignment_id": str(assignment.id), "error": str(exc)},
                )

        self.db.flush()
        logger.info(
            "personalization.slate_built",
            extra={"user_id": str(profile.user_id), "slate_id": str(slate.id), "items": items_created},
        )
        return slate

    def get_current(self, user_id: uuid.UUID) -> Optional[RecommendationSlate]:
        return (
            self.db.query(RecommendationSlate)
            .filter(
                RecommendationSlate.user_id == user_id,
                RecommendationSlate.is_current == True,  # noqa: E712
            )
            .first()
        )

    def get_items(self, slate_id: uuid.UUID, section: Optional[str] = None) -> list[RecommendationSlateItem]:
        q = self.db.query(RecommendationSlateItem).filter(
            RecommendationSlateItem.slate_id == slate_id
        )
        if section:
            q = q.filter(RecommendationSlateItem.section == section)
        return q.order_by(RecommendationSlateItem.section, RecommendationSlateItem.position).all()
