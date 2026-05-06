"""
Deterministic, normalized scoring for Learning Hub recommendations.

Scores are bounded in [0, 1] per component before weights are applied.
The service is explainable and query-safe for production use.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import exp
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domains.content_registry.services.content_registry_service import ContentRegistryService
from app.domains.content_registry.models import ContentRegistryItem
from app.domains.learning_progress.enums import LearningSessionStatus
from app.domains.learning_progress.models import LearningSession
from app.domains.recommendation_analytics.models import RecommendationPerformanceSnapshot

logger = get_logger(__name__)

_CONTENT_TYPE_WEIGHT = 1.0
_CATEGORY_WEIGHT = 1.0
_RESUME_DAYS_HALF_LIFE = 7.0
_MIN_RESUME_PROGRESS = 10.0
_MIN_RESUME_DURATION_SECONDS = 120
_MIN_COMPLETION_HISTORY = 2
_MIN_ABANDONMENT_HISTORY = 3
_MIN_IMPRESSIONS = 20

_WEIGHTS = {
    "continue_learning": 3.0,
    "recency_resume": 1.2,
    "completion_affinity": 1.0,
    "engagement": 0.8,
    "goal_match": 0.8,
    "context_match": 0.7,
    "abandonment_penalty": -0.5,
}


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _timestamp_ms(value: Any) -> int:
    if not value:
        return 0
    try:
        if isinstance(value, datetime):
            return int(value.timestamp() * 1000)
        return int(datetime.fromisoformat(str(value)).replace(tzinfo=timezone.utc).timestamp() * 1000)
    except Exception:
        return 0


def _days_since(value: Any) -> float:
    ts = _timestamp_ms(value)
    if not ts:
        return 1e9
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    return max(0.0, (now_ms - ts) / 86_400_000.0)


def _flatten_values(value: Any) -> List[str]:
    out: List[str] = []
    if isinstance(value, dict):
        for v in value.values():
            out.extend(_flatten_values(v))
    elif isinstance(value, list):
        for v in value:
            out.extend(_flatten_values(v))
    elif value is not None:
        out.append(_norm(value))
    return out


@dataclass
class TeacherBehaviorProfile:
    active_sessions_by_content: Dict[str, LearningSession] = field(default_factory=dict)
    in_progress_content_ids: List[str] = field(default_factory=list)
    completed_by_type_category: Dict[Tuple[str, str], int] = field(default_factory=dict)
    started_by_type_category: Dict[Tuple[str, str], int] = field(default_factory=dict)
    content_last_seen_ms: Dict[str, int] = field(default_factory=dict)
    content_progress: Dict[str, float] = field(default_factory=dict)
    content_duration_seconds: Dict[str, int] = field(default_factory=dict)
    goals: List[str] = field(default_factory=list)
    subjects: List[str] = field(default_factory=list)
    grade_band: str = ""


class RecommendationScoringService:
    def __init__(self, db: Session):
        self.db = db

    def build_behavior_profile(
        self,
        teacher_id: UUID,
        goals: Optional[List[str]] = None,
        subjects: Optional[List[str]] = None,
        grade_band: str = "",
    ) -> TeacherBehaviorProfile:
        registry_svc = ContentRegistryService(self.db)
        registry_cache: Dict[str, Optional[ContentRegistryItem]] = {}
        sessions = (
            self.db.query(LearningSession)
            .filter(LearningSession.teacher_id == teacher_id)
            .order_by(LearningSession.updated_at.desc())
            .all()
        )
        profile = TeacherBehaviorProfile(
            goals=goals or [],
            subjects=subjects or [],
            grade_band=_norm(grade_band),
        )

        for session in sessions:
            content_id = getattr(session, "content_id", None)
            if not content_id or content_id.startswith("learning-hub:"):
                continue

            status = _norm(getattr(session, "session_status", ""))
            progress = float(getattr(session, "progress_percent", 0.0) or 0.0)
            content_type = _norm(getattr(session, "content_type", ""))
            if content_id not in registry_cache:
                registry_cache[content_id] = registry_svc.get_item_by_content_id(content_id)
            registry_item = registry_cache.get(content_id)
            category = _norm(getattr(registry_item, "category", None))
            last_seen_ms = max(
                _timestamp_ms(getattr(session, "last_event_at", None)),
                _timestamp_ms(getattr(session, "updated_at", None)),
                _timestamp_ms(getattr(session, "completed_at", None)),
                _timestamp_ms(getattr(session, "started_at", None)),
            )

            if last_seen_ms > profile.content_last_seen_ms.get(content_id, 0):
                profile.content_last_seen_ms[content_id] = last_seen_ms
                profile.content_progress[content_id] = progress
                profile.content_duration_seconds[content_id] = int(getattr(session, "duration_seconds", 0) or 0)

            if status in {LearningSessionStatus.STARTED.value, LearningSessionStatus.IN_PROGRESS.value} or (
                status != LearningSessionStatus.COMPLETED.value and progress > 0
            ):
                if content_id not in profile.active_sessions_by_content:
                    profile.active_sessions_by_content[content_id] = session
                    profile.in_progress_content_ids.append(content_id)

            type_category_key = (content_type, category)
            if status == LearningSessionStatus.COMPLETED.value:
                profile.completed_by_type_category[type_category_key] = profile.completed_by_type_category.get(type_category_key, 0) + 1
            elif status in {LearningSessionStatus.STARTED.value, LearningSessionStatus.IN_PROGRESS.value} or progress > 0:
                profile.started_by_type_category[type_category_key] = profile.started_by_type_category.get(type_category_key, 0) + 1

        return profile

    def score_item(
        self,
        item: ContentRegistryItem,
        behavior: TeacherBehaviorProfile,
        analytics_snapshot: Optional[RecommendationPerformanceSnapshot] = None,
    ) -> Dict[str, Any]:
        content_id = item.content_id
        content_type = _norm(item.content_type)
        category = _norm(item.category)
        tags = item.tags or {}
        alignment = item.alignment or {}
        active_session = behavior.active_sessions_by_content.get(content_id)

        components = {
            "continue_learning": 0.0,
            "recency_resume": 0.0,
            "completion_affinity": 0.0,
            "abandonment_penalty": 0.0,
            "engagement": 0.0,
            "goal_match": 0.0,
            "context_match": 0.0,
        }
        reason = "Suggested for you"

        if active_session:
            progress = float(getattr(active_session, "progress_percent", 0.0) or 0.0)
            status = _norm(getattr(active_session, "session_status", ""))
            if status in {LearningSessionStatus.STARTED.value, LearningSessionStatus.IN_PROGRESS.value} or progress > 0:
                components["continue_learning"] = 1.0
                reason = "Continue where you left off"

        if not active_session:
            last_seen_ms = behavior.content_last_seen_ms.get(content_id, 0)
            if last_seen_ms:
                latest = max(last_seen_ms, 0)
                progress = float(behavior.content_progress.get(content_id, 0.0) or 0.0)
                duration_seconds = int(behavior.content_duration_seconds.get(content_id, 0) or 0)
                if progress >= _MIN_RESUME_PROGRESS or duration_seconds >= _MIN_RESUME_DURATION_SECONDS:
                    days = _days_since(datetime.fromtimestamp(latest / 1000.0, tz=timezone.utc))
                    # exp(-ln(2) * days / half_life) keeps score in [0,1]
                    components["recency_resume"] = _clamp(exp(-0.69314718056 * (days / _RESUME_DAYS_HALF_LIFE)))

        started_same = sum(
            v for (t, c), v in behavior.started_by_type_category.items() if t == content_type and c == category
        )
        completed_same = sum(
            v for (t, c), v in behavior.completed_by_type_category.items() if t == content_type and c == category
        )
        completion_ratio = completed_same / max(1, started_same)
        if started_same >= _MIN_COMPLETION_HISTORY:
            components["completion_affinity"] = _clamp(completion_ratio)
            if not active_session and components["completion_affinity"] > 0.5 and reason == "Suggested for you":
                reason = "Because you completed similar content"

        if started_same >= _MIN_ABANDONMENT_HISTORY:
            components["abandonment_penalty"] = _clamp(1.0 - completion_ratio)

        if analytics_snapshot and int(getattr(analytics_snapshot, "impressions", 0) or 0) >= _MIN_IMPRESSIONS:
            ctr = _clamp(float(getattr(analytics_snapshot, "ctr", 0.0) or 0.0))
            completion_rate = _clamp(float(getattr(analytics_snapshot, "completion_rate", 0.0) or 0.0))
            # simple smoothing to avoid overreacting to thin snapshots
            components["engagement"] = _clamp((ctr * 0.55) + (completion_rate * 0.45))
            if components["engagement"] > 0.55 and reason == "Suggested for you":
                reason = "Popular and effective for teachers like you"

        if behavior.goals:
            goal_match = 0.0
            searchable = " ".join(
                [
                    content_type,
                    category,
                    _norm(item.title),
                    _norm(item.subtitle),
                    _norm(item.summary),
                    " ".join(_flatten_values(tags)),
                    " ".join(_flatten_values(alignment)),
                ]
            )
            for goal in behavior.goals:
                goal_l = _norm(goal)
                if goal_l and goal_l in searchable:
                    goal_match = 1.0
                    reason = "Matches your goals and recent activity"
                    break
            components["goal_match"] = goal_match

        context_match = 0.0
        if behavior.subjects and any(_norm(subject) and _norm(subject) in category for subject in behavior.subjects):
            context_match = 1.0
        elif behavior.grade_band and behavior.grade_band in category:
            context_match = 0.5
        components["context_match"] = _clamp(context_match)

        total_score = 0.0
        for key, weight in _WEIGHTS.items():
            if key == "abandonment_penalty":
                total_score += components[key] * weight
            else:
                total_score += components[key] * weight

        total_score = _clamp(total_score / 7.0, 0.0, 1.0)
        return {
            "content_id": content_id,
            "score": total_score,
            "reason": reason,
            "components": components,
        }

