"""Service for creating and managing personalized content assignments."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domains.personalization.models import (
    PersonalizedContentAssignment,
    SectionInventoryConfig,
    UserPersonalizationProfile,
)

logger = get_logger(__name__)

DEFAULT_INVENTORY: dict[str, dict[str, int]] = {
    "micro_courses": {"visible": 5, "locked_preview": 5, "reserve": 10},
    "growth_recommendations": {"visible": 3, "locked_preview": 3, "reserve": 6},
    "tutorials": {"visible": 3, "locked_preview": 3, "reserve": 6},
    "research_insights": {"visible": 5, "locked_preview": 5, "reserve": 10},
    "specialist_tracks": {"visible": 3, "locked_preview": 3, "reserve": 6},
}


class AssignmentService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _get_inventory(self, section: str) -> dict[str, int]:
        config = self.db.query(SectionInventoryConfig).filter(SectionInventoryConfig.section == section).first()
        defaults = DEFAULT_INVENTORY.get(section, {"visible": 3, "locked_preview": 3, "reserve": 3})
        if config:
            # Enforce production minimum targets even if DB config is stale/lower.
            return {
                "visible": max(config.visible_count, defaults["visible"]),
                "locked_preview": max(config.locked_preview_count, defaults["locked_preview"]),
                "reserve": max(config.reserve_buffer_count, defaults["reserve"]),
            }
        return defaults

    def _already_completed_content_ids(self, user_id: uuid.UUID) -> set[str]:
        """Return content_ids that were completed in any prior version. Excluded from new assignments."""
        rows = (
            self.db.query(PersonalizedContentAssignment.content_id)
            .filter(
                PersonalizedContentAssignment.user_id == user_id,
                PersonalizedContentAssignment.status == "completed",
            )
            .all()
        )
        return {r.content_id for r in rows}

    def create_from_ranked(
        self,
        profile: UserPersonalizationProfile,
        snapshot_id: uuid.UUID,
        section: str,
        ranked_items: list[dict[str, Any]],
    ) -> list[PersonalizedContentAssignment]:
        """
        Create assignments from a ranked list of content items.

        ranked_items: list of dicts with keys:
            content_id, content_type, score, reason_codes, ranking_signals, route, content_slug
        """
        inventory = self._get_inventory(section)
        excluded = self._already_completed_content_ids(profile.user_id)

        # Dedup: same content_id not twice in same version
        existing_content_ids: set[str] = set(
            r.content_id
            for r in self.db.query(PersonalizedContentAssignment.content_id)
            .filter(
                PersonalizedContentAssignment.user_id == profile.user_id,
                PersonalizedContentAssignment.personalization_version == profile.personalization_version,
            )
            .all()
        )

        assignments = []
        position = 0
        seen_rank_titles: set[str] = set()

        visible_limit = inventory["visible"]
        preview_limit = inventory["locked_preview"]
        reserve_limit = inventory["reserve"]
        total_limit = visible_limit + preview_limit + reserve_limit

        # Early-stage split guard:
        # If the upstream ranked candidates are still small (e.g., only a few content items
        # are available while generation is catching up), the classic bucket boundary
        # (first `visible_limit` items -> visible) can result in zero `locked_preview`
        # assignments for extended periods.
        #
        # For production correctness we still keep the overall inventory caps; this only
        # adjusts the *visible/locked_preview boundary* so that when at least 2 candidates
        # exist, at least 1 can land in `locked_preview`.
        ranked_len = len(ranked_items)
        visible_limit_for_bucket = visible_limit
        if ranked_len >= 2 and ranked_len < visible_limit + 1:
            visible_limit_for_bucket = max(1, ranked_len - 1)

        for item in ranked_items:
            if len(assignments) >= total_limit:
                break

            content_id = item.get("content_id", "")
            norm_title = (item.get("title") or "").strip().lower()
            if not content_id:
                continue
            if content_id in excluded:
                continue
            if content_id in existing_content_ids:
                continue
            # Semantic dedup guard: avoid different content IDs with the same title
            # landing in the same section/version slate.
            if norm_title and norm_title in seen_rank_titles:
                continue

            # Assign bucket by position (with early-stage split guard)
            if position < visible_limit_for_bucket:
                bucket = "visible"
            elif position < visible_limit_for_bucket + preview_limit:
                bucket = "locked_preview"
            else:
                bucket = "reserve"

            # Policy: starter_seed may be used as transparent fallback inventory,
            # but should not masquerade as primary visible personalized content.
            if item.get("source_type") == "starter_seed" and bucket == "visible":
                bucket = "locked_preview"

            assignment = PersonalizedContentAssignment(
                personalization_profile_id=profile.id,
                snapshot_id=snapshot_id,
                user_id=profile.user_id,
                personalization_version=profile.personalization_version,
                content_id=content_id,
                content_type=item.get("content_type", ""),
                section=section,
                bucket=bucket,
                position=position,
                priority_rank=position,
                diversity_key=norm_title or content_id,
                score=item.get("score", 0.0),
                reason_codes=item.get("reason_codes", []),
                ranking_signals=item.get("ranking_signals", {}),
                route=item.get("route"),
                content_slug=item.get("content_slug"),
                status="assigned",
                is_active=True,
            )
            self.db.add(assignment)
            assignments.append(assignment)
            existing_content_ids.add(content_id)
            if norm_title:
                seen_rank_titles.add(norm_title)
            position += 1

        self.db.flush()
        logger.info(
            "personalization.assignments_created",
            extra={"user_id": str(profile.user_id), "section": section, "count": len(assignments)},
        )
        return assignments

    def inventory_counts(self, user_id: uuid.UUID, section: str, version: int) -> dict[str, int]:
        rows = (
            self.db.query(PersonalizedContentAssignment.bucket, PersonalizedContentAssignment.id)
            .filter(
                PersonalizedContentAssignment.user_id == user_id,
                PersonalizedContentAssignment.section == section,
                PersonalizedContentAssignment.personalization_version == version,
                PersonalizedContentAssignment.is_active == True,  # noqa: E712
            )
            .all()
        )
        counts = {"visible": 0, "locked_preview": 0, "reserve": 0}
        for bucket, _ in rows:
            if bucket in counts:
                counts[bucket] += 1
        return counts

    def needs_refill(self, user_id: uuid.UUID, section: str, version: int) -> bool:
        inv = self._get_inventory(section)
        counts = self.inventory_counts(user_id, section, version)
        required_total = inv["visible"] + inv["locked_preview"] + inv["reserve"]
        current_total = counts["visible"] + counts["locked_preview"] + counts["reserve"]
        reserve_threshold = max(1, inv["reserve"] // 2)
        return current_total < required_total or counts["reserve"] < reserve_threshold

    def rebalance_after_completion(
        self,
        user_id: uuid.UUID,
        section: str,
        version: int,
    ) -> dict[str, int]:
        """
        Progression contract:
        1) promote next locked_preview -> visible
        2) promote next reserve -> locked_preview
        """
        inv = self._get_inventory(section)
        assignments = (
            self.db.query(PersonalizedContentAssignment)
            .filter(
                PersonalizedContentAssignment.user_id == user_id,
                PersonalizedContentAssignment.section == section,
                PersonalizedContentAssignment.personalization_version == version,
                PersonalizedContentAssignment.is_active == True,  # noqa: E712
            )
            .order_by(PersonalizedContentAssignment.position.asc())
            .all()
        )

        visible = [a for a in assignments if a.bucket == "visible"]
        locked = [a for a in assignments if a.bucket == "locked_preview"]
        reserve = [a for a in assignments if a.bucket == "reserve"]

        while len(visible) < inv["visible"] and locked:
            nxt = locked.pop(0)
            nxt.bucket = "visible"
            nxt.updated_at = datetime.now(timezone.utc)
            visible.append(nxt)

        while len(locked) < inv["locked_preview"] and reserve:
            nxt = reserve.pop(0)
            nxt.bucket = "locked_preview"
            nxt.updated_at = datetime.now(timezone.utc)
            locked.append(nxt)

        self.db.flush()
        return self.inventory_counts(user_id, section, version)

    def get_active(self, user_id: uuid.UUID, section: str, version: int) -> list[PersonalizedContentAssignment]:
        return (
            self.db.query(PersonalizedContentAssignment)
            .filter(
                PersonalizedContentAssignment.user_id == user_id,
                PersonalizedContentAssignment.section == section,
                PersonalizedContentAssignment.personalization_version == version,
                PersonalizedContentAssignment.is_active == True,  # noqa: E712
            )
            .order_by(PersonalizedContentAssignment.position)
            .all()
        )

    def supersede_all(self, user_id: uuid.UUID, old_version: int, new_version: int) -> int:
        now = datetime.now(timezone.utc)
        count = (
            self.db.query(PersonalizedContentAssignment)
            .filter(
                PersonalizedContentAssignment.user_id == user_id,
                PersonalizedContentAssignment.personalization_version == old_version,
                PersonalizedContentAssignment.is_active == True,  # noqa: E712
            )
            .update(
                {
                    "is_active": False,
                    "status": "superseded",
                    "superseded_at": now,
                    "superseded_by_version": new_version,
                    "updated_at": now,
                }
            )
        )
        self.db.flush()
        return count

    def mark_started(self, assignment: PersonalizedContentAssignment) -> PersonalizedContentAssignment:
        assignment.status = "started"
        assignment.started_at = datetime.now(timezone.utc)
        assignment.updated_at = datetime.now(timezone.utc)
        self.db.flush()
        return assignment

    def mark_completed(self, assignment: PersonalizedContentAssignment) -> PersonalizedContentAssignment:
        assignment.status = "completed"
        assignment.completed_at = datetime.now(timezone.utc)
        assignment.updated_at = datetime.now(timezone.utc)
        self.db.flush()
        return assignment

    def get_by_id(self, assignment_id: uuid.UUID, user_id: uuid.UUID) -> Optional[PersonalizedContentAssignment]:
        return (
            self.db.query(PersonalizedContentAssignment)
            .filter(
                PersonalizedContentAssignment.id == assignment_id,
                PersonalizedContentAssignment.user_id == user_id,
                PersonalizedContentAssignment.is_active == True,  # noqa: E712
            )
            .first()
        )

    def find_by_content_id(self, user_id: uuid.UUID, content_id: str, version: int) -> Optional[PersonalizedContentAssignment]:
        return (
            self.db.query(PersonalizedContentAssignment)
            .filter(
                PersonalizedContentAssignment.user_id == user_id,
                PersonalizedContentAssignment.content_id == content_id,
                PersonalizedContentAssignment.personalization_version == version,
                PersonalizedContentAssignment.is_active == True,  # noqa: E712
            )
            .first()
        )
