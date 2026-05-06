"""
Learning Hub home orchestration (V1): build home payload from CTP, snapshot, ml_output, context.
Deterministic, rules-based; no LLMs. No content registry yet.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domains.auth.models import TeacherProfileContext
from app.domains.teacher_intelligence.services import (
    CTPAssemblerService,
    FeatureSnapshotService,
    MLOutputService,
    IntelligenceRefreshService,
)
from app.domains.teacher_identity.models import (
    TeacherAchievement,
    TeacherCertification,
    TeacherCareerDocument,
    TeacherEducation,
    TeacherExperience,
)
from app.domains.content_registry.services import RecommendationMappingService
from app.domains.learning_progress.services import ProgressAggregationService
from app.domains.learning_hub import schemas as hub_schemas
from app.domains.content_registry.enums import ContentType

logger = get_logger(__name__)

# Fields that count toward profile completeness (spec)
_COMPLETENESS_FIELDS = [
    "country",
    "region",
    "subjects",
    "grade_band",
    "school_type",
    "language_preference",
    "years_experience",
]

_COLD_START = "cold_start"
_WARM_START = "warm_start"
_PERSONALIZED = "personalized"


def _has_meaningful_profile_data(ctp: Dict[str, Any], profile_completeness: hub_schemas.ProfileCompleteness) -> bool:
    if not ctp:
        return False
    identity = ctp.get("identity") or {}
    environment = ctp.get("environment") or {}
    profile_fields = [
        identity.get("country"),
        identity.get("region"),
        identity.get("subjects"),
        identity.get("grade_band"),
        environment.get("school_type"),
        environment.get("language_preference"),
    ]
    populated = sum(1 for field in profile_fields if field)
    return populated >= 4 and profile_completeness.score >= 0.45


def _detect_learning_hub_mode(
    ctp: Dict[str, Any],
    snapshot: Any,
    ml_output: Any,
    profile_completeness: hub_schemas.ProfileCompleteness,
    progress_overview: Any,
) -> str:
    identity = ctp.get("identity") or {}
    environment = ctp.get("environment") or {}
    profile_ready = _has_meaningful_profile_data(ctp, profile_completeness)
    behavior_sessions = int(getattr(progress_overview, "total_sessions", 0) or 0) if progress_overview else 0
    behavior_completed = int(getattr(progress_overview, "completed_content_count", 0) or 0) if progress_overview else 0
    behavior_ready = behavior_sessions >= 4 and behavior_completed >= 1
    snapshot_ready = snapshot is not None
    ml_ready = ml_output is not None

    has_any_signal = any(
        [
            profile_ready,
            snapshot_ready,
            ml_ready,
            behavior_sessions > 0,
            bool(identity.get("subjects")),
            bool(identity.get("grade_band")),
            bool(environment.get("school_type")),
        ]
    )

    if profile_completeness.score < 0.45 and not behavior_ready and not snapshot_ready and not ml_ready:
        return _COLD_START

    if profile_ready and snapshot_ready and ml_ready and behavior_ready:
        return _PERSONALIZED

    if profile_ready or has_any_signal:
        return _WARM_START

    return _COLD_START


def _compute_profile_completeness(
    db: Session, teacher_id: UUID
) -> hub_schemas.ProfileCompleteness:
    """Score 0-1 and missing_fields from context + at least one identity record."""
    missing: List[str] = []
    ctx = None
    try:
        ctx = (
            db.query(TeacherProfileContext)
            .filter(TeacherProfileContext.user_id == teacher_id)
            .first()
        )
    except Exception:
        # Partial migrations / missing optional tables -> treat profile as incomplete.
        try:
            db.rollback()
        except Exception:
            pass
        return hub_schemas.ProfileCompleteness(
            score=0.0,
            missing_fields=list(_COMPLETENESS_FIELDS) + ["teaching_context"],
        )

    if not ctx:
        return hub_schemas.ProfileCompleteness(
            score=0.0,
            missing_fields=list(_COMPLETENESS_FIELDS) + ["teaching_context"],
        )

    if not (ctx.country and str(ctx.country).strip()):
        missing.append("country")
    if not (ctx.region and str(ctx.region).strip()):
        missing.append("region")
    if not (ctx.subjects and isinstance(ctx.subjects, list) and len(ctx.subjects) > 0):
        missing.append("subjects")
    if not (ctx.grade_band and str(ctx.grade_band).strip()):
        missing.append("grade_band")
    if not (ctx.school_type and str(ctx.school_type).strip()):
        missing.append("school_type")
    if not (ctx.language_preference and str(ctx.language_preference).strip()):
        missing.append("language_preference")
    if not (getattr(ctx, "years_experience", None) and str(ctx.years_experience or "").strip()):
        missing.append("years_experience")

    has_identity = False
    try:
        has_identity = bool(
            db.query(TeacherExperience).filter(TeacherExperience.user_id == teacher_id).first()
            or db.query(TeacherCertification).filter(TeacherCertification.user_id == teacher_id).first()
            or db.query(TeacherCareerDocument).filter(TeacherCareerDocument.user_id == teacher_id).first()
        )
    except Exception as exc:
        logger.warning(
            "learning_hub.profile_completeness.identity_check_failed teacher_id=%s error=%s",
            teacher_id, exc,
        )
        try:
            db.rollback()
        except Exception:
            pass
        has_identity = False
    if not has_identity:
        missing.append("experience_or_certification_or_document")

    total_checks = len(_COMPLETENESS_FIELDS) + 1
    score = (total_checks - len(missing)) / total_checks if total_checks else 0.0
    return hub_schemas.ProfileCompleteness(score=max(0.0, min(1.0, score)), missing_fields=missing)


def _teacher_summary_from_ctp(ctp: Dict[str, Any]) -> hub_schemas.TeacherSummary:
    """Build teacher summary from CTP dict."""
    identity = ctp.get("identity") or {}
    environment = ctp.get("environment") or {}
    subjects = identity.get("subjects") or []
    return hub_schemas.TeacherSummary(
        subjects=subjects if isinstance(subjects, list) else [],
        grade_band=str(identity.get("grade_band") or ""),
        school_type=str(environment.get("school_type") or ""),
        region=str(identity.get("region") or ""),
        years_experience=str(environment.get("years_experience") or ""),
    )


def _intelligence_from_ml_output(ml_output: Any) -> hub_schemas.IntelligenceCard:
    """Build intelligence card from ML output record."""
    results = getattr(ml_output, "results", None) or {}
    return hub_schemas.IntelligenceCard(
        cluster_id=results.get("cluster_id"),
        persona_tag=results.get("persona_tag"),
        pipeline_version=getattr(ml_output, "pipeline_version", None),
        feature_schema_version=None,
    )


def _focus_areas_and_next_actions(
    db: Session,
    teacher_id: UUID,
    has_snapshot: bool,
    has_ml_output: bool,
    profile_completeness: hub_schemas.ProfileCompleteness,
) -> tuple[List[hub_schemas.FocusArea], List[hub_schemas.NextAction]]:
    """Rules-based focus areas and next actions."""
    focus_areas: List[hub_schemas.FocusArea] = []
    next_actions: List[hub_schemas.NextAction] = []

    if has_ml_output:
        focus_areas.append(
            hub_schemas.FocusArea(
                title="Personalized learning path",
                source="ml_output",
                priority=1,
            )
            # V1: no concrete content IDs; generic title
        )

    if not has_snapshot:
        next_actions.append(
            hub_schemas.NextAction(
                action_type="generate_feature_snapshot",
                label="Generate your learning profile",
                reason="Your feature snapshot is missing. Generate it to get personalized recommendations.",
            )
        )

    if profile_completeness.score < 1.0 and profile_completeness.missing_fields:
        if "teaching_context" in profile_completeness.missing_fields or any(
            f in profile_completeness.missing_fields for f in _COMPLETENESS_FIELDS
        ):
            next_actions.append(
                hub_schemas.NextAction(
                    action_type="complete_profile",
                    label="Complete your teaching context",
                    reason="Complete your profile for better recommendations.",
                )
            )
        if "experience_or_certification_or_document" in profile_completeness.missing_fields:
            next_actions.append(
                hub_schemas.NextAction(
                    action_type="add_career_data",
                    label="Add experience, certifications, or documents",
                    reason="Add career data to enrich your learning profile.",
                )
            )

    if not next_actions and has_snapshot and has_ml_output:
        next_actions.append(
            hub_schemas.NextAction(
                action_type="explore_recommendations",
                label="Explore recommendations",
                reason="Your profile is set up. Explore your personalized focus areas.",
            )
        )

    return focus_areas, next_actions


class LearningHubHomeService:
    """Build V1 Learning Hub home response from available intelligence."""

    def __init__(self, db: Session):
        self.db = db

    def get_home(self, teacher_id: UUID) -> hub_schemas.LearningHubHomeResponse:
        """Build deterministic home payload for the teacher. Ensures fresh intelligence first."""
        refresh_service = IntelligenceRefreshService(self.db)
        try:
            refresh_service.ensure_fresh_teacher_intelligence(teacher_id)
        except Exception:  # pragma: no cover - defensive
            # If intelligence tables aren’t present (e.g., partial migrations),
            # degrade gracefully to cold-start mode with seeded recommendations.
            try:
                self.db.rollback()
            except Exception:
                pass

        assembler = CTPAssemblerService(self.db)
        snapshot_svc = FeatureSnapshotService(self.db)
        output_svc = MLOutputService(self.db)
        progress_svc = ProgressAggregationService(self.db)

        ctp = {}
        try:
            ctp = assembler.assemble(teacher_id) or {}
        except Exception as exc:  # pragma: no cover - defensive
            # If optional CTP sources/tables are missing, fall back to cold-start mode.
            # We keep home deterministic and non-empty via seeded recommendations.
            ctp = {}
            try:
                self.db.rollback()
            except Exception:
                pass

        snapshot = None
        try:
            snapshot = snapshot_svc.get_latest(teacher_id)
        except Exception:  # pragma: no cover - defensive
            snapshot = None
            try:
                self.db.rollback()
            except Exception:
                pass

        ml_output = None
        try:
            ml_output = output_svc.get_latest(teacher_id, pipeline_name="pipeline2")
        except Exception:  # pragma: no cover - defensive
            ml_output = None
            try:
                self.db.rollback()
            except Exception:
                pass

        profile_completeness = _compute_profile_completeness(self.db, teacher_id)
        teacher_summary = _teacher_summary_from_ctp(ctp)

        if ml_output:
            intelligence = _intelligence_from_ml_output(ml_output)
            if snapshot:
                intelligence.feature_schema_version = getattr(
                    snapshot, "feature_schema_version", None
                )
        else:
            intelligence = hub_schemas.IntelligenceCard()

        focus_areas, next_actions = _focus_areas_and_next_actions(
            self.db,
            teacher_id,
            has_snapshot=snapshot is not None,
            has_ml_output=ml_output is not None,
            profile_completeness=profile_completeness,
        )

        mapping_svc = RecommendationMappingService(self.db)
        locale = "en"
        if ctp:
            identity = ctp.get("identity") or {}
            locale = str(identity.get("language_preference") or identity.get("locale") or "en").strip() or "en"
        progress_overview = None
        try:
            progress_overview = progress_svc.get_progress_overview(teacher_id)
        except Exception:  # pragma: no cover - defensive
            progress_overview = None
            try:
                self.db.rollback()
            except Exception:
                pass
        mode = _detect_learning_hub_mode(
            ctp=ctp,
            snapshot=snapshot,
            ml_output=ml_output,
            profile_completeness=profile_completeness,
            progress_overview=progress_overview,
        )
        rec_response = mapping_svc.get_learning_hub_recommendations(
            teacher_id=teacher_id,
            locale=locale,
            limit=6,
            mode=mode,
        )

        # Ensure home payload always has actionable growth recommendation metadata.
        # If profile/ML signals are sparse, derive focus_areas + next_actions from ranked cards
        # so frontend can render AI growth recommendations without falling back to dummy-only UI.
        if not focus_areas:
            ranked_cards = [
                c
                for c in ((rec_response.primary_recommendations or []) + (rec_response.secondary_recommendations or []))
                if str(getattr(c, "content_type", "") or "").strip().lower()
                in {ContentType.LEARNING_PATH.value, ContentType.PATH_MODULE.value}
            ]
            focus_areas = [
                hub_schemas.FocusArea(
                    title=(card.title or "Recommended skill"),
                    source="ml_output",
                    priority=idx + 1,
                )
                for idx, card in enumerate(ranked_cards[:3])
                if getattr(card, "title", None)
            ]

        if not next_actions:
            ranked_cards = [
                c
                for c in ((rec_response.primary_recommendations or []) + (rec_response.secondary_recommendations or []))
                if str(getattr(c, "content_type", "") or "").strip().lower()
                in {ContentType.LEARNING_PATH.value, ContentType.PATH_MODULE.value}
            ]
            next_actions = [
                hub_schemas.NextAction(
                    action_type="explore_recommendations",
                    label=(card.title or "Recommended skill"),
                    reason=(card.reason or "Recommended based on your profile and learning activity."),
                )
                for card in ranked_cards[:3]
                if getattr(card, "title", None)
            ]

        return hub_schemas.LearningHubHomeResponse(
            teacher_id=teacher_id,
            generated_at=datetime.now(timezone.utc),
            profile_completeness=profile_completeness,
            teacher_summary=teacher_summary,
            intelligence=intelligence,
            focus_areas=focus_areas,
            next_actions=next_actions,
            primary_recommendations=rec_response.primary_recommendations,
            secondary_recommendations=rec_response.secondary_recommendations,
            progress_overview=progress_overview.model_dump(),
            mode=mode,
        )


# ---------------------------------------------------------------------------
# Profile completion status — used by the ProfileCompletionGate UI
# ---------------------------------------------------------------------------

def _count_identity_records(db: Session, teacher_id: UUID, model_class: Any) -> int:
    """Safe count of identity records; returns 0 on any DB error."""
    try:
        return db.query(model_class).filter(model_class.user_id == teacher_id).count()
    except Exception as exc:
        logger.warning(
            "learning_hub.profile_completion_status.count_failed model=%s teacher_id=%s error=%s",
            model_class.__name__, teacher_id, exc,
        )
        try:
            db.rollback()
        except Exception:
            pass
        return 0


def get_profile_completion_status(
    db: Session, teacher_id: UUID
) -> hub_schemas.ProfileCompletionStatusResponse:
    """
    Return a structured profile completion breakdown for the Learning Hub gate UI.

    Covers both teaching context (country, region, subjects, grade_band, school_type,
    language_preference, years_experience) and identity sections (experience, education,
    certifications, skills/achievements, career documents).
    """
    # Re-use existing completeness computation for the score.
    completeness = _compute_profile_completeness(db, teacher_id)
    missing = set(completeness.missing_fields)

    ctx = None
    try:
        ctx = (
            db.query(TeacherProfileContext)
            .filter(TeacherProfileContext.user_id == teacher_id)
            .first()
        )
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass

    # ---------- Teaching context fields ----------
    context_fields = [
        hub_schemas.ProfileSectionStatus(
            key="country",
            label="Country",
            complete="country" not in missing,
            route="/profile",
            description="Where you teach",
        ),
        hub_schemas.ProfileSectionStatus(
            key="region",
            label="Region / State",
            complete="region" not in missing,
            route="/profile",
            description="Your teaching region",
        ),
        hub_schemas.ProfileSectionStatus(
            key="subjects",
            label="Subjects",
            complete="subjects" not in missing,
            route="/profile",
            description="Subjects you teach",
        ),
        hub_schemas.ProfileSectionStatus(
            key="grade_band",
            label="Grade Band",
            complete="grade_band" not in missing,
            route="/profile",
            description="Grade levels you teach",
        ),
        hub_schemas.ProfileSectionStatus(
            key="school_type",
            label="School Type",
            complete="school_type" not in missing,
            route="/profile",
            description="Type of school you work at",
        ),
        hub_schemas.ProfileSectionStatus(
            key="language_preference",
            label="Teaching Language",
            complete="language_preference" not in missing,
            route="/profile",
            description="Primary language of instruction",
        ),
        hub_schemas.ProfileSectionStatus(
            key="years_experience",
            label="Years of Experience",
            complete="years_experience" not in missing,
            route="/profile",
            description="How long you've been teaching",
        ),
    ]

    # ---------- Identity / career sections ----------
    exp_count = _count_identity_records(db, teacher_id, TeacherExperience)
    edu_count = _count_identity_records(db, teacher_id, TeacherEducation)
    cert_count = _count_identity_records(db, teacher_id, TeacherCertification)
    achieve_count = _count_identity_records(db, teacher_id, TeacherAchievement)
    doc_count = _count_identity_records(db, teacher_id, TeacherCareerDocument)

    identity_fields = [
        hub_schemas.ProfileSectionStatus(
            key="experience",
            label="Teaching Experience",
            complete=exp_count > 0,
            count=exp_count,
            route="/profile?tab=experience",
            description="Add positions you've held",
        ),
        hub_schemas.ProfileSectionStatus(
            key="education",
            label="Education",
            complete=edu_count > 0,
            count=edu_count,
            route="/profile?tab=education",
            description="Your academic qualifications",
        ),
        hub_schemas.ProfileSectionStatus(
            key="certifications",
            label="Certifications",
            complete=cert_count > 0,
            count=cert_count,
            route="/profile?tab=certifications",
            description="Teaching licenses and credentials",
        ),
        hub_schemas.ProfileSectionStatus(
            key="achievements",
            label="Achievements",
            complete=achieve_count > 0,
            count=achieve_count,
            route="/profile?tab=achievements",
            description="Awards, publications, or recognitions",
        ),
        hub_schemas.ProfileSectionStatus(
            key="documents",
            label="Career Documents",
            complete=doc_count > 0,
            count=doc_count,
            route="/profile?tab=documents",
            description="CV, resume, or portfolio upload",
        ),
    ]

    all_sections = context_fields + identity_fields
    has_identity_record = "experience_or_certification_or_document" not in missing
    teaching_context_complete = not any(
        f in missing for f in _COMPLETENESS_FIELDS
    )
    missing_count = len([s for s in all_sections if not s.complete])

    # Build a short guidance message for the banner
    if completeness.score == 0.0:
        guidance_message = (
            "Start by adding your teaching context — country, subjects, and grade band — "
            "then add at least one experience or certification to unlock your personalized Learning Hub."
        )
    elif completeness.score < 0.45:
        guidance_message = (
            f"You're {int(completeness.score * 100)}% complete. "
            "Add a few more profile details to unlock personalized recommendations."
        )
    elif not has_identity_record:
        guidance_message = (
            "Great start! Add at least one experience record, certification, or document "
            "to enable full AI personalization."
        )
    else:
        guidance_message = (
            "Your profile is ready. Add more details any time to improve your recommendations."
        )

    return hub_schemas.ProfileCompletionStatusResponse(
        score=completeness.score,
        is_sufficient=completeness.score >= 0.45,
        missing_count=missing_count,
        sections=all_sections,
        teaching_context_complete=teaching_context_complete,
        has_identity_record=has_identity_record,
        guidance_message=guidance_message,
    )
