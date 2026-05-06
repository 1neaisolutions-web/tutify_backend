"""
Deterministic ranking and deduplication for Learning Hub recommendations.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.domains.content_registry.models import ContentRegistryItem
from app.domains.content_registry.schemas import RecommendationCard, RecommendationMappingResponse
from app.domains.content_registry.services.content_registry_service import ContentRegistryService
from app.domains.content_registry.enums import ContentStatus, ContentType
from app.domains.teacher_intelligence.services import CTPAssemblerService, MLOutputService
from app.domains.recommendation_analytics.models import RecommendationPerformanceSnapshot
from app.domains.recommendation_engine.services.recommendation_scoring_service import (
    RecommendationScoringService,
    TeacherBehaviorProfile,
)
from app.domains.content_factory.services.gap_generation_service import GapGenerationService
from app.domains.learning_hub.route_resolver import (
    resolve_delivery_slug,
    resolve_learning_hub_route,
    validate_frontend_route,
)

logger = get_logger(__name__)

PREFERRED_TYPES = [
    ContentType.MICRO_COURSE.value,
    ContentType.AI_GUIDED_TUTORIAL.value,
    ContentType.LEARNING_PATH.value,
]

STARTER_BASE_SLUGS = [
    "classroom-management-quick-wins",
    "classroom-management-learning-path",
    "student-engagement-strategies",
    "formative-assessment-essentials",
    "differentiation-made-simple",
    "lesson-planning-with-ai",
    "lesson-planning-learning-path",
]

_FOUNDATIONAL_CATEGORY_HINTS = (
    "foundational",
    "core teaching skills",
    "beginner-friendly",
    "classroom_management",
    "lesson_planning",
    "assessment",
)
_STARTER_PENALTY_WHEN_HEALTHY = 0.35


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


class RecommendationRankingService:
    def __init__(self, db: Session):
        self.db = db
        self.scoring = RecommendationScoringService(db)

    def _analytics_index(self, content_ids: List[str]) -> Dict[str, RecommendationPerformanceSnapshot]:
        if not content_ids:
            return {}
        rows = (
            self.db.query(RecommendationPerformanceSnapshot)
            .filter(RecommendationPerformanceSnapshot.content_id.in_(content_ids))
            .order_by(RecommendationPerformanceSnapshot.snapshot_date.desc())
            .all()
        )
        index: Dict[str, RecommendationPerformanceSnapshot] = {}
        for row in rows:
            if row.content_id not in index:
                index[row.content_id] = row
        return index

    @staticmethod
    def _delivery_for_card(item: Any) -> Optional[Dict[str, Any]]:
        blob = item.json_blob or {}
        d = blob.get("delivery")
        if not isinstance(d, dict):
            return None
        out: Dict[str, Any] = {}
        for k in ("route", "slug", "media_steps", "publishing"):
            if k in d:
                out[k] = d[k]
        return out or None

    def _item_to_card(
        self,
        item: ContentRegistryItem,
        score: float,
        reason: str,
        route: Optional[str] = None,
    ) -> RecommendationCard:
        canonical = resolve_learning_hub_route(item)
        resolved_route = validate_frontend_route(route) or canonical
        return RecommendationCard(
            content_id=item.content_id,
            content_type=item.content_type,
            title=item.title,
            subtitle=item.subtitle,
            summary=item.summary,
            category=item.category,
            estimated_duration_min=item.estimated_duration_min,
            difficulty=item.difficulty,
            route=resolved_route,
            content_slug=resolve_delivery_slug(item),
            delivery=self._delivery_for_card(item),
            score=score,
            reason=reason,
        )

    def _is_valid_candidate(self, item: ContentRegistryItem, locale: str) -> bool:
        return bool(
            item
            and item.status == ContentStatus.PUBLISHED.value
            and (not locale or item.locale == locale)
            and item.content_type in PREFERRED_TYPES
        )

    def _card_reason(self, mode: str, scored: Dict[str, Any], fallback: str) -> str:
        reason = str(scored.get("reason") or "").strip()
        if reason:
            return reason
        if mode == "cold_start":
            return "A great place to start"
        if mode == "warm_start":
            return "Based on your teaching profile"
        return fallback

    def _score_for_mode(self, mode: str, scored: Dict[str, Any]) -> float:
        if mode == "cold_start":
            return max(0.55, float(scored.get("components", {}).get("engagement", 0.0) or 0.0))
        if mode == "warm_start":
            components = scored.get("components", {})
            return max(
                0.6,
                float(scored.get("score", 0.0) or 0.0),
                float(components.get("goal_match", 0.0) or 0.0) * 0.9,
                float(components.get("context_match", 0.0) or 0.0) * 0.85,
                float(components.get("engagement", 0.0) or 0.0) * 0.6,
            )
        return float(scored.get("score", 0.0) or 0.0)

    def _is_foundational(self, item: ContentRegistryItem) -> bool:
        blob = " ".join(
            [
                _norm(item.category),
                _norm(item.difficulty),
                _norm(item.title),
                _norm(item.subtitle),
                _norm(item.summary),
                " ".join(_norm(tag) for tag in (item.tags or {}).values()) if isinstance(item.tags, dict) else _norm(item.tags),
            ]
        )
        return any(hint in blob for hint in _FOUNDATIONAL_CATEGORY_HINTS)

    @staticmethod
    def _is_starter_item(item: Optional[ContentRegistryItem]) -> bool:
        if not item:
            return False
        if getattr(item, "source_type", None) == "starter_seed":
            return True
        if str(item.content_id or "").startswith("starter-"):
            return True
        tags = item.tags or {}
        if isinstance(tags, dict):
            starter_flag = tags.get("starter")
            if starter_flag is True:
                return True
            if isinstance(starter_flag, str) and starter_flag.strip().lower() == "true":
                return True
        return False

    def _score_with_starter_penalty(
        self,
        item: ContentRegistryItem,
        base_score: float,
        healthy_non_starter_pool: bool,
    ) -> float:
        """
        Keep starter content as safety net, but stop it from dominating once locale has
        enough published non-starter content.
        """
        if healthy_non_starter_pool and self._is_starter_item(item):
            return max(0.0, float(base_score) - _STARTER_PENALTY_WHEN_HEALTHY)
        return float(base_score)

    def _unique_append(
        self,
        bucket: List[RecommendationCard],
        seen: Set[str],
        seen_fingerprints: Set[str],
        card: RecommendationCard,
        limit: int,
    ) -> bool:
        # Deduplicate both by content_id and by semantic fingerprint to avoid
        # repeated cards when multiple generated items share the same title/topic.
        fp = f"{_norm(card.content_type)}|{_norm(card.category)}|{_norm(card.title)}"
        if card.content_id in seen or fp in seen_fingerprints or len(bucket) >= limit:
            return False
        bucket.append(card)
        seen.add(card.content_id)
        seen_fingerprints.add(fp)
        return True

    def _get_cold_start_recommendations(
        self,
        published: List[ContentRegistryItem],
        behavior: TeacherBehaviorProfile,
        analytics_index: Dict[str, RecommendationPerformanceSnapshot],
        limit: int,
        healthy_non_starter_pool: bool = False,
    ) -> RecommendationMappingResponse:
        primary: List[RecommendationCard] = []
        secondary: List[RecommendationCard] = []
        seen: Set[str] = set()
        seen_fingerprints: Set[str] = set()

        candidates = [item for item in published if self._is_valid_candidate(item, getattr(item, "locale", ""))]
        candidates = [item for item in candidates if self._is_foundational(item) or _norm(item.difficulty) in {"beginner", "introductory"}]
        if not candidates:
            candidates = [item for item in published if self._is_valid_candidate(item, getattr(item, "locale", ""))]

        scored_items = []
        for item in candidates:
            scored = self.scoring.score_item(item, behavior, analytics_index.get(item.content_id))
            total = self._score_with_starter_penalty(
                item,
                self._score_for_mode("cold_start", scored),
                healthy_non_starter_pool=healthy_non_starter_pool,
            )
            scored_items.append((total, item, scored))
        scored_items.sort(key=lambda row: (row[0], _norm(row[1].title)), reverse=True)

        for total, item, scored in scored_items:
            card = self._item_to_card(item, score=total, reason=self._card_reason("cold_start", scored, "Recommended for new learners"))
            target = primary if len(primary) < min(3, limit) else secondary
            if self._unique_append(target, seen, seen_fingerprints, card, min(3, limit)):
                continue
            if len(secondary) < min(3, limit):
                self._unique_append(secondary, seen, seen_fingerprints, card, min(3, limit))

        if not primary:
            return self._fallback_cold_start(published, behavior, analytics_index, limit)
        return RecommendationMappingResponse(primary_recommendations=primary[:3], secondary_recommendations=secondary[:3])

    def _get_warm_start_recommendations(
        self,
        published: List[ContentRegistryItem],
        behavior: TeacherBehaviorProfile,
        analytics_index: Dict[str, RecommendationPerformanceSnapshot],
        limit: int,
        healthy_non_starter_pool: bool = False,
    ) -> RecommendationMappingResponse:
        primary: List[RecommendationCard] = []
        secondary: List[RecommendationCard] = []
        seen: Set[str] = set()
        seen_fingerprints: Set[str] = set()

        scored_items = []
        for item in published:
            if not self._is_valid_candidate(item, getattr(item, "locale", "")):
                continue
            scored = self.scoring.score_item(item, behavior, analytics_index.get(item.content_id))
            components = scored.get("components", {})
            if components.get("goal_match", 0) > 0 or components.get("context_match", 0) > 0 or components.get("engagement", 0) > 0:
                total = self._score_with_starter_penalty(
                    item,
                    self._score_for_mode("warm_start", scored),
                    healthy_non_starter_pool=healthy_non_starter_pool,
                )
                scored_items.append((total, item, scored))

        scored_items.sort(key=lambda row: (row[0], _norm(row[1].title)), reverse=True)

        for total, item, scored in scored_items:
            card = self._item_to_card(item, score=total, reason=self._card_reason("warm_start", scored, "Selected for your teaching context"))
            if len(primary) < min(3, limit):
                self._unique_append(primary, seen, seen_fingerprints, card, min(3, limit))
            elif len(secondary) < min(3, limit):
                self._unique_append(secondary, seen, seen_fingerprints, card, min(3, limit))

        if not primary:
            return self._fallback_cold_start(published, behavior, analytics_index, limit)
        return RecommendationMappingResponse(primary_recommendations=primary[:3], secondary_recommendations=secondary[:3])

    def _fallback_cold_start(
        self,
        published: List[ContentRegistryItem],
        behavior: TeacherBehaviorProfile,
        analytics_index: Dict[str, RecommendationPerformanceSnapshot],
        limit: int,
        healthy_non_starter_pool: bool = False,
    ) -> RecommendationMappingResponse:
        primary: List[RecommendationCard] = []
        secondary: List[RecommendationCard] = []
        seen: Set[str] = set()
        seen_fingerprints: Set[str] = set()
        for item in published:
            if not self._is_valid_candidate(item, getattr(item, "locale", "")):
                continue
            scored = self.scoring.score_item(item, behavior, analytics_index.get(item.content_id))
            card = self._item_to_card(
                item,
                score=self._score_with_starter_penalty(
                    item,
                    self._score_for_mode("cold_start", scored),
                    healthy_non_starter_pool=healthy_non_starter_pool,
                ),
                reason="Popular among teachers",
            )
            if len(primary) < min(3, limit):
                self._unique_append(primary, seen, seen_fingerprints, card, min(3, limit))
            elif len(secondary) < min(3, limit):
                self._unique_append(secondary, seen, seen_fingerprints, card, min(3, limit))
            if len(primary) >= 3 and len(secondary) >= 3:
                break
        return RecommendationMappingResponse(primary_recommendations=primary[:3], secondary_recommendations=secondary[:3])

    def _get_personalized_recommendations(
        self,
        published: List[ContentRegistryItem],
        behavior: TeacherBehaviorProfile,
        analytics_index: Dict[str, RecommendationPerformanceSnapshot],
        ml_output: Any,
        limit: int,
        healthy_non_starter_pool: bool = False,
    ) -> RecommendationMappingResponse:
        primary: List[RecommendationCard] = []
        secondary: List[RecommendationCard] = []
        seen: Set[str] = set()
        seen_fingerprints: Set[str] = set()

        published_index = {item.content_id: item for item in published if item}

        for content_id in behavior.in_progress_content_ids:
            item = published_index.get(content_id)
            if not self._is_valid_candidate(item, getattr(item, "locale", "")) or item.content_id in seen:
                continue
            scored = self.scoring.score_item(item, behavior, analytics_index.get(item.content_id))
            self._unique_append(
                primary,
                seen,
                seen_fingerprints,
                self._item_to_card(
                    item,
                    score=self._score_with_starter_penalty(
                        item,
                        max(0.95, self._score_for_mode("personalized", scored)),
                        healthy_non_starter_pool=healthy_non_starter_pool,
                    ),
                    reason="Continue where you left off",
                ),
                min(3, limit),
            )
            if len(primary) >= 3:
                break

        if ml_output and isinstance(ml_output.results, dict):
            targets = ml_output.results.get("recommended_targets") or []
            for t in targets:
                if len(primary) >= 3:
                    break
                target_id = t.get("target_id") or t.get("content_id") if isinstance(t, dict) else str(t) if t else None
                if not target_id or target_id in seen:
                    continue
                item = published_index.get(str(target_id))
                if not self._is_valid_candidate(item, getattr(item, "locale", "")):
                    continue
                scored = self.scoring.score_item(item, behavior, analytics_index.get(item.content_id))
                total = max(float(t.get("score") or 0.0) if isinstance(t, dict) else 0.0, self._score_for_mode("personalized", scored))
                total = self._score_with_starter_penalty(
                    item,
                    total,
                    healthy_non_starter_pool=healthy_non_starter_pool,
                )
                self._unique_append(
                    primary,
                    seen,
                    seen_fingerprints,
                    self._item_to_card(item, score=total, reason=self._card_reason("personalized", scored, "Recommended by your learning profile")),
                    min(3, limit),
                )

        for item in published:
            if item.content_id in seen or not self._is_valid_candidate(item, getattr(item, "locale", "")):
                continue
            scored = self.scoring.score_item(item, behavior, analytics_index.get(item.content_id))
            components = scored["components"]
            if components["goal_match"] > 0 or components["context_match"] > 0 or components["engagement"] > 0:
                card = self._item_to_card(
                    item,
                    score=self._score_with_starter_penalty(
                        item,
                        max(0.5, self._score_for_mode("personalized", scored)),
                        healthy_non_starter_pool=healthy_non_starter_pool,
                    ),
                    reason=self._card_reason("personalized", scored, "Matches your goals and recent activity"),
                )
                if len(primary) < 3:
                    self._unique_append(primary, seen, seen_fingerprints, card, min(3, limit))
                elif len(secondary) < 3:
                    self._unique_append(secondary, seen, seen_fingerprints, card, min(3, limit))
            if len(primary) >= 3 and len(secondary) >= 3:
                break

        if not primary:
            return self._fallback_cold_start(published, behavior, analytics_index, limit)
        return RecommendationMappingResponse(primary_recommendations=primary[:3], secondary_recommendations=secondary[:3])

    def get_learning_hub_recommendations(self, teacher_id: UUID, locale: str = "en", limit: int = 6, mode: str = "personalized") -> RecommendationMappingResponse:
        registry_svc = ContentRegistryService(self.db)
        ctp = {}
        try:
            ctp = CTPAssemblerService(self.db).assemble(teacher_id) or {}
        except Exception:  # pragma: no cover - defensive
            try:
                self.db.rollback()
            except Exception:
                pass
            ctp = {}
        ml_output = None
        try:
            ml_output = MLOutputService(self.db).get_latest(teacher_id, pipeline_name="pipeline2")
        except Exception:  # pragma: no cover - defensive
            try:
                self.db.rollback()
            except Exception:
                pass
            ml_output = None
        identity = ctp.get("identity") or {}
        goals = ctp.get("goals") or []
        subjects = identity.get("subjects") or []
        grade_band = identity.get("grade_band") or ""

        # Behavior signals are optional for bootstrapping. If learning_progress tables
        # are missing/inaccessible, degrade gracefully to an empty behavior profile.
        try:
            behavior = self.scoring.build_behavior_profile(
                teacher_id, goals=goals, subjects=subjects, grade_band=grade_band
            )
        except Exception:  # pragma: no cover - defensive
            try:
                self.db.rollback()
            except Exception:
                pass
            behavior = TeacherBehaviorProfile(
                goals=goals or [],
                subjects=subjects or [],
                grade_band=_norm(grade_band),
            )

        # Ensure starter content exists for locale and default 'en'
        registry_svc.seed_learning_hub_starter_content(locales=[locale, "en"])

        published_locale = registry_svc.list_items(status=ContentStatus.PUBLISHED.value, locale=locale, limit=100)
        published_index = {item.content_id: item for item in published_locale if item}
        candidate_count = len(published_index)

        # If locale is thin, augment with default 'en' content and allow cross-locale fallback.
        if candidate_count < settings.MIN_CONTENT_PER_LOCALE and locale != "en":
            published_en = registry_svc.list_items(status=ContentStatus.PUBLISHED.value, locale="en", limit=100)
            for item in published_en:
                if item and item.content_id not in published_index:
                    published_index[item.content_id] = item
            candidate_count = len(published_index)
            published = list(published_index.values())
            effective_locale = ""  # disable strict locale check in _is_valid_candidate for fallback pool
        else:
            published = list(published_index.values())
            effective_locale = locale

        analytics_index = self._analytics_index(list(published_index.keys()))

        if settings.ENABLE_RECOMMENDATION_DEBUG:
            logger.info(
                "learning_hub_ranking_start",
                extra={
                    "mode": mode,
                    "candidate_count_total": candidate_count,
                    "locale": locale,
                },
            )

        non_starter_locale_count = len(
            [item for item in published_locale if self._is_valid_candidate(item, locale) and not self._is_starter_item(item)]
        )
        healthy_non_starter_pool = non_starter_locale_count >= max(3, settings.MIN_CONTENT_PER_LOCALE)

        if mode == "cold_start":
            response = self._get_cold_start_recommendations(
                published,
                behavior,
                analytics_index,
                limit,
                healthy_non_starter_pool=healthy_non_starter_pool,
            )
            strategy = "cold_start"
        elif mode == "warm_start":
            response = self._get_warm_start_recommendations(
                published,
                behavior,
                analytics_index,
                limit,
                healthy_non_starter_pool=healthy_non_starter_pool,
            )
            strategy = "warm_start"
        else:
            response = self._get_personalized_recommendations(
                published,
                behavior,
                analytics_index,
                ml_output,
                limit,
                healthy_non_starter_pool=healthy_non_starter_pool,
            )
            strategy = "personalized"

        fallback_used = False
        if not response.primary_recommendations:
            fallback_used = True
            response = self._fallback_cold_start(
                published,
                behavior,
                analytics_index,
                limit,
                healthy_non_starter_pool=healthy_non_starter_pool,
            )

        # Ensure generated/non-starter content is visible when it exists.
        # This is intentionally conservative: only when the response contains zero non-starter items.
        try:
            non_starter_items = [it for it in published if it and not self._is_starter_item(it)]
            if non_starter_items:
                non_starter_ids = {it.content_id for it in non_starter_items}
                rec_ids = {
                    c.content_id
                    for c in (response.primary_recommendations + response.secondary_recommendations)
                    if getattr(c, "content_id", None)
                }
                if rec_ids.isdisjoint(non_starter_ids):
                    best_item = None
                    best_total = float("-inf")
                    for it in non_starter_items:
                        scored = self.scoring.score_item(it, behavior, analytics_index.get(it.content_id))
                        total = self._score_with_starter_penalty(
                            it,
                            self._score_for_mode(mode, scored),
                            healthy_non_starter_pool=healthy_non_starter_pool,
                        )
                        if total > best_total:
                            best_total = total
                            best_item = it
                    if best_item is not None:
                        card = self._item_to_card(
                            best_item,
                            score=best_total,
                            reason="Recommended from newly generated content",
                        )
                        # Prefer primary slot so the UI's main recommendation area shows AI content.
                        if response.primary_recommendations:
                            response.primary_recommendations[-1] = card
                        elif len(response.secondary_recommendations) < 3:
                            response.secondary_recommendations.append(card)
                        elif response.secondary_recommendations:
                            response.secondary_recommendations[-1] = card
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to inject non-starter recommendation: %s", exc)

        # Guarantee at least one learning_path recommendation in the home payload.
        # The frontend AI Growth Recommendations panel only renders when the home payload
        # includes learning-path-like registry cards in primary/secondary recommendations.
        try:
            has_learning_path = any(
                (getattr(c, "content_type", "") or "").strip() == ContentType.LEARNING_PATH.value
                for c in (response.primary_recommendations + response.secondary_recommendations)
            )
            if not has_learning_path:
                path_candidates = [
                    it
                    for it in published
                    if getattr(it, "content_type", None) == ContentType.LEARNING_PATH.value
                ]
                if path_candidates:
                    # Prefer non-starter content if the pool is healthy; otherwise allow starter paths.
                    non_starter = [it for it in path_candidates if not self._is_starter_item(it)]
                    pool = non_starter if non_starter else path_candidates
                    best_item = None
                    best_total = float("-inf")
                    for it in pool:
                        scored = self.scoring.score_item(it, behavior, analytics_index.get(it.content_id))
                        total = self._score_with_starter_penalty(
                            it,
                            self._score_for_mode(mode, scored),
                            healthy_non_starter_pool=healthy_non_starter_pool,
                        )
                        if total > best_total:
                            best_total = total
                            best_item = it
                    if best_item is not None:
                        best_card = self._item_to_card(
                            best_item,
                            score=best_total,
                            reason="Recommended learning path for your growth",
                        )
                        if response.primary_recommendations:
                            response.primary_recommendations[-1] = best_card
                        elif response.secondary_recommendations and len(response.secondary_recommendations) < 3:
                            response.secondary_recommendations.append(best_card)
                        else:
                            # If primary is empty but secondary has 3 items, replace the last one.
                            if response.secondary_recommendations:
                                response.secondary_recommendations[-1] = best_card
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to inject learning_path recommendation: %s", exc)

        # Guarantee at least one card for each home section type:
        # - micro_course (Personalized micro-courses)
        # - ai_guided_tutorial (AI-guided tutorials)
        # - learning_path (AI Growth Recommendations)
        # This keeps section composition stable without mixing entity types.
        try:
            def _inject_required_type(ctype: str, reason: str) -> None:
                cards_all = response.primary_recommendations + response.secondary_recommendations
                if any((getattr(c, "content_type", "") or "").strip() == ctype for c in cards_all):
                    return
                candidates = [it for it in published if getattr(it, "content_type", None) == ctype]
                if not candidates:
                    return
                non_starter = [it for it in candidates if not self._is_starter_item(it)]
                pool = non_starter if non_starter else candidates
                best_item = None
                best_total = float("-inf")
                for it in pool:
                    scored = self.scoring.score_item(it, behavior, analytics_index.get(it.content_id))
                    total = self._score_with_starter_penalty(
                        it,
                        self._score_for_mode(mode, scored),
                        healthy_non_starter_pool=healthy_non_starter_pool,
                    )
                    if total > best_total:
                        best_total = total
                        best_item = it
                if best_item is None:
                    return
                best_card = self._item_to_card(best_item, score=best_total, reason=reason)
                if response.primary_recommendations:
                    response.primary_recommendations[-1] = best_card
                elif len(response.secondary_recommendations) < 3:
                    response.secondary_recommendations.append(best_card)
                elif response.secondary_recommendations:
                    response.secondary_recommendations[-1] = best_card

            _inject_required_type(ContentType.MICRO_COURSE.value, "Recommended micro-course for your profile")
            _inject_required_type(ContentType.AI_GUIDED_TUTORIAL.value, "Recommended guided tutorial for your profile")
            _inject_required_type(ContentType.LEARNING_PATH.value, "Recommended learning path for your growth")
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to enforce section type coverage: %s", exc)

        # Simple gap detection:
        # - insufficient pool OR too few results -> enqueue async jobs
        # - non-starter pool unhealthy -> enqueue async jobs even if starter content exists
        try:
            if (
                candidate_count < settings.MIN_CONTENT_PER_LOCALE
                or (
                    len(response.primary_recommendations) + len(response.secondary_recommendations) < limit
                )
                or (not healthy_non_starter_pool)
            ):
                identity = ctp.get("identity") or {}
                subjects = identity.get("subjects") or []
                grade_band = identity.get("grade_band") or ""

                # If teacher profile has no explicit subjects, derive candidates from what
                # already exists in the registry (categories from starter content).
                if not subjects:
                    try:
                        derived: List[str] = []
                        for it in published_index.values():
                            cat = getattr(it, "category", None)
                            if cat:
                                derived.append(str(cat))
                        # keep unique, stable order
                        seen: Set[str] = set()
                        subjects = [x for x in derived if not (x.lower() in seen or seen.add(x.lower()))][:5]
                    except Exception:
                        subjects = []

                if not subjects:
                    return response

                GapGenerationService(self.db).enqueue_gap_jobs(
                    locale=locale,
                    subjects=subjects,
                    grade_band=grade_band or None,
                    mode=mode,
                    prefer_non_starter=not healthy_non_starter_pool,
                )
                if settings.ENABLE_RECOMMENDATION_DEBUG:
                    logger.info(
                        "learning_hub_gap_detected",
                        extra={
                            "mode": mode,
                            "strategy": strategy,
                            "candidate_count_total": candidate_count,
                            "results_primary": len(response.primary_recommendations),
                            "results_secondary": len(response.secondary_recommendations),
                            "subjects": subjects,
                            "grade_band": grade_band,
                        },
                    )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Gap detection/enqueue failed: %s", exc)

        # Final hard guard: if still empty, force starter content cards (locale-first, then en).
        if not response.primary_recommendations and not response.secondary_recommendations:
            starter_cards: List[RecommendationCard] = []
            seen_ids: Set[str] = set()
            for base in STARTER_BASE_SLUGS:
                for loc in [locale, "en"]:
                    cid = f"starter-{loc}-{base}"
                    if cid in seen_ids:
                        continue
                    item = registry_svc.get_item_by_content_id(cid)
                    if not item:
                        continue
                    seen_ids.add(cid)
                    starter_cards.append(
                        self._item_to_card(
                            item,
                            score=1.0,
                            reason="A great place to start",
                        )
                    )
                    if len(starter_cards) >= limit:
                        break
                if len(starter_cards) >= limit:
                    break

            if starter_cards:
                response = RecommendationMappingResponse(
                    primary_recommendations=starter_cards[: min(3, len(starter_cards))],
                    secondary_recommendations=starter_cards[min(3, len(starter_cards)) : min(6, len(starter_cards))],
                )
                fallback_used = True

        if settings.ENABLE_RECOMMENDATION_DEBUG:
            top_cards = response.primary_recommendations[:3]
            logger.info(
                "learning_hub_ranking_end",
                extra={
                    "mode": mode,
                    "strategy": strategy,
                    "fallback_used": fallback_used,
                    "results_primary": len(response.primary_recommendations),
                    "results_secondary": len(response.secondary_recommendations),
                    "top_recommendations": [
                        {
                            "content_id": c.content_id,
                            "title": c.title,
                            "score": c.score,
                            "reason": c.reason,
                            "rank_position": idx + 1,
                        }
                        for idx, c in enumerate(top_cards)
                    ],
                },
            )

        return response

