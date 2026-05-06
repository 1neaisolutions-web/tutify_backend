"""
Learning Hub bootstrap / orchestration — single source of truth for loader progress,
stages, MVHR (minimum viable hub readiness), and anti-stuck transitions.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.domains.auth.models import TeacherProfileContext
from app.domains.content_factory.models import ContentGenerationJob
from app.domains.personalization.models import PersonalizationJob, UserActivityEvent
from app.domains.personalization.services.assignment_service import AssignmentService
from app.domains.personalization.services.personalization_profile_service import PersonalizationProfileService
from app.domains.personalization.services.slate_service import SlateService

# Minimum viable inventory thresholds for *entry* (test + production-friendly MVHR).
# The full-page loader should not block until large inventory targets are met; it
# should transition when the hub is usable (and then continue preparing more content).
MICRO_VISIBLE = 1
MICRO_LOCKED = 1
TUTOR_VISIBLE = 1
TUTOR_LOCKED = 1
RESEARCH_VISIBLE = 1
SPECIALIST_VISIBLE = 1
GROWTH_VISIBLE = 1
GROWTH_LOCKED = 1
REQUIRED_SIGNAL_COUNT = 5

# Hard timeout hint (do not force-enter hub; show recovery state instead).
HARD_TIMEOUT_AFTER_SECONDS = 60.0
# UX: "taking longer than expected"
TAKING_LONG_AFTER_SECONDS = 45.0
# Hard hint: suggest refresh / support
STALLED_AFTER_SECONDS = 300.0


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc).isoformat()
    return dt.isoformat()


def _growth_readiness_from_counts(
    db: Session,
    user_id: uuid.UUID,
    _personalization_version: int,
    growth_counts: Dict[str, int],
) -> Tuple[str, Dict[str, Any]]:
    """Mirror learning_hub.routes growth_state logic (no slate required)."""
    signal_q = db.query(UserActivityEvent).filter(
        UserActivityEvent.user_id == user_id,
        UserActivityEvent.event_type.in_(["content_completed", "content_started", "card_clicked"]),
    )
    if _personalization_version and hasattr(UserActivityEvent, "personalization_version"):
        signal_q = signal_q.filter(
            UserActivityEvent.personalization_version == _personalization_version
        )
    signal_count = signal_q.count()
    generation_inflight = (
        db.query(ContentGenerationJob)
        .filter(
            ContentGenerationJob.requested_by_user_id == user_id,
            ContentGenerationJob.source.in_(["inventory_expansion", "gap_detection"]),
            ContentGenerationJob.status.in_(["pending", "running", "publishing"]),
            ContentGenerationJob.job_type == "growth_recommendations",
        )
        .count()
    )
    progress_percent = min(
        100,
        int((min(signal_count, REQUIRED_SIGNAL_COUNT) / REQUIRED_SIGNAL_COUNT) * 100),
    )
    readiness_state = "ready"
    if signal_count <= 0:
        readiness_state = "no_signal"
    elif signal_count < REQUIRED_SIGNAL_COUNT:
        readiness_state = "signal_building"
    elif generation_inflight > 0:
        readiness_state = "generating"
    elif growth_counts["visible"] < GROWTH_VISIBLE or growth_counts["locked_preview"] < GROWTH_LOCKED:
        readiness_state = "generating"

    growth_state = {
        "readiness_state": readiness_state,
        "signal_count": int(signal_count),
        "required_signal_count": REQUIRED_SIGNAL_COUNT,
        "progress_percent": progress_percent,
        "generation_status": "running" if generation_inflight > 0 else "idle",
    }
    return readiness_state, growth_state


def _failed_generation_flags(db: Session, user_id: uuid.UUID) -> Tuple[bool, List[str]]:
    """Recent failed jobs for this user (content generation)."""
    failed = (
        db.query(ContentGenerationJob)
        .filter(
            ContentGenerationJob.requested_by_user_id == user_id,
            ContentGenerationJob.status.in_(["failed", "failed_quality", "cancelled"]),
        )
        .order_by(ContentGenerationJob.updated_at.desc())
        .limit(5)
        .all()
    )
    if not failed:
        return False, []
    sections = sorted({j.job_type for j in failed if j.job_type})
    return True, sections


def _failed_personalization_jobs(db: Session, user_id: uuid.UUID) -> bool:
    row = (
        db.query(PersonalizationJob)
        .filter(PersonalizationJob.user_id == user_id, PersonalizationJob.status == "failed")
        .order_by(PersonalizationJob.updated_at.desc())
        .first()
    )
    return row is not None


def compute_truthful_progress_percent(
    *,
    ctx_complete: bool,
    profile_started: bool,
    slate_exists: bool,
    micro: Dict[str, int],
    tutorials: Dict[str, int],
    growth_counts: Dict[str, int],
    growth_readiness_state: str,
    can_enter_hub: bool,
    micro_ready: bool,
    tutorials_ready: bool,
    assembling: bool,
) -> int:
    """
    Sequential milestone bands so later stages cannot read "ahead" of inventory truth:
    15 → 25 → 25–50 (micro) → 50–70 (tutorials, after micro ready) → 70–85 (growth) → 85–99 (assemble) → 100.
    """
    if can_enter_hub:
        return 100

    pct = 5
    if ctx_complete:
        pct = max(pct, 15)
    if profile_started:
        pct = max(pct, 25)
    if slate_exists:
        pct = max(pct, 26)

    mv = min(micro.get("visible", 0), MICRO_VISIBLE)
    ml = min(micro.get("locked_preview", 0), MICRO_LOCKED)
    micro_frac = (mv / float(MICRO_VISIBLE)) * 0.55 + (ml / float(MICRO_LOCKED)) * 0.45
    pct = max(pct, int(25 + micro_frac * 25))  # 25–50
    if not micro_ready:
        return min(52, max(5, pct))

    tv = min(tutorials.get("visible", 0), TUTOR_VISIBLE)
    tl = min(tutorials.get("locked_preview", 0), TUTOR_LOCKED)
    tut_frac = (tv / float(TUTOR_VISIBLE)) * 0.55 + (tl / float(TUTOR_LOCKED)) * 0.45
    pct = max(pct, int(50 + tut_frac * 20))  # 50–70
    if not tutorials_ready:
        return min(72, max(5, pct))

    gv = min(growth_counts.get("visible", 0), GROWTH_VISIBLE)
    gl = min(growth_counts.get("locked_preview", 0), GROWTH_LOCKED)
    grs = growth_readiness_state
    if grs == "ready" and gv >= GROWTH_VISIBLE and gl >= GROWTH_LOCKED:
        growth_frac = 1.0
    elif grs == "signal_building":
        growth_frac = 0.9
    elif grs == "generating":
        growth_frac = 0.35 + 0.65 * ((gv / float(GROWTH_VISIBLE)) * 0.5 + (gl / float(GROWTH_LOCKED)) * 0.5)
    elif grs == "no_signal":
        growth_frac = 0.2
    else:
        growth_frac = 0.35
    pct = max(pct, int(70 + growth_frac * 15))  # 70–85

    if assembling:
        pct = max(pct, min(99, 88))

    return min(99, max(5, pct))


def resolve_current_stage(
    *,
    ctx_complete: bool,
    profile_started: bool,
    slate_exists: bool,
    micro_ready: bool,
    tutorials_ready: bool,
    growth_rs: str,
    growth_inventory_ready: bool,
    can_enter: bool,
    soft_unlock: bool,
) -> Tuple[str, str, str]:
    """
    Returns (current_stage, stage_message, sub_status).
    """
    if can_enter:
        return (
            "ready",
            "Your personalized learning hub is ready.",
            "Opening your hub…",
        )
    if not ctx_complete:
        return (
            "analyzing_profile",
            "Analyzing your teaching profile",
            "We are reading your subjects, grade band, and goals.",
        )
    if not profile_started:
        return (
            "building_personalization_profile",
            "Building your personalization profile",
            "Creating your adaptive learning snapshot.",
        )
    if not slate_exists:
        return (
            "building_personalization_profile",
            "Building your personalization profile",
            "Assembling your first recommendation slate.",
        )
    if not micro_ready:
        return (
            "generating_micro_courses",
            "Preparing your first classroom-ready micro-courses",
            "Generating and staging visible and locked preview items.",
        )
    if not tutorials_ready:
        return (
            "generating_tutorials",
            "Generating AI-guided tutorials",
            "Creating tutorials matched to your teaching context.",
        )
    if growth_rs in ("no_signal", "signal_building") and not growth_inventory_ready:
        if growth_rs == "signal_building":
            return (
                "generating_growth_recommendations",
                "Collecting learning signals for growth paths",
                "Professional signal-building in progress — recommendations unlock as signals mature.",
            )
        return (
            "generating_growth_recommendations",
            "Preparing growth recommendations",
            "Interact with your hub to build signals, or wait for automatic expansion.",
        )
    if growth_rs == "generating" or not growth_inventory_ready:
        return (
            "generating_growth_recommendations",
            "Generating your personalized growth recommendations",
            "Publishing paths into your hub inventory.",
        )
    if soft_unlock:
        return (
            "assembling_learning_hub",
            "Assembling your learning hub",
            "Core micro-courses are ready; opening your hub while secondary sections finish.",
        )
    return (
        "assembling_learning_hub",
        "Assembling your learning hub",
        "Finalizing section readiness and hero state.",
    )


def compute_bootstrap_status(db: Session, user_id: uuid.UUID) -> Dict[str, Any]:
    """
    Full orchestration payload for GET /learning-hub/bootstrap-status.
    """
    correlation_id = str(uuid.uuid4())
    profile_svc = PersonalizationProfileService(db)
    profile = profile_svc.get(user_id)
    ctx = db.query(TeacherProfileContext).filter(TeacherProfileContext.user_id == user_id).first()
    ctx_complete = bool(
        ctx and ctx.country and ctx.subjects and ctx.grade_band
    )

    started_at = _iso(profile.personalization_started_at) if profile else None
    updated_at = _iso(profile.updated_at) if profile else None
    last_recomputed = _iso(profile.last_recomputed_at) if profile and profile.last_recomputed_at else None

    now = _utcnow()
    if profile and profile.personalization_started_at:
        elapsed = (now - profile.personalization_started_at).total_seconds()
    else:
        elapsed = 0.0

    if not profile or not profile.personalization_started_at:
        return {
            "state": "orchestrating",
            "page_readiness_state": "hub_bootstrapping",
            "progress_percent": 10 if ctx_complete else 5,
            "current_stage": "building_personalization_profile" if ctx_complete else "analyzing_profile",
            "stage_message": (
                "Building your personalization profile"
                if ctx_complete
                else "Analyzing your teaching profile"
            ),
            "sub_status": None,
            "started_at": started_at,
            "updated_at": updated_at,
            "minimum_ready_sections_met": [],
            "blocking_sections": ["personalization_profile"] if ctx_complete else ["teacher_profile"],
            "ready_sections": [],
            "failed_sections": [],
            "can_enter_hub": False,
            "fallback_message": None,
            "timeout_state": "none",
            "failure_state": False,
            "growth_state": None,
            "elapsed_seconds": round(elapsed, 1),
            "soft_unlock_seconds": HARD_TIMEOUT_AFTER_SECONDS,
            "taking_long": elapsed >= TAKING_LONG_AFTER_SECONDS,
            "show_bootstrap_banner": False,
            "has_ready_inventory": False,
            "generation_inflight": False,
            "orchestration_session_id": None,
        }

    ver = profile.personalization_version
    assignment_svc = AssignmentService(db)
    slate_svc = SlateService(db)
    slate = slate_svc.get_current(user_id)
    slate_exists = slate is not None

    micro = assignment_svc.inventory_counts(user_id, "micro_courses", ver)
    tutorials = assignment_svc.inventory_counts(user_id, "tutorials", ver)
    research_counts = assignment_svc.inventory_counts(user_id, "research_insights", ver)
    specialist_counts = assignment_svc.inventory_counts(user_id, "specialist_tracks", ver)
    growth_counts = assignment_svc.inventory_counts(user_id, "growth_recommendations", ver)

    growth_rs, growth_state = _growth_readiness_from_counts(db, user_id, ver, growth_counts)
    micro_ready = micro["visible"] >= MICRO_VISIBLE
    tutorials_ready = tutorials["visible"] >= TUTOR_VISIBLE
    growth_inventory_ready = (
        growth_rs == "ready"
        and growth_counts["visible"] >= GROWTH_VISIBLE
    )
    growth_mvhr = growth_inventory_ready or growth_rs in {"signal_building", "no_signal", "generating"}
    research_ready = research_counts["visible"] >= RESEARCH_VISIBLE
    specialist_ready = specialist_counts["visible"] >= SPECIALIST_VISIBLE

    # Progressive minimum viable readiness:
    # enter as soon as core sections have at least one visible item.
    minimum_viable_ready = bool(micro_ready and tutorials_ready and research_ready and specialist_ready)
    hard_timeout_reached = elapsed >= HARD_TIMEOUT_AFTER_SECONDS
    # Never-stuck guarantee: force entry once timeout is reached, then continue
    # section generation progressively inside the hub.
    can_enter_hub = bool(minimum_viable_ready or hard_timeout_reached)

    gen_failed, failed_job_types = _failed_generation_flags(db, user_id)
    pers_failed = _failed_personalization_jobs(db, user_id)
    failure_state = gen_failed or pers_failed

    blocking: List[str] = []
    if not micro_ready:
        blocking.append("micro_courses")
    # Growth never blocks hub entry; it has its own staged UX.
    if not tutorials_ready and not can_enter_hub:
        blocking.append("tutorials")
    if not research_ready and not can_enter_hub:
        blocking.append("research_insights")
    if not specialist_ready and not can_enter_hub:
        blocking.append("specialist_tracks")

    ready_sections: List[str] = []
    if micro_ready:
        ready_sections.append("micro_courses")
    if tutorials_ready:
        ready_sections.append("tutorials")
    if research_ready:
        ready_sections.append("research_insights")
    if specialist_ready:
        ready_sections.append("specialist_tracks")
    if growth_inventory_ready:
        ready_sections.append("growth_recommendations")

    minimum_ready_sections_met: List[str] = []
    if micro_ready:
        minimum_ready_sections_met.append("micro_courses")
    if tutorials_ready:
        minimum_ready_sections_met.append("tutorials")
    if research_ready:
        minimum_ready_sections_met.append("research_insights")
    if specialist_ready:
        minimum_ready_sections_met.append("specialist_tracks")
    if growth_inventory_ready:
        minimum_ready_sections_met.append("growth_recommendations")
    elif growth_rs in {"signal_building", "no_signal", "generating"}:
        minimum_ready_sections_met.append("growth_recommendations_signal_building")

    assembling = not can_enter_hub and (micro_ready or tutorials_ready or research_ready or specialist_ready)

    pct = compute_truthful_progress_percent(
        ctx_complete=ctx_complete,
        profile_started=True,
        slate_exists=slate_exists,
        micro=micro,
        tutorials=tutorials,
        growth_counts=growth_counts,
        growth_readiness_state=growth_rs,
        can_enter_hub=can_enter_hub,
        micro_ready=micro_ready,
        tutorials_ready=tutorials_ready,
        assembling=assembling,
    )

    stage, msg, sub = resolve_current_stage(
        ctx_complete=ctx_complete,
        profile_started=True,
        slate_exists=slate_exists,
        micro_ready=micro_ready,
        tutorials_ready=tutorials_ready,
        growth_rs=growth_rs,
        growth_inventory_ready=growth_inventory_ready,
        can_enter=can_enter_hub,
        soft_unlock=False,
    )

    timeout_state = "none"
    fallback_message = None
    if elapsed >= STALLED_AFTER_SECONDS and not can_enter_hub:
        timeout_state = "stalled"
        fallback_message = (
            "This is taking longer than usual. You can keep waiting or refresh the page — your progress is saved."
        )
    elif hard_timeout_reached and not minimum_viable_ready:
        timeout_state = "soft_unlock"
        fallback_message = "Opening your hub now while remaining sections continue preparing in the background."
    elif elapsed >= TAKING_LONG_AFTER_SECONDS and not can_enter_hub:
        timeout_state = "taking_long"
        fallback_message = "Still working — large personalization jobs can take a minute or two."

    top_state = "ready" if can_enter_hub else "orchestrating"
    if failure_state and not can_enter_hub:
        top_state = "degraded"

    # show_bootstrap_banner: True only during active orchestration triggered by a
    # profile change/completion/reset (started within last 300 s) and hub not yet ready.
    show_bootstrap_banner = (
        not can_enter_hub
        and elapsed <= 300.0
        and profile.personalization_started_at is not None
    )

    has_ready_inventory = len(ready_sections) > 0

    # Top-level generation_inflight: any pending/running generation job for this user
    # (ContentGenerationJob is already imported at the top of this module)
    generation_inflight_count = (
        db.query(ContentGenerationJob)
        .filter(
            ContentGenerationJob.requested_by_user_id == user_id,
            ContentGenerationJob.status.in_(["pending", "running", "publishing"]),
        )
        .count()
    )
    generation_inflight = generation_inflight_count > 0

    # orchestration_session_id: stable per-run ID derived from user_id + version + started_at
    _started_iso = started_at or ""
    orchestration_session_id = (
        str(uuid.uuid5(uuid.NAMESPACE_URL, f"{user_id}:{ver}:{_started_iso}"))
        if profile and profile.personalization_started_at
        else None
    )

    from app.core.logging import get_logger as _get_logger
    _log = _get_logger(__name__)
    _log.info(
        "bootstrap_status.computed",
        extra={
            "correlation_id": correlation_id,
            "user_id": str(user_id),
            "can_enter_hub": can_enter_hub,
            "show_bootstrap_banner": show_bootstrap_banner,
            "has_ready_inventory": has_ready_inventory,
            "generation_inflight": generation_inflight,
            "orchestration_session_id": orchestration_session_id,
            "progress_percent": pct,
            "elapsed_seconds": round(elapsed, 1),
        }
    )

    return {
        "state": top_state,
        "page_readiness_state": "hub_ready" if can_enter_hub else "hub_bootstrapping",
        "progress_percent": pct,
        "current_stage": stage,
        "stage_message": msg,
        "sub_status": sub,
        "started_at": started_at,
        "updated_at": updated_at,
        "last_recomputed_at": last_recomputed,
        "minimum_ready_sections_met": ready_sections,
        "blocking_sections": blocking,
        "ready_sections": ready_sections,
        "failed_sections": failed_job_types,
        "can_enter_hub": can_enter_hub,
        "fallback_message": fallback_message,
        "timeout_state": timeout_state,
        "failure_state": failure_state,
        "growth_state": growth_state,
        "elapsed_seconds": round(elapsed, 1),
        "soft_unlock_seconds": HARD_TIMEOUT_AFTER_SECONDS,
        "taking_long": elapsed >= TAKING_LONG_AFTER_SECONDS and not can_enter_hub,
        "global_generation_stage": msg,
        "global_progress_percent": pct,
        "show_bootstrap_banner": show_bootstrap_banner,
        "has_ready_inventory": has_ready_inventory,
        "generation_inflight": generation_inflight,
        "orchestration_session_id": orchestration_session_id,
        "correlation_id": correlation_id,
    }
