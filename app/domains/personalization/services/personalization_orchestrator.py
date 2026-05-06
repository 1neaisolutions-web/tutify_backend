"""
PersonalizationOrchestrator: coordinates the full personalization lifecycle.

Responsibilities:
- start_personalization: initial profile creation → snapshot → assignments → slate → readiness
- recompute: minor update — re-score existing assignments, rebuild slate, keep unlock states
- reset: major update — archive old version, increment version, re-run start flow
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domains.personalization.enums import SECTION_CONTENT_TYPES, SectionKey, SectionReadinessStatus
from app.domains.personalization.models import (
    PersonalizedContentAssignment,
    UserPersonalizationProfile,
)
from app.domains.personalization.services.assignment_service import AssignmentService
from app.domains.personalization.services.inventory_expansion_worker import InventoryExpansionWorker
from app.domains.personalization.services.personalization_job_service import PersonalizationJobService
from app.domains.personalization.services.personalization_profile_service import PersonalizationProfileService
from app.domains.personalization.services.personalization_snapshot_service import PersonalizationSnapshotService
from app.domains.personalization.services.profile_version_service import ProfileVersionService
from app.domains.personalization.services.section_readiness_service import SectionReadinessService
from app.domains.personalization.services.slate_service import SlateService
from app.domains.personalization.services.unlock_service import UnlockService

logger = get_logger(__name__)
_GENERIC_TITLE_MARKERS = {
    "introduction",
    "overview",
    "basics",
    "fundamentals",
    "general guide",
    "template",
}


def _title_quality_ok(title: str | None) -> bool:
    t = (title or "").strip().lower()
    if len(t) < 12:
        return False
    return not any(marker == t or t.startswith(f"{marker} ") for marker in _GENERIC_TITLE_MARKERS)


def _duration_quality_ok(content_type: str, duration_min: int | None) -> bool:
    if duration_min is None:
        return True
    ct = (content_type or "").strip().lower()
    if ct == "micro_course":
        return 5 <= duration_min <= 12
    if ct == "ai_guided_tutorial":
        return 8 <= duration_min <= 25
    if ct in ("learning_path", "path_module"):
        return 60 <= duration_min <= 180
    if ct in ("research", "resource"):
        return 5 <= duration_min <= 10
    return True

# Attempt to import content registry model - guard against missing table
try:
    from app.domains.content_registry.models import ContentRegistryItem
    _CONTENT_REGISTRY_AVAILABLE = True
except ImportError:
    _CONTENT_REGISTRY_AVAILABLE = False
    ContentRegistryItem = None  # type: ignore


# Minimum profile-match score for a content item to be included in ranked output.
# Items scoring below this are suppressed entirely — no generic fallback filling.
_PROFILE_MATCH_THRESHOLD = 0.15


def _score_item_for_profile(item: Any, profile_snapshot: dict[str, Any]) -> float:
    """
    Score a registry item against a profile snapshot. Returns 0.0–1.0.

    Additive rules:
    - alignment.subjects contains a profile subject     → +0.40
    - alignment.grade_band matches profile grade_band   → +0.25
    - category contains a profile subject keyword       → +0.20
    - tags contain a profile subject keyword            → +0.15
    - alignment.curriculum_framework matches profile    → +0.10

    If the snapshot has no subjects AND no grade_band (incomplete profile),
    returns 0.5 (neutral pass) so item is not wrongly excluded.
    """
    subjects = [s.strip().lower() for s in (profile_snapshot.get("subjects") or []) if s]
    grade_band = (profile_snapshot.get("grade_band") or "").strip().lower()
    curriculum = (profile_snapshot.get("curriculum_framework") or "").strip().lower()

    if not subjects and not grade_band:
        return 0.5  # No profile signal — neutral pass, cannot filter

    score = 0.0

    # ── alignment JSONB ──────────────────────────────────────────────────────
    alignment = item.alignment or {}
    if isinstance(alignment, dict):
        align_subjects = alignment.get("subjects") or alignment.get("subject") or []
        if isinstance(align_subjects, str):
            align_subjects = [align_subjects]
        align_subjects_lower = [str(s).strip().lower() for s in align_subjects]

        subject_matched = subjects and any(ps in align_subjects_lower for ps in subjects)
        # Hard exclusion: item declares explicit subjects and none match → score 0.0.
        # Grade band / curriculum bonuses are irrelevant when the subject is wrong.
        if align_subjects_lower and subjects and not subject_matched:
            return 0.0

        if subject_matched:
            score += 0.40

        align_grade = str(
            alignment.get("grade_band") or alignment.get("grade") or ""
        ).strip().lower()
        if grade_band and align_grade and (
            grade_band == align_grade
            or grade_band in align_grade
            or align_grade in grade_band
        ):
            score += 0.25

        align_curr = str(
            alignment.get("curriculum_framework") or alignment.get("curriculum") or ""
        ).strip().lower()
        if curriculum and align_curr and curriculum == align_curr:
            score += 0.10

    # ── category field ───────────────────────────────────────────────────────
    category = (item.category or "").strip().lower()
    if category and subjects and any(ps in category or category in ps for ps in subjects):
        score += 0.20

    # ── tags JSONB ───────────────────────────────────────────────────────────
    if subjects:
        tags = item.tags or {}
        if isinstance(tags, dict):
            tag_subjects = tags.get("subjects") or tags.get("subject") or []
            if isinstance(tag_subjects, str):
                tag_subjects = [tag_subjects]
            if any(ps in [str(t).strip().lower() for t in tag_subjects] for ps in subjects):
                score = max(score, 0.15)
            tag_text = " ".join(str(v).lower() for v in tags.values() if v)
        elif isinstance(tags, list):
            tag_text = " ".join(str(t).lower() for t in tags)
        else:
            tag_text = ""
        if tag_text and any(ps in tag_text for ps in subjects):
            score += 0.15

    return min(score, 1.0)


def _rank_content_for_section(
    db: Session,
    section: str,
    profile_snapshot: dict[str, Any],
    limit: int = 15,
) -> list[dict[str, Any]]:
    """
    Rank content items for a section filtered and scored against the profile snapshot.

    Only items with _score_item_for_profile >= _PROFILE_MATCH_THRESHOLD are included.
    If no items pass, returns [] so the orchestrator leaves the section in
    preparing/generating state rather than filling with unrelated content.
    """
    if not _CONTENT_REGISTRY_AVAILABLE:
        return []

    allowed_types = SECTION_CONTENT_TYPES.get(section, [])
    if not allowed_types:
        return []

    try:
        from app.domains.learning_hub.route_resolver import resolve_learning_hub_route

        # Prefer factory-generated content; fall back to starter_seed only if thin.
        preferred_items = (
            db.query(ContentRegistryItem)
            .filter(
                ContentRegistryItem.content_type.in_(allowed_types),
                ContentRegistryItem.status == "published",
                ContentRegistryItem.source_type == "content_factory",
            )
            .order_by(ContentRegistryItem.created_at.desc())
            .limit(limit * 6)
            .all()
        )
        candidates = list(preferred_items)
        if len(preferred_items) < limit:
            fallback_items = (
                db.query(ContentRegistryItem)
                .filter(
                    ContentRegistryItem.content_type.in_(allowed_types),
                    ContentRegistryItem.status == "published",
                    ContentRegistryItem.source_type == "starter_seed",
                )
                .order_by(ContentRegistryItem.created_at.desc())
                .limit(limit * 4)
                .all()
            )
            candidates.extend(fallback_items)

        # ── Profile-aware scoring & filtering ────────────────────────────────
        scored: list[tuple[Any, float]] = []
        unmatched_count = 0
        for item in candidates:
            item_score = _score_item_for_profile(item, profile_snapshot)
            if item_score >= _PROFILE_MATCH_THRESHOLD:
                scored.append((item, item_score))
            else:
                unmatched_count += 1

        if not scored:
            # Nothing matches profile — do NOT fill with generic recency picks.
            # Log so ops can diagnose thin inventory for this profile type.
            logger.info(
                "personalization.no_profile_match",
                extra={
                    "section": section,
                    "subjects": profile_snapshot.get("subjects"),
                    "grade_band": profile_snapshot.get("grade_band"),
                    "candidates_checked": len(candidates),
                    "unmatched_suppressed": unmatched_count,
                },
            )
            return []

        # Sort by profile score descending so best matches appear first.
        scored.sort(key=lambda x: x[1], reverse=True)

        # ── Dedup + quality filters ──────────────────────────────────────────
        ranked = []
        seen_titles: set[str] = set()
        seen_content_ids: set[str] = set()
        category_counts: dict[str, int] = {}

        for item, item_score in scored:
            if len(ranked) >= limit:
                break

            norm_title = (item.title or "").strip().lower()
            if item.content_id in seen_content_ids:
                continue
            if norm_title and norm_title in seen_titles:
                continue
            if not _title_quality_ok(item.title):
                continue
            if not _duration_quality_ok(item.content_type, item.estimated_duration_min):
                continue
            category = (item.category or "").strip().lower()
            if category and category_counts.get(category, 0) >= 2:
                continue

            seen_content_ids.add(item.content_id)
            if norm_title:
                seen_titles.add(norm_title)
            if category:
                category_counts[category] = category_counts.get(category, 0) + 1

            try:
                route = resolve_learning_hub_route(item)
            except Exception:
                route = "/learning-hub"

            ranked.append({
                "content_id": item.content_id,
                "content_type": item.content_type,
                "source_type": item.source_type,
                "score": round(item_score, 4),
                "reason_codes": ["profile_match"],
                "ranking_signals": {
                    "subjects": profile_snapshot.get("subjects"),
                    "grade_band": profile_snapshot.get("grade_band"),
                },
                "route": route,
                "content_slug": item.content_id,
                "title": item.title,
            })

        return ranked
    except Exception as exc:
        logger.error("personalization.rank_content_failed", extra={"section": section, "error": str(exc)})
        return []


class PersonalizationOrchestrator:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.profile_svc = PersonalizationProfileService(db)
        self.version_svc = ProfileVersionService(db)
        self.snapshot_svc = PersonalizationSnapshotService(db)
        self.job_svc = PersonalizationJobService(db)
        self.assignment_svc = AssignmentService(db)
        self.slate_svc = SlateService(db)
        self.readiness_svc = SectionReadinessService(db)
        self.unlock_svc = UnlockService(db)

    def start_personalization(
        self,
        user_id: uuid.UUID,
        profile_snapshot: dict[str, Any],
        profile_completeness: float = 100.0,
        trigger: str = "initial",
    ) -> UserPersonalizationProfile:
        """Full initialization flow: profile → version → snapshot → assignments → slate → readiness."""
        profile = self.profile_svc.get_or_create(user_id, profile_completeness)
        self.profile_svc.mark_started(profile)

        job = self.job_svc.create(profile, "start", trigger=trigger)
        self.job_svc.mark_running(job)

        try:
            # Record profile version
            self.version_svc.record_version(
                profile, profile_snapshot, profile_completeness, change_type="initial"
            )

            # Create snapshot
            snapshot = self.snapshot_svc.create(profile, trigger=trigger, ranking_signals={"completeness": profile_completeness})

            # Initialize readiness rows
            readiness_rows = self.readiness_svc.initialize_all(profile, snapshot_id=snapshot.id, job_id=job.id)
            for sr in readiness_rows:
                self.readiness_svc.transition(sr, SectionReadinessStatus.PREPARING, job_id=job.id)

            # Create assignments per section
            all_assignments: list[PersonalizedContentAssignment] = []
            for section_key in SectionKey:
                section = section_key.value
                ranked = _rank_content_for_section(self.db, section, profile_snapshot)
                if ranked:
                    assignments = self.assignment_svc.create_from_ranked(
                        profile, snapshot.id, section, ranked
                    )
                    all_assignments.extend(assignments)

                    # Update readiness
                    sr = self.readiness_svc.get(user_id, section, profile.personalization_version)
                    visible_assignments = [a for a in assignments if a.bucket == "visible"]
                    locked_preview_assignments = [a for a in assignments if a.bucket == "locked_preview"]
                    if sr:
                        self.readiness_svc.update_inventory_readiness(
                            sr,
                            visible_actual=len(visible_assignments),
                            locked_preview_actual=len(locked_preview_assignments),
                            slate_id=None,
                        )

            # Initialize unlock states for all assignments
            self.unlock_svc.initialize_unlock_states(user_id, all_assignments)

            # Build slate
            slate = self.slate_svc.build_slate(profile, snapshot_id=snapshot.id)

            # Update readiness with slate reference
            for section_key in SectionKey:
                section = section_key.value
                sr = self.readiness_svc.get(user_id, section, profile.personalization_version)
                if sr and sr.status in (SectionReadinessStatus.PREPARING, SectionReadinessStatus.PARTIAL_READY):
                    visible_items = [a for a in all_assignments if a.section == section and a.bucket == "visible"]
                    locked_preview_items = [
                        a for a in all_assignments if a.section == section and a.bucket == "locked_preview"
                    ]
                    self.readiness_svc.update_inventory_readiness(
                        sr,
                        visible_actual=len(visible_items),
                        locked_preview_actual=len(locked_preview_items),
                        slate_id=slate.id,
                    )

            self.profile_svc.mark_recomputed(profile)
            self.job_svc.mark_completed(job)

            logger.info(
                "personalization.started",
                extra={"user_id": str(user_id), "version": profile.personalization_version},
            )
            InventoryExpansionWorker.run_in_background(user_id, trigger="after_start_personalization")
            return profile

        except Exception as exc:
            self.job_svc.mark_failed(job, str(exc))
            # Mark all preparing sections as failed
            for section_key in SectionKey:
                sr = self.readiness_svc.get(user_id, section_key.value, profile.personalization_version)
                if sr and sr.status == SectionReadinessStatus.PREPARING:
                    self.readiness_svc.transition(sr, SectionReadinessStatus.FAILED)
            raise

    def recompute(
        self,
        user_id: uuid.UUID,
        profile_snapshot: dict[str, Any],
        trigger: str = "minor_recompute",
    ) -> UserPersonalizationProfile:
        """Minor update: re-score existing assignments, rebuild slate. Preserve unlock states."""
        profile = self.profile_svc.get(user_id)
        if not profile:
            raise ValueError(f"No personalization profile for user {user_id}")

        job = self.job_svc.create(profile, "recompute", trigger=trigger)
        self.job_svc.mark_running(job)

        try:
            snapshot = self.snapshot_svc.create(profile, trigger=trigger)

            # Refill missing inventory before rebuilding slate.
            for section_key in SectionKey:
                section = section_key.value
                if self.assignment_svc.needs_refill(user_id, section, profile.personalization_version):
                    ranked = _rank_content_for_section(self.db, section, profile_snapshot, limit=30)
                    if ranked:
                        self.assignment_svc.create_from_ranked(
                            profile,  # same version
                            snapshot_id=snapshot.id,
                            section=section,
                            ranked_items=ranked,
                        )
            slate = self.slate_svc.build_slate(profile, snapshot_id=snapshot.id)

            # Mark all sections as stale → ready after rebuild
            for section_key in SectionKey:
                sr = self.readiness_svc.get(user_id, section_key.value, profile.personalization_version)
                if sr and sr.status == SectionReadinessStatus.READY:
                    self.readiness_svc.transition(sr, SectionReadinessStatus.STALE)
                if sr:
                    section_assignments = self.assignment_svc.get_active(
                        user_id, section_key.value, profile.personalization_version
                    )
                    visible_items = [a for a in section_assignments if a.bucket == "visible"]
                    locked_preview_items = [a for a in section_assignments if a.bucket == "locked_preview"]
                    self.readiness_svc.update_inventory_readiness(
                        sr,
                        visible_actual=len(visible_items),
                        locked_preview_actual=len(locked_preview_items),
                        slate_id=slate.id,
                    )

            self.profile_svc.mark_recomputed(profile)
            self.job_svc.mark_completed(job)

            logger.info(
                "personalization.recompute_triggered",
                extra={"user_id": str(user_id), "trigger": trigger},
            )
            InventoryExpansionWorker.run_in_background(user_id, trigger=f"after_recompute:{trigger}")
            return profile
        except Exception as exc:
            self.job_svc.mark_failed(job, str(exc))
            raise

    def reset(
        self,
        user_id: uuid.UUID,
        new_profile_snapshot: dict[str, Any],
        profile_completeness: float = 100.0,
        trigger: str = "major_reset",
    ) -> UserPersonalizationProfile:
        """Major reset: archive old version, increment, re-run start flow."""
        profile = self.profile_svc.get(user_id)
        if not profile:
            raise ValueError(f"No personalization profile for user {user_id}")

        old_version = profile.personalization_version

        job = self.job_svc.create(profile, "reset", trigger=trigger)
        self.job_svc.mark_running(job)

        try:
            # Archive old assignments
            superseded = self.assignment_svc.supersede_all(user_id, old_version, old_version + 1)

            # Archive old slate
            from app.domains.personalization.models import RecommendationSlate
            self.db.query(RecommendationSlate).filter(
                RecommendationSlate.user_id == user_id,
                RecommendationSlate.is_current == True,  # noqa: E712
            ).update({"is_current": False})

            # Increment version
            self.profile_svc.increment_version(profile)

            # Record the new version
            self.version_svc.record_version(
                profile, new_profile_snapshot, profile_completeness,
                change_type="major_reset",
            )

            self.job_svc.mark_completed(job)

            logger.info(
                "personalization.reset_triggered",
                extra={"user_id": str(user_id), "old_version": old_version, "new_version": profile.personalization_version},
            )

            # Re-run start for new version
            return self.start_personalization(user_id, new_profile_snapshot, profile_completeness, trigger="post_reset")

        except Exception as exc:
            self.job_svc.mark_failed(job, str(exc))
            raise
