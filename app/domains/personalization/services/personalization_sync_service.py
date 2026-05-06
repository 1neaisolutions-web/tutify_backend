"""
Bridge profile / teacher-identity mutations to personalization recompute or reset.

Single entry point for enqueueing work after teaching context or identity changes.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Optional

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.domains.auth.models import TeacherProfileContext
from app.domains.personalization.enums import ProfileChangeSeverity
from app.domains.personalization.services.personalization_orchestrator import PersonalizationOrchestrator
from app.domains.personalization.services.personalization_profile_service import PersonalizationProfileService
from app.domains.personalization.services.profile_change_evaluator import ProfileChangeEvaluator
from app.domains.teacher_identity.models import (
    TeacherAchievement,
    TeacherCareerDocument,
    TeacherCertification,
    TeacherEducation,
    TeacherExperience,
)

logger = get_logger(__name__)


def _stable_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, default=str)


def build_full_snapshot(db: Session, user_id: uuid.UUID) -> dict[str, Any]:
    """
    Teaching context + compact teacher identity fingerprint for personalization
    and ProfileChangeEvaluator.
    """
    ctx = db.query(TeacherProfileContext).filter(TeacherProfileContext.user_id == user_id).first()
    out: dict[str, Any] = {
        "country": None,
        "region": None,
        "school_type": None,
        "grade_band": None,
        "subjects": [],
        "language_preference": None,
        "years_experience": None,
        "professional_goals": [],
        "curriculum_framework": None,
        "city": None,
        "postal_code": None,
        "school_name": None,
        "completeness": 0.0,
        "identity_fingerprint": "",
    }
    if ctx:
        out.update(
            {
                "country": ctx.country,
                "region": ctx.region,
                "school_type": ctx.school_type,
                "grade_band": ctx.grade_band,
                "subjects": list(ctx.subjects or []),
                "language_preference": ctx.language_preference,
                "years_experience": ctx.years_experience,
                "professional_goals": list(ctx.professional_goals or []),
                "curriculum_framework": ctx.curriculum_framework,
                "city": ctx.city,
                "postal_code": ctx.postal_code,
                "school_name": ctx.school_name,
                "completeness": 100.0,
            }
        )

    id_parts: list[str] = []
    for row in (
        db.query(TeacherCertification)
        .filter(TeacherCertification.user_id == user_id)
        .order_by(TeacherCertification.id)
        .all()
    ):
        id_parts.append(
            f"c:{row.id}:{row.name}:{row.issuer}:{row.issue_date}:{row.expiry_date}"
        )
    for row in (
        db.query(TeacherExperience)
        .filter(TeacherExperience.user_id == user_id)
        .order_by(TeacherExperience.id)
        .all()
    ):
        id_parts.append(
            f"e:{row.id}:{row.institution_name}:{row.role_title}:{row.subject_area}:{row.start_date}"
        )
    for row in (
        db.query(TeacherEducation)
        .filter(TeacherEducation.user_id == user_id)
        .order_by(TeacherEducation.id)
        .all()
    ):
        id_parts.append(f"ed:{row.id}:{row.institution_name}:{row.degree}:{row.field_of_study}")
    for row in (
        db.query(TeacherAchievement)
        .filter(TeacherAchievement.user_id == user_id)
        .order_by(TeacherAchievement.id)
        .all()
    ):
        id_parts.append(f"a:{row.id}:{row.title}:{row.organization}:{row.date}")
    for row in (
        db.query(TeacherCareerDocument)
        .filter(TeacherCareerDocument.user_id == user_id)
        .order_by(TeacherCareerDocument.id)
        .all()
    ):
        id_parts.append(f"doc:{row.id}:{row.document_type}:{row.file_name}:{row.status}")

    raw_fp = "|".join(id_parts)
    out["identity_fingerprint"] = hashlib.sha256(raw_fp.encode("utf-8")).hexdigest() if raw_fp else ""
    return out


def _snapshots_equal(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return _stable_json(a) == _stable_json(b)


def _run_personalization_job(
    user_id: uuid.UUID,
    old_snapshot: dict[str, Any],
    new_snapshot: dict[str, Any],
    trigger: str,
    correlation_id: str,
    operation: str,
) -> None:
    bg_db = SessionLocal()
    try:
        profile_svc = PersonalizationProfileService(bg_db)
        profile = profile_svc.get(user_id)
        orch = PersonalizationOrchestrator(bg_db)

        if operation == "start":
            completeness = float(new_snapshot.get("completeness") or 0.0)
            orch.start_personalization(
                user_id,
                new_snapshot,
                profile_completeness=completeness,
                trigger=trigger,
            )
            bg_db.commit()
            logger.info(
                "personalization.sync.start_complete",
                extra={"user_id": str(user_id), "correlation_id": correlation_id, "trigger": trigger},
            )
            return

        if not profile or not profile.personalization_started_at:
            completeness = float(new_snapshot.get("completeness") or 0.0)
            orch.start_personalization(
                user_id,
                new_snapshot,
                profile_completeness=max(completeness, 1.0),
                trigger=f"{trigger}_cold_start",
            )
            bg_db.commit()
            logger.info(
                "personalization.sync.cold_start_complete",
                extra={"user_id": str(user_id), "correlation_id": correlation_id, "trigger": trigger},
            )
            return

        if operation == "reset":
            orch.reset(
                user_id,
                new_snapshot,
                profile_completeness=float(new_snapshot.get("completeness") or 100.0),
                trigger=trigger,
            )
            bg_db.commit()
            logger.info(
                "personalization.sync.reset_complete",
                extra={
                    "user_id": str(user_id),
                    "correlation_id": correlation_id,
                    "version": profile.personalization_version,
                    "trigger": trigger,
                },
            )
            return

        if operation == "recompute":
            orch.recompute(user_id, new_snapshot, trigger=trigger)
            bg_db.commit()
            logger.info(
                "personalization.sync.recompute_complete",
                extra={"user_id": str(user_id), "correlation_id": correlation_id, "trigger": trigger},
            )
            return

        logger.warning(
            "personalization.sync.unknown_operation",
            extra={"operation": operation, "user_id": str(user_id), "correlation_id": correlation_id},
        )
    except Exception as exc:
        bg_db.rollback()
        logger.error(
            "personalization.sync.job_failed",
            extra={"user_id": str(user_id), "correlation_id": correlation_id, "error": str(exc)},
        )
    finally:
        bg_db.close()


def plan_sync(
    db: Session,
    user_id: uuid.UUID,
    old_snapshot: dict[str, Any],
    new_snapshot: dict[str, Any],
) -> tuple[str, str]:
    """
    Returns (operation, severity_reason) where operation is recompute | reset | start | noop.
    """
    operation, severity_str, _changed, _msg = plan_sync_full(db, user_id, old_snapshot, new_snapshot)
    return operation, severity_str


def plan_sync_full(
    db: Session,
    user_id: uuid.UUID,
    old_snapshot: dict[str, Any],
    new_snapshot: dict[str, Any],
) -> tuple[str, str, list[str], str]:
    """
    Returns (operation, severity_str, changed_fields, message).
    operation: recompute | reset | start | noop
    """
    if _snapshots_equal(old_snapshot, new_snapshot):
        return "noop", "none", [], "No personalization changes needed."

    evaluator = ProfileChangeEvaluator()
    severity, changed_fields = evaluator.evaluate(old_snapshot, new_snapshot)
    message = evaluator.severity_message(severity, changed_fields)
    logger.info(
        "personalization.sync.evaluated",
        extra={
            "user_id": str(user_id),
            "severity": severity.value,
            "changed_fields": changed_fields,
        },
    )

    profile_svc = PersonalizationProfileService(db)
    profile = profile_svc.get(user_id)

    if not profile or not profile.personalization_started_at:
        return "start", severity.value, changed_fields, message

    if severity == ProfileChangeSeverity.MAJOR_RESET:
        return "reset", severity.value, changed_fields, message
    if severity == ProfileChangeSeverity.MINOR_RECOMPUTE:
        return "recompute", severity.value, changed_fields, message
    if severity == ProfileChangeSeverity.NONE:
        return "noop", "none", [], "No personalization changes needed."
    return "recompute", severity.value, changed_fields, message


def enqueue_sync_with_db(
    background_tasks: BackgroundTasks,
    db: Session,
    user_id: uuid.UUID,
    old_snapshot: dict[str, Any],
    new_snapshot: dict[str, Any],
    trigger: str,
    correlation_id: Optional[str] = None,
) -> dict[str, Any]:
    cid = correlation_id or str(uuid.uuid4())
    operation, severity_str, changed_fields, message = plan_sync_full(
        db, user_id, old_snapshot, new_snapshot
    )

    profile_svc = PersonalizationProfileService(db)
    profile = profile_svc.get(user_id)
    version = profile.personalization_version if profile else 0
    last_rec = profile.last_recomputed_at.isoformat() if profile and profile.last_recomputed_at else None

    if operation == "noop":
        logger.info(
            "personalization.sync.noop",
            extra={"user_id": str(user_id), "correlation_id": cid, "trigger": trigger},
        )
        return {
            "status": "noop",
            "operation": "noop",
            "severity": "none",
            "changed_fields": [],
            "message": "No personalization changes needed.",
            "personalization_version": version,
            "last_recomputed_at": last_rec,
            "correlation_id": cid,
        }

    logger.info(
        "personalization.sync.enqueued",
        extra={
            "user_id": str(user_id),
            "correlation_id": cid,
            "trigger": trigger,
            "operation": operation,
            "severity": severity_str,
            "changed_fields": changed_fields,
        },
    )

    background_tasks.add_task(
        _run_personalization_job,
        user_id,
        old_snapshot,
        new_snapshot,
        trigger,
        cid,
        operation,
    )

    return {
        "status": "queued",
        "operation": operation,
        "severity": severity_str,
        "changed_fields": changed_fields,
        "message": message,
        "personalization_version": version,
        "last_recomputed_at": last_rec,
        "correlation_id": cid,
    }
