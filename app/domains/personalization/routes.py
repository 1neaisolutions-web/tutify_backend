"""Personalization domain API routes."""
from __future__ import annotations

import uuid
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.session import get_db
from app.domains.auth.dependencies import get_current_user, require_role  # type: ignore[attr-defined]
from app.domains.auth.models import User
from app.domains.personalization.enums import ProfileChangeSeverity, SectionReadinessStatus
from app.domains.personalization.models import (
    SectionInventoryConfig,
    UnlockRule,
)
from app.domains.personalization.schemas import (
    ActivityEventsRequest,
    ActivityEventsResponse,
    AdminPersonalizationOverviewResponse,
    ContentCompleteRequest,
    ContentCompleteResponse,
    PersonalizationJobOut,
    PersonalizationStateOut,
    ProfileChangeSeverityRequest,
    ProfileChangeSeverityResponse,
    ProfilePreflightRequest,
    ProfilePreflightResponse,
    ResetPersonalizationRequest,
    ResetPersonalizationResponse,
    SectionReadinessOut,
    StartPersonalizationRequest,
    StartPersonalizationResponse,
    UnlockRuleOut,
    UnlockRuleUpdateRequest,
    UnlockStateOut,
)
from app.domains.personalization.services.activity_ingestion_service import ActivityIngestionService
from app.domains.personalization.services.assignment_service import AssignmentService
from app.domains.personalization.services.inventory_expansion_worker import InventoryExpansionWorker
from app.domains.personalization.services.personalization_job_service import PersonalizationJobService
from app.domains.personalization.services.personalization_orchestrator import PersonalizationOrchestrator
from app.domains.personalization.services.personalization_profile_service import PersonalizationProfileService
from app.domains.personalization.services.profile_change_evaluator import ProfileChangeEvaluator
from app.domains.personalization.services.section_readiness_service import SectionReadinessService
from app.domains.personalization.services.slate_service import SlateService
from app.domains.personalization.services.unlock_service import UnlockService

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/personalization", tags=["personalization"])
admin_router = APIRouter(prefix="/api/v1/admin", tags=["admin-personalization"])


# ---------------------------------------------------------------------------
# Personalization State
# ---------------------------------------------------------------------------

@router.get("/state", response_model=PersonalizationStateOut)
def get_personalization_state(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the current personalization state for the authenticated user."""
    profile_svc = PersonalizationProfileService(db)
    readiness_svc = SectionReadinessService(db)

    profile = profile_svc.get(current_user.id)
    if not profile:
        return PersonalizationStateOut(
            user_id=current_user.id,
            status="no_profile",
            personalization_version=0,
            profile_completeness=0.0,
            section_readiness=[],
            message="No personalization profile yet. Complete your teaching profile to get started.",
        )

    readiness_rows = readiness_svc.get_current_all(current_user.id, profile.personalization_version)
    readiness_out = [
        SectionReadinessOut(
            section=r.section,
            status=r.status,
            visible_count_target=r.visible_count_target,
            visible_count_actual=r.visible_count_actual,
            last_ready_at=r.last_ready_at,
            failure_count=r.failure_count,
        )
        for r in readiness_rows
    ]

    return PersonalizationStateOut(
        user_id=current_user.id,
        status=profile.status,
        personalization_version=profile.personalization_version,
        profile_completeness=profile.profile_completeness,
        personalization_started_at=profile.personalization_started_at,
        last_recomputed_at=profile.last_recomputed_at,
        last_reset_at=profile.last_reset_at,
        section_readiness=readiness_out,
    )


@router.post("/start", response_model=StartPersonalizationResponse)
def start_personalization(
    request: StartPersonalizationRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Trigger personalization for the current user.
    Idempotent: safe to call multiple times; only runs if not already initialized.
    """
    profile_svc = PersonalizationProfileService(db)
    profile = profile_svc.get(current_user.id)

    if profile and profile.personalization_started_at:
        return StartPersonalizationResponse(
            status="already_started",
            personalization_version=profile.personalization_version,
            message="Personalization is already active.",
        )

    # Pull profile snapshot from teacher profile context
    profile_snapshot = _build_profile_snapshot(current_user.id, db)

    def _run():
        try:
            orch = PersonalizationOrchestrator(db)
            orch.start_personalization(
                current_user.id,
                profile_snapshot,
                profile_completeness=profile_snapshot.get("completeness", 100.0),
                trigger=request.trigger or "user_request",
            )
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.error("personalization.start_background_failed", extra={"user_id": str(current_user.id), "error": str(exc)})

    background_tasks.add_task(_run)

    new_profile = profile_svc.get_or_create(current_user.id)
    db.commit()

    return StartPersonalizationResponse(
        status="initializing",
        personalization_version=new_profile.personalization_version,
        message="Personalization is being prepared. Check /state for progress.",
    )


@router.post("/reset", response_model=ResetPersonalizationResponse)
def reset_personalization(
    request: ResetPersonalizationRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Reset personalization. Requires confirmed=true. Archives old version, creates new."""
    if not request.confirmed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset must be explicitly confirmed. Set confirmed=true.",
        )

    profile_svc = PersonalizationProfileService(db)
    profile = profile_svc.get(current_user.id)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No personalization profile found.")

    # Test reset: clear usage signals and stale generation jobs so growth onboarding
    # can be replayed deterministically for runtime verification.
    #
    # IMPORTANT: This is gated by `request.reason` starting with "test" to avoid
    # harming production users.
    if request.reason and str(request.reason).lower().startswith("test"):
        try:
            from app.domains.personalization.models import UserActivityEvent
            from app.domains.content_factory.models import ContentGenerationJob

            db.query(UserActivityEvent).filter(UserActivityEvent.user_id == current_user.id).delete(
                synchronize_session=False
            )
            db.query(ContentGenerationJob).filter(
                ContentGenerationJob.requested_by_user_id == current_user.id,
                ContentGenerationJob.status.in_(["pending", "running", "publishing"]),
            ).delete(synchronize_session=False)
            db.commit()
        except Exception:
            db.rollback()

    profile_snapshot = _build_profile_snapshot(current_user.id, db)

    def _run():
        try:
            orch = PersonalizationOrchestrator(db)
            orch.reset(
                current_user.id,
                profile_snapshot,
                profile_completeness=profile_snapshot.get("completeness", 100.0),
                trigger="user_reset",
            )
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.error("personalization.reset_background_failed", extra={"user_id": str(current_user.id), "error": str(exc)})

    background_tasks.add_task(_run)

    return ResetPersonalizationResponse(
        status="reset_initiated",
        new_version=profile.personalization_version + 1,
        message="Your personalization is being regenerated. This may take a moment.",
    )


@router.get("/jobs", response_model=list[PersonalizationJobOut])
def get_personalization_jobs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job_svc = PersonalizationJobService(db)
    return job_svc.get_jobs(current_user.id)


@router.get("/profile-change-severity", response_model=ProfileChangeSeverityResponse)
def get_profile_change_severity(
    current_profile: dict[str, Any] = None,
    proposed_profile: dict[str, Any] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Evaluate the severity of a profile change before saving.
    POST variant below handles the body properly.
    """
    raise HTTPException(status_code=405, detail="Use POST /profile-change-severity")


@router.post("/profile-change-severity", response_model=ProfileChangeSeverityResponse)
def evaluate_profile_change_severity(
    request: ProfileChangeSeverityRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    evaluator = ProfileChangeEvaluator()
    severity, changed_fields = evaluator.evaluate(request.current_profile, request.proposed_profile)
    message = evaluator.severity_message(severity, changed_fields)
    return ProfileChangeSeverityResponse(
        severity=severity,
        changed_fields=changed_fields,
        message=message,
    )


@router.post("/preflight", response_model=ProfilePreflightResponse)
def preflight_profile_change(
    request: ProfilePreflightRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Read-only impact assessment for a proposed teaching-context change.
    Fetches the user's current DB snapshot, merges the proposed_context on top,
    and returns severity + user-facing copy.  No DB writes, no jobs enqueued.
    """
    from app.domains.personalization.services.personalization_sync_service import (
        build_full_snapshot,
        plan_sync_full,
    )

    # Current state from DB
    current_snapshot = build_full_snapshot(db, current_user.id)

    # Build proposed snapshot by overlaying proposed_context onto current snapshot.
    # Lists (subjects, professional_goals) are replaced wholesale when present.
    proposed_snapshot = dict(current_snapshot)
    for key, val in request.proposed_context.items():
        proposed_snapshot[key] = val

    operation, severity_str, changed_fields, message = plan_sync_full(
        db, current_user.id, current_snapshot, proposed_snapshot
    )

    # Build user-facing copy
    requires_confirmation = severity_str == ProfileChangeSeverity.MAJOR_RESET.value
    if requires_confirmation:
        user_display_title = "This change resets your personalization"
        user_display_body = (
            "Changing "
            + ", ".join(f.replace("_", " ") for f in changed_fields)
            + " will rebuild your entire recommendation set. "
            "Your completed items and progress are preserved, but your current course lineup will be replaced."
        )
    elif severity_str == ProfileChangeSeverity.MINOR_RECOMPUTE.value:
        user_display_title = "Recommendations will be updated"
        user_display_body = (
            "Your recommendations will be refreshed to reflect the updated "
            + ", ".join(f.replace("_", " ") for f in changed_fields)
            + "."
        )
    else:
        user_display_title = ""
        user_display_body = ""

    return ProfilePreflightResponse(
        severity=severity_str,
        operation=operation,
        changed_fields=changed_fields,
        message=message,
        user_display_title=user_display_title,
        user_display_body=user_display_body,
        requires_confirmation=requires_confirmation,
    )


# ---------------------------------------------------------------------------
# Unlock state
# ---------------------------------------------------------------------------

@router.get("/unlocks/state", response_model=list[UnlockStateOut])
def get_unlock_state(
    section: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    unlock_svc = UnlockService(db)
    states = unlock_svc.get_states(current_user.id, section)
    return [
        UnlockStateOut(
            assignment_id=s.assignment_id,
            section=s.section,
            locked=s.locked,
            bucket=s.bucket,
            unlocked_at=s.unlocked_at,
            unlock_rule_id=s.unlock_rule_id,
        )
        for s in states
    ]


# ---------------------------------------------------------------------------
# Activity events
# ---------------------------------------------------------------------------

activity_router = APIRouter(prefix="/api/v1/activity", tags=["activity"])


@activity_router.post("/events", response_model=ActivityEventsResponse)
def ingest_activity_events(
    request: ActivityEventsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ingestion_svc = ActivityIngestionService(db)
    raw_events = [e.model_dump() for e in request.events]
    accepted, skipped = ingestion_svc.ingest(current_user.id, raw_events)
    db.commit()
    return ActivityEventsResponse(accepted=accepted, duplicate_skipped=skipped)


# ---------------------------------------------------------------------------
# Content completion
# ---------------------------------------------------------------------------

content_router = APIRouter(prefix="/api/v1/content", tags=["content-completion"])


@content_router.post("/{content_id}/complete", response_model=ContentCompleteResponse)
def complete_content(
    content_id: str,
    request: ContentCompleteRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Record content completion, evaluate unlocks, return newly unlocked items."""
    profile_svc = PersonalizationProfileService(db)
    profile = profile_svc.get(current_user.id)

    if not profile:
        return ContentCompleteResponse(
            status="recorded",
            newly_unlocked=[],
            message="Completion recorded. No personalization profile.",
        )

    assignment_svc = AssignmentService(db)
    assignment = None
    if request.assignment_id:
        assignment = assignment_svc.get_by_id(request.assignment_id, current_user.id)

    if assignment is None:
        assignment = assignment_svc.find_by_content_id(
            current_user.id, content_id, profile.personalization_version
        )

    newly_unlocked_ids: list[uuid.UUID] = []

    if assignment:
        assignment_svc.mark_completed(assignment)
        section = assignment.section

        # Ingest a completion event for unlock evaluation
        activity_svc = ActivityIngestionService(db)
        activity_svc.ingest(
            current_user.id,
            [{
                "client_event_id": f"complete_{content_id}_{str(assignment.id)[:8]}",
                "event_type": "content_completed",
                "section": section,
                "content_id": content_id,
                "content_type": assignment.content_type,
                "assignment_id": str(assignment.id),
            }],
        )

        # Evaluate unlocks
        unlock_svc = UnlockService(db)
        newly_unlocked_ids = unlock_svc.evaluate_unlocks(
            current_user.id, section, profile.personalization_version, trigger_event_id=assignment.id
        )

        # Progression guarantee: promote locked -> visible and reserve -> locked.
        assignment_svc.rebalance_after_completion(
            current_user.id,
            section,
            profile.personalization_version,
        )

        # Rebuild slate in background if unlocks happened
        if newly_unlocked_ids:
            def _rebuild():
                try:
                    slate_svc = SlateService(db)
                    slate_svc.build_slate(profile)
                    db.commit()
                except Exception as exc:
                    db.rollback()
                    logger.error("personalization.slate_rebuild_failed", extra={"error": str(exc)})
            background_tasks.add_task(_rebuild)

        # Proactive refill trigger if inventory is getting thin.
        if assignment_svc.needs_refill(current_user.id, section, profile.personalization_version):
            def _refill():
                try:
                    snapshot = _build_profile_snapshot(current_user.id, db)
                    orch = PersonalizationOrchestrator(db)
                    orch.recompute(current_user.id, snapshot, trigger="auto_refill_after_completion")
                    db.commit()
                except Exception as exc:
                    db.rollback()
                    logger.error("personalization.inventory_refill_failed", extra={"error": str(exc)})
            background_tasks.add_task(_refill)
        # Always run inventory expansion after completion as a proactive top-up.
        background_tasks.add_task(
            InventoryExpansionWorker.run_in_background,
            current_user.id,
            "after_completion",
        )

    db.commit()

    return ContentCompleteResponse(
        assignment_id=assignment.id if assignment else None,
        status="completed",
        newly_unlocked=newly_unlocked_ids,
        message="Completion recorded." + (f" {len(newly_unlocked_ids)} new items unlocked." if newly_unlocked_ids else ""),
    )


# ---------------------------------------------------------------------------
# Admin routes
# ---------------------------------------------------------------------------

@admin_router.get("/personalization/overview", response_model=AdminPersonalizationOverviewResponse)
def get_personalization_overview(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.domains.personalization.models import (
        PersonalizationJob,
        SectionReadiness,
        UserPersonalizationProfile,
    )
    from datetime import timedelta
    from sqlalchemy import func

    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)

    total = db.query(UserPersonalizationProfile).count()
    status_counts = dict(
        db.query(UserPersonalizationProfile.status, func.count(UserPersonalizationProfile.id))
        .group_by(UserPersonalizationProfile.status)
        .all()
    )

    # Section readiness heatmap (latest version per user)
    sr_rows = db.query(SectionReadiness).all()
    heatmap: dict[str, dict[str, int]] = {}
    for row in sr_rows:
        section = row.section
        s = row.status
        if section not in heatmap:
            heatmap[section] = {}
        heatmap[section][s] = heatmap[section].get(s, 0) + 1

    # Jobs last 24h
    cutoff = now - __import__("datetime").timedelta(hours=24)
    job_rows = (
        db.query(PersonalizationJob.status, func.count(PersonalizationJob.id))
        .filter(PersonalizationJob.created_at >= cutoff)
        .group_by(PersonalizationJob.status)
        .all()
    )
    jobs_24h: dict[str, int] = {r[0]: r[1] for r in job_rows}
    jobs_24h["total"] = sum(jobs_24h.values())

    # Recent orchestration errors: last 10 failed PersonalizationJobs
    failed_jobs = (
        db.query(PersonalizationJob)
        .filter(PersonalizationJob.status == "failed")
        .order_by(PersonalizationJob.updated_at.desc())
        .limit(10)
        .all()
    )
    recent_orchestration_errors = [
        {
            "user_id": str(job.user_id),
            "reason": job.error_message or "unknown",
            "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        }
        for job in failed_jobs
    ]

    # Banner trigger stats: active (personalization_started_at set) vs cold
    active_count = (
        db.query(UserPersonalizationProfile)
        .filter(UserPersonalizationProfile.personalization_started_at.isnot(None))
        .count()
    )
    cold_count = (
        db.query(UserPersonalizationProfile)
        .filter(UserPersonalizationProfile.personalization_started_at.is_(None))
        .count()
    )
    banner_trigger_stats = {"active": active_count, "cold": cold_count}

    return AdminPersonalizationOverviewResponse(
        total_personalized_users=total,
        users_by_status=status_counts,
        section_readiness_heatmap=heatmap,
        jobs_last_24h=jobs_24h,
        recent_orchestration_errors=recent_orchestration_errors,
        banner_trigger_stats=banner_trigger_stats,
    )


@admin_router.get("/personalization/users/{user_id}/orchestration")
def get_user_orchestration_status(
    user_id: uuid.UUID,
    current_user: User = Depends(require_role("super_admin")),
    db: Session = Depends(get_db),
):
    """Return the full compute_bootstrap_status() payload for any user, augmented with admin metadata."""
    from app.domains.learning_hub.bootstrap_orchestration import compute_bootstrap_status
    correlation_id = str(uuid.uuid4())
    status = compute_bootstrap_status(db, user_id)
    blocking = status.get("blocking_sections", [])
    reasons = []
    if blocking:
        reasons.append(f"Blocking on: {', '.join(blocking)}")
    if status.get("timeout_state") not in ("none", None):
        reasons.append(f"Timeout state: {status['timeout_state']}")
    if status.get("failure_state"):
        failed = status.get("failed_sections", [])
        reasons.append(f"Failed sections: {', '.join(failed) if failed else 'unknown'}")
    logger.info(
        "admin.orchestration_status.queried",
        extra={
            "correlation_id": correlation_id,
            "admin_user_id": str(current_user.id),
            "target_user_id": str(user_id),
            "can_enter_hub": status.get("can_enter_hub"),
        }
    )
    return {
        **status,
        "user_id": str(user_id),
        "correlation_id": correlation_id,
        "reasons": reasons,
    }


@admin_router.get("/unlock-rules", response_model=list[UnlockRuleOut])
def list_unlock_rules(
    current_user: User = Depends(require_role("org_admin")),
    db: Session = Depends(get_db),
):
    rules = db.query(UnlockRule).order_by(UnlockRule.section, UnlockRule.batch_order).all()
    return [UnlockRuleOut.model_validate(r) for r in rules]


@admin_router.put("/unlock-rules/{rule_id}", response_model=UnlockRuleOut)
def update_unlock_rule(
    rule_id: str,
    request: UnlockRuleUpdateRequest,
    current_user: User = Depends(require_role("super_admin")),
    db: Session = Depends(get_db),
):
    rule = db.query(UnlockRule).filter(UnlockRule.rule_id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Unlock rule not found.")

    if request.trigger_threshold is not None:
        rule.trigger_threshold = request.trigger_threshold
    if request.unlock_count is not None:
        rule.unlock_count = request.unlock_count
    if request.enabled is not None:
        rule.enabled = request.enabled
    if request.cooldown_seconds is not None:
        rule.cooldown_seconds = request.cooldown_seconds
    if request.priority is not None:
        rule.priority = request.priority

    db.commit()
    UnlockService.invalidate_cache(rule.section)
    return UnlockRuleOut.model_validate(rule)


@admin_router.post("/personalization/stale-recompute")
def trigger_stale_recompute(
    dry_run: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Detect stale profiles and enqueue recompute jobs for them."""
    from app.domains.personalization.services.stale_detection_service import StaleDetectionService
    svc = StaleDetectionService(db)
    result = svc.trigger_stale_recompute(dry_run=dry_run)
    if not dry_run:
        db.commit()
    return result


@admin_router.post("/personalization/inventory-expand")
def trigger_inventory_expansion(
    user_id: Optional[uuid.UUID] = None,
    current_user: User = Depends(require_role("org_admin")),
    db: Session = Depends(get_db),
):
    """
    Manual/cron trigger for proactive inventory expansion.
    - If user_id is provided: expand one user.
    - Otherwise: expand active personalized users in background.
    """
    profile_svc = PersonalizationProfileService(db)
    if user_id:
        profile = profile_svc.get(user_id)
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found.")
        InventoryExpansionWorker.run_in_background(user_id, trigger="admin_manual")
        return {"status": "started", "scope": "single_user", "user_id": str(user_id)}

    from app.domains.personalization.models import UserPersonalizationProfile
    users = (
        db.query(UserPersonalizationProfile.user_id)
        .filter(UserPersonalizationProfile.personalization_started_at.isnot(None))
        .limit(200)
        .all()
    )
    for (uid,) in users:
        InventoryExpansionWorker.run_in_background(uid, trigger="admin_cron")
    return {"status": "started", "scope": "batch", "users_queued": len(users)}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_profile_snapshot(user_id: uuid.UUID, db: Session) -> dict[str, Any]:
    """Pull teacher profile context + teacher identity into a snapshot dict."""
    try:
        from app.domains.personalization.services.personalization_sync_service import build_full_snapshot

        return build_full_snapshot(db, user_id)
    except Exception as exc:
        logger.warning("personalization.profile_snapshot_failed", extra={"user_id": str(user_id), "error": str(exc)})
        return {"completeness": 0.0}
