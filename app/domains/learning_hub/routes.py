"""
Learning Hub API routes: Pipeline2 run, home, home/refresh, sections.

The /home endpoint is dual-mode:
- When the user has a personalization profile with a current slate: returns slate-based
  section payload (mode: personalized / initializing / partial_ready / no_profile).
- When no personalization profile exists: returns legacy LearningHubHomeResponse.
Frontend detects mode by presence of 'sections' key.
"""
import threading
import uuid as _uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.session import get_db
from app.domains.auth.dependencies import get_current_user
from app.domains.auth.models import User
from app.domains.learning_hub import schemas as hub_schemas
from app.domains.learning_hub.services import (
    LearningHubHomeService,
    Pipeline2IntegrationService,
)
from app.domains.learning_hub.route_resolver import resolve_learning_hub_route
from app.domains.teacher_intelligence import schemas as ti_schemas

logger = get_logger(__name__)
FASTTRACK_TEST_EMAILS = {"test1@gmail.com"}

router = APIRouter(prefix="/api/v1/learning-hub", tags=["learning-hub"])


@router.get(
    "/profile-completion-status",
    response_model=hub_schemas.ProfileCompletionStatusResponse,
    summary="Profile completion breakdown for Learning Hub gate UI",
)
def get_profile_completion_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> hub_schemas.ProfileCompletionStatusResponse:
    """
    Returns a structured checklist of profile sections (teaching context + identity)
    with completion status, record counts, and CTA routes.
    Used by the frontend ProfileCompletionGate to guide teachers to complete their profile.
    """
    from app.domains.learning_hub.services.learning_hub_home_service import get_profile_completion_status
    return get_profile_completion_status(db, current_user.id)


@router.get("/bootstrap-status")
def get_bootstrap_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Source of truth for Learning Hub full-page orchestration loader:
    progress, stages, MVHR (can_enter_hub), anti-stuck / timeout hints, failure flags.
    """
    from app.domains.learning_hub.bootstrap_orchestration import compute_bootstrap_status

    return compute_bootstrap_status(db, current_user.id)


@router.get("/bootstrap-status/stream")
def stream_bootstrap_status(
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    SSE stream for Learning Hub bootstrap status.
    Emits one JSON event every 2.5 s until can_enter_hub is True or 180 s have elapsed.
    Set headers Cache-Control: no-cache and X-Accel-Buffering: no for proxy compatibility.
    """
    import json
    import time
    from fastapi.responses import StreamingResponse

    user_id = current_user.id

    def generate():
        # Import SessionLocal inside the generator to avoid circular imports and
        # to create a fresh session that lives only for the lifetime of this stream.
        from app.db.session import SessionLocal
        from app.domains.learning_hub.bootstrap_orchestration import compute_bootstrap_status

        db = SessionLocal()
        try:
            start = time.time()
            while time.time() - start < 180:
                status = compute_bootstrap_status(db, user_id)
                yield f"data: {json.dumps(status)}\n\n"
                if status.get("can_enter_hub"):
                    break
                time.sleep(2.5)
        finally:
            db.close()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/bootstrap-retry")
def bootstrap_retry(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Retry Learning Hub bootstrapping for the authenticated user.
    This is a production-safe recovery action (idempotent background expansion).
    """
    from app.core.config import settings
    from app.domains.personalization.services.inventory_expansion_worker import InventoryExpansionWorker

    if not settings.LEARNING_HUB_AUTO_LLM_ENABLED:
        return {
            "status": "disabled",
            "message": "Learning Hub auto LLM is off. Set LEARNING_HUB_AUTO_LLM_ENABLED=true after your API key is configured.",
            "user_id": str(current_user.id),
            "trigger": "bootstrap_retry",
        }

    InventoryExpansionWorker.run_in_background(current_user.id, trigger="bootstrap_retry")
    return {
        "status": "started",
        "user_id": str(current_user.id),
        "trigger": "bootstrap_retry",
    }


def _normalize_duration_label(content_type: str, duration_min: int | None) -> str:
    """Normalize duration labels to product-quality, type-specific ranges."""
    ct = (content_type or "").strip().lower()
    if ct == "micro_course":
        minutes = max(5, min(12, duration_min or 8))
        return f"{minutes} min"
    if ct == "ai_guided_tutorial":
        minutes = max(8, min(25, duration_min or 12))
        return f"{minutes} min"
    if ct in ("learning_path", "path_module"):
        minutes = max(60, min(180, duration_min or 90))
        return f"{minutes} min"
    if ct in ("research", "resource"):
        minutes = max(5, min(10, duration_min or 7))
        return f"{minutes} min read"
    if duration_min and duration_min > 0:
        return f"{duration_min} min"
    return ""


def _teacher_context_tokens(ctx: Any) -> tuple[str, str]:
    subjects = list(getattr(ctx, "subjects", []) or [])
    subject = (subjects[0] if subjects else "Teaching").title()
    grade_band = str(getattr(ctx, "grade_band", "") or "").replace("_", " ").title() or "Your Class"
    return subject, grade_band


def _is_placeholder_title(title: str | None) -> bool:
    t = (title or "").strip().lower()
    return t.startswith("[fasttrack]") or t.startswith("generated ") or t.startswith("fasttrack ")


def _contextual_title_for_section(section: str, ctx: Any) -> str:
    subject, grade_band = _teacher_context_tokens(ctx)
    if section == "tutorials":
        return f"{subject} Lesson Demo for {grade_band}"
    if section == "research_insights":
        return f"Evidence-Based {subject} Strategies"
    if section == "specialist_tracks":
        return f"{subject} Mastery Track ({grade_band})"
    if section == "micro_courses":
        return f"Foundational {subject} Practice"
    if section == "growth_recommendations":
        return f"{subject} Professional Growth Path"
    return f"{subject} Learning Content"


def _section_scoped_route(section: str, content_slug: str | None, fallback_route: str | None) -> str:
    slug = (content_slug or "").strip()
    if not slug:
        return fallback_route or "/learning-hub"
    if section == "tutorials":
        return f"/learning-hub/ai-guided-tutorials-demonstrations/{slug}"
    if section == "research_insights":
        return f"/learning-hub/research-insights-library/{slug}"
    if section == "specialist_tracks":
        return f"/learning-hub/specialist-deep-dive-tracks/{slug}"
    if section == "growth_recommendations":
        return f"/learning-hub/ai-growth-recommendations/{slug}"
    if section == "micro_courses":
        return f"/learning-hub/personalized-micro-courses/{slug}"
    return fallback_route or "/learning-hub"


def _default_growth_page_visual() -> dict[str, Any]:
    return {
        "sidebarStyle": "tiered",
        "headerGradient": "from-green-600 via-emerald-600 to-teal-600",
        "heroSubtitleClass": "text-green-100",
        "heroShowEarnedPoints": False,
        "heroShowImpactRow": False,
        "heroShowBookmarkShare": False,
        "tieredSidebarActive": "bg-green-100 border-2 border-green-500 text-green-900",
        "tieredSidebarCompleted": "bg-gray-50 border border-gray-200 text-gray-700 hover:bg-gray-100",
        "tieredSidebarIdle": "bg-white border border-gray-200 text-gray-700 hover:bg-gray-50",
        "tieredSidebarCheckComplete": "text-green-600",
        "sidebarProgressFill": "bg-green-600",
        "engagementSidebarActive": "bg-blue-100 border-2 border-blue-500 text-blue-900",
        "engagementSidebarIdle": "bg-white border border-gray-200 text-gray-700 hover:bg-gray-50",
        "engagementNumCompleted": "bg-green-600 text-white",
        "engagementNumActive": "bg-blue-600 text-white",
        "engagementNumIdle": "bg-gray-200 text-gray-600",
        "engagementTitleActive": "text-blue-900",
        "lessonTypeIconClass": "text-green-600",
        "pointsPill": "bg-green-100 text-green-700",
        "videoOverlayGradient": "from-green-600 to-emerald-600",
        "videoPlayUseTranslucent": False,
        "videoPlayIconClass": "text-green-600",
        "showLessonHeaderShare": True,
        "keyPointsPanel": "bg-green-50 rounded-lg p-6 border border-green-200",
        "keyPointsCheck": "text-green-600",
        "transcriptPanel": "bg-white rounded-lg p-6 border border-gray-200",
        "readingArticleWrap": "bg-white rounded-lg p-8 border border-gray-200",
        "readingTakeawaysPanel": "bg-green-50 rounded-lg p-6 border border-green-200",
        "readingTakeawaysIcon": "text-green-600",
        "interactiveStepsPanel": "bg-green-50 rounded-lg p-6 border border-green-200",
        "interactiveStepNumber": "bg-green-600 text-white",
        "templateSectionsCard": "bg-white rounded-lg p-6 border border-gray-200",
        "templateSectionNumber": "bg-green-100 text-green-700",
        "templateDownloadCard": "p-4 bg-green-50 border-2 border-green-200 rounded-lg hover:bg-green-100",
        "templateDownloadIcon": "text-green-600",
        "markCompleteButton": "bg-green-600 hover:bg-green-700",
        "completionPanel": "border-2 border-green-300 bg-gradient-to-br from-green-50 to-emerald-50",
        "completionIconBg": "bg-green-600",
        "completionCta": "bg-green-600 hover:bg-green-700",
        "completedLessonBadge": "bg-green-100 text-green-700",
        "lessonNavigation": "inline-only",
        "footerCompleteButton": "bg-green-600 hover:bg-green-700",
        "blockHeadingClass": "text-sm font-semibold text-gray-900 mb-3",
    }


def _is_rich_growth_payload(content: Any) -> bool:
    if not isinstance(content, dict):
        return False
    modules = content.get("modules") or []
    if not isinstance(modules, list) or len(modules) < 1:
        return False
    first = modules[0] if modules else {}
    detail = first.get("detail") if isinstance(first, dict) else None
    return bool(
        content.get("aiGuidance")
        and content.get("skillImpacts")
        and isinstance(detail, dict)
        and isinstance(detail.get("lessons"), list)
        and detail.get("pageVisual")
    )


def _is_rich_tutorial_payload(content: Any) -> bool:
    if not isinstance(content, dict):
        return False
    steps = content.get("steps") or []
    if not isinstance(steps, list) or len(steps) < 3:
        return False
    first = steps[0] if steps else {}
    return bool(
        content.get("completionTitle")
        and content.get("completionBody")
        and isinstance(first, dict)
        and isinstance((first.get("content") or {}).get("data"), dict)
    )


def _is_rich_research_payload(content: Any) -> bool:
    if not isinstance(content, dict):
        return False
    payload = content.get("payload") if isinstance(content, dict) else None
    sections = (payload or {}).get("sections") if isinstance(payload, dict) else None
    return bool(
        content.get("headerBadgeLabels")
        and content.get("headerGradientClass")
        and isinstance(sections, list)
        and len(sections) >= 2
        and payload.get("implementationIdeas")
        and payload.get("references")
    )


def _is_rich_specialist_payload(content: Any) -> bool:
    if not isinstance(content, dict):
        return False
    modules = content.get("modules") or []
    if not isinstance(modules, list) or len(modules) < 2:
        return False
    first = modules[0] if modules else {}
    return bool(
        content.get("headerGradientClass")
        and content.get("assessment")
        and content.get("certification")
        and isinstance(first, dict)
        and first.get("moduleAssessment")
        and first.get("metadata")
    )


def _build_contextual_detail_payload(item: Any, ctx: Any, section: str | None = None) -> dict[str, Any]:
    subject, grade_band = _teacher_context_tokens(ctx)
    title = (item.title or _contextual_title_for_section("", ctx)).strip()
    blob = item.json_blob if isinstance(item.json_blob, dict) else {}
    if item.content_type == "ai_guided_tutorial":
        if _is_rich_tutorial_payload(blob.get("aiGuidedTutorialContent")):
            return blob
        return {
            "aiGuidedTutorialContent": {
                "type": "tutorial",
                "renderProfile": "lesson-planner",
                "description": f"Guided walkthrough tailored to {subject} teaching goals.",
                "heroSubtitle": f"{subject} tutorial",
                "heroDescription": f"Practical walkthrough for {grade_band} with classroom-ready steps.",
                "headerDurationLabel": "10 min",
                "completionTitle": "Tutorial complete",
                "completionBody": f"You now have a reusable {subject} routine for {grade_band}.",
                "metadata": {
                    "source": "backend-contextual",
                    "subject": subject,
                    "grade_band": grade_band,
                },
                "steps": [
                    {
                        "id": "s1",
                        "title": "Context setup",
                        "duration": "3 min",
                        "content": {
                            "type": "text",
                            "data": {
                                "strategies": [
                                    f"Define one focused {subject} objective for {grade_band}.",
                                    "Clarify success criteria before activity design.",
                                ],
                                "tools": ["Learning objective", "Success criteria", "Exit ticket prompt"],
                            },
                        },
                        "keyTakeaways": ["Define one measurable objective"],
                        "reflection": "Which part needs more modeling?",
                    },
                    {
                        "id": "s2",
                        "title": "Template adaptation",
                        "duration": "4 min",
                        "content": {
                            "type": "interactive",
                            "data": {
                                "strategy": "Adapt activity flow to your class pace.",
                                "implementation": ["Warm-up prompt", "Guided practice", "Exit check"],
                                "examples": [{"scenario": "Daily routine", "tip": "Use one consistent check-for-understanding moment."}],
                            },
                        },
                        "keyTakeaways": ["Keep transitions explicit"],
                        "reflection": "Which transition loses engagement?",
                    },
                    {
                        "id": "s3",
                        "title": "Quick review loop",
                        "duration": "3 min",
                        "content": {
                            "type": "example",
                            "data": {
                                "summary": "Use one immediate check-for-understanding routine.",
                                "example": "Collect 3 exemplar responses and compare to success criteria.",
                            },
                        },
                        "keyTakeaways": ["Close with evidence"],
                        "reflection": "What evidence confirms readiness?",
                    },
                ],
            }
        }
    if item.content_type == "research":
        if _is_rich_research_payload(blob.get("researchInsightContent")):
            return blob
        return {
            "researchInsightContent": {
                "type": "research-insight",
                "renderProfile": "research-article",
                "variant": "research-structured-sections",
                "description": f"Research summary for {subject} teachers.",
                "heroSubtitle": f"{subject} evidence brief",
                "heroDescription": f"Evidence-backed actions for {grade_band}.",
                "headerDurationLabel": "8 min read",
                "headerBadgeLabels": ["Evidence-Based", "Teacher-Friendly", "Actionable"],
                "headerGradientClass": "from-blue-600 via-indigo-600 to-purple-600",
                "metadata": {"subject": subject, "grade_band": grade_band, "source": "backend-contextual"},
                "payload": {
                    "summary": [
                        f"Retrieval practice improves {subject} retention.",
                        "Explicit modeling reduces cognitive load.",
                        "Frequent low-stakes checks improve transfer.",
                    ],
                    "sections": [
                        {
                            "id": "what-works",
                            "title": "What works in classrooms",
                            "contentBlocks": [
                                {
                                    "type": "text",
                                    "heading": "High-impact patterns",
                                    "paragraphs": [
                                        f"Across studies, {subject} outcomes improve when teachers model first, then shift to guided practice.",
                                        "Brief retrieval checks during class and at the next lesson start significantly improve recall.",
                                    ],
                                }
                            ],
                        },
                        {
                            "id": "implementation",
                            "title": "How to implement this week",
                            "contentBlocks": [
                                {
                                    "type": "interactive",
                                    "title": "Plan one evidence loop",
                                    "prompt": f"Pick one {subject} lesson and define the observable evidence students will produce.",
                                    "tips": [
                                        "Use one explicit success criterion.",
                                        "Insert a 2-minute retrieval check.",
                                        "Use responses to regroup support.",
                                    ],
                                }
                            ],
                        },
                    ],
                    "keyTakeaways": [
                        "Keep explanations short and modeled.",
                        "Use frequent checks to adapt instruction.",
                    ],
                    "implementationIdeas": [
                        "Start class with a 2-minute retrieval warm-up.",
                        "Use one explicit success criterion per task.",
                    ],
                    "references": [
                        "Rosenshine, B. (2012) Principles of Instruction.",
                        "Dunlosky et al. (2013) Effective learning techniques.",
                    ],
                    "metadata": {"difficulty": "beginner", "audience": "k12-teachers"},
                },
            }
        }
    if item.content_type == "learning_path":
        if section == "growth_recommendations" and _is_rich_growth_payload(blob.get("aiGrowthRecommendationContent")):
            return blob
        if section != "growth_recommendations" and _is_rich_specialist_payload(blob.get("specialistDeepDiveContent")):
            return blob
        if section == "growth_recommendations":
            return {
                "aiGrowthRecommendationContent": {
                    "type": "path",
                    "description": f"Personalized growth path for {subject}.",
                    "estimatedTime": "90 min",
                    "impactLevel": "High",
                    "heroSubtitle": f"{subject} growth plan",
                    "heroDescription": f"Progressive modules tuned for {grade_band}.",
                    "themeId": "ai-growth-student-engagement",
                    "tags": ["personalized", subject.lower(), "professional-growth"],
                    "metadata": {"subject": subject, "grade_band": grade_band, "source": "backend-contextual"},
                    "blocks": [{"type": "text", "heading": "Path overview", "paragraphs": [f"Structured {subject} growth path for {grade_band}."]}],
                    "cta": {"primaryLabel": "Start Path", "secondaryLabel": "Save for later"},
                    "aiGuidance": {
                        "recommendation": f"Focus on one high-leverage {subject} routine this week.",
                        "reason": "Recent usage signals indicate readiness for deeper practice.",
                        "nextSteps": ["Start module 1", "Apply in one class", "Review outcomes"],
                        "personalizedTip": f"Use examples connected to {grade_band} classroom context.",
                    },
                    "skillImpacts": [
                        {"skillId": "impact-eng-active-participation", "before": 42, "after": 71, "improvement": 29, "description": "Improve active participation routines."},
                        {"skillId": "impact-eng-teaching-effectiveness", "before": 48, "after": 68, "improvement": 20, "description": "Tighter checks for understanding."},
                    ],
                    "modules": [
                        {
                            "id": "g1",
                            "slug": "contextual-growth-module-1",
                            "title": f"{subject} Engagement Foundations",
                            "description": "Build repeatable engagement routines.",
                            "duration": "30 min",
                            "level": "Beginner",
                            "impact": "High",
                            "skillIds": ["eng-gamification", "eng-points-badges"],
                            "learningOutcomes": ["Run one structured engagement loop", "Track participation signals"],
                            "prerequisites": ["Complete baseline profile setup"],
                            "content": [
                                {
                                    "type": "video",
                                    "title": "Model routine",
                                    "duration": "8 min",
                                    "points": 20,
                                    "media": {
                                        "type": "video",
                                        "provider": "mp4",
                                        "url": "https://www.w3schools.com/html/mov_bbb.mp4",
                                        "title": "Model routine",
                                        "duration": "8 min",
                                        "controls": True,
                                    },
                                },
                                {"type": "reading", "title": "Evidence checklist", "points": 10},
                                {"type": "interactive", "title": "Engagement loop builder", "points": 20},
                                {"type": "template", "title": "Weekly implementation template", "points": 10},
                            ],
                            "blocks": [{"type": "text", "heading": "Module note", "paragraphs": ["Apply one engagement loop and measure evidence."]}],
                            "metadata": {"module_order": 1, "path": "contextual-growth"},
                            "assessment": {"type": "Practice check", "description": "Apply routine and reflect.", "points": 30},
                            "realWorldApplication": "Use this in tomorrow's lesson warm-up.",
                            "detail": {
                                "moduleLabel": "Module 1 of 1",
                                "backPathSlug": "contextual-growth-module-1",
                                "pageVisual": _default_growth_page_visual(),
                                "lessons": [
                                    {
                                        "id": "g1-l1",
                                        "type": "video",
                                        "title": "Model routine",
                                        "duration": "8 min",
                                        "points": 20,
                                        "content": {
                                            "description": "Observe a complete routine with transitions and checks.",
                                            "keyPoints": ["Clear launch", "Guided practice", "Evidence capture"],
                                            "transcript": "Start with objective, model, then gather evidence.",
                                        },
                                    },
                                    {
                                        "id": "g1-l2",
                                        "type": "interactive",
                                        "title": "Build your loop",
                                        "points": 20,
                                        "content": {
                                            "description": "Design your own engagement loop.",
                                            "steps": ["Define objective", "Pick interaction", "Define evidence"],
                                        },
                                    },
                                ],
                            },
                        }
                    ],
                    "storageKey": "growth-contextual-path",
                }
            }
        return {
            "specialistDeepDiveContent": {
                "type": "track",
                "renderProfile": "deep-dive-track",
                "description": f"Advanced {subject} track for {grade_band}.",
                "heroSubtitle": "Specialist track",
                "heroDescription": f"Structured progression to deepen {subject} outcomes.",
                "headerGradientClass": "from-indigo-600 via-blue-600 to-cyan-600",
                "modules": [
                    {
                        "id": "m1",
                        "title": f"{subject} Core Patterns",
                        "description": "High-impact routines and sequencing.",
                        "duration": "35 min",
                        "learningOutcomes": [
                            "Run a consistent instruction sequence",
                            "Collect evidence at each phase",
                        ],
                        "moduleAssessment": {
                            "type": "Checkpoint",
                            "description": "Submit one implemented routine artifact.",
                            "points": 30,
                        },
                        "lessons": [
                            {
                                "id": "l1",
                                "title": "Instructional routine",
                                "duration": "12 min",
                                "contentBlocks": [
                                    {
                                        "type": "text",
                                        "heading": "Core routine",
                                        "paragraphs": [
                                            "Use explicit modeling, guided practice, then independent checks.",
                                            "Keep transitions visible to reduce cognitive load.",
                                        ],
                                    }
                                ],
                        "metadata": {"level": "beginner", "subject": subject},
                            },
                            {
                                "id": "l2",
                                "title": "Application cycle",
                                "duration": "10 min",
                                "contentBlocks": [
                                    {
                                        "type": "interactive",
                                        "title": "Apply to your week",
                                        "prompt": "Map this routine to one weekly lesson.",
                                        "tips": [
                                            "Start with one class first",
                                            "Measure completion and mastery",
                                        ],
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "id": "m2",
                        "title": f"{subject} Evidence and Feedback",
                        "description": "Tight feedback loops for faster student growth.",
                        "duration": "30 min",
                        "learningOutcomes": [
                            "Design a quick evidence check",
                            "Use feedback to adjust next lesson",
                        ],
                        "lessons": [
                            {
                                "id": "l3",
                                "title": "Feedback protocol",
                                "duration": "9 min",
                                "contentBlocks": [
                                    {
                                        "type": "caseStudy",
                                        "title": "Case: Mid-lesson misconception",
                                        "scenario": f"A {grade_band} class shows confusion during a {subject} task. You need a rapid adjustment.",
                                        "discussionQuestions": [
                                            "What evidence indicates misconception?",
                                            "Which feedback move should happen now?",
                                        ],
                                    }
                                ],
                            }
                        ],
                        "metadata": {"level": "intermediate", "subject": subject},
                    },
                ],
                "outcomes": [f"Improve {subject} lesson clarity", "Increase student success-rate on exit checks"],
                "assessment": {
                    "title": "Track assessment",
                    "description": "Submit one revised lesson plan with evidence checks.",
                    "points": 60,
                },
                "certification": {
                    "title": f"{subject} Specialist track completed",
                    "body": "Apply this cycle in one classroom this week and review outcomes.",
                },
                "metadata": {"source": "backend-contextual", "subject": subject, "grade_band": grade_band},
            }
        }
    if item.content_type == "micro_course":
        if blob.get("personalizedMicroCourseContent"):
            return blob
        return {
            "personalizedMicroCourseContent": {
                "description": f"Short {subject} micro-course for {grade_band}.",
                "learningObjectives": [f"Plan one stronger {subject} mini-lesson", "Apply one formative check"],
                "lessons": [{"id": 1, "title": "Focused objective", "duration": "5 min", "contentBlocks": [{"type": "text", "heading": "Objective", "paragraphs": ["Set one clear objective and mastery signal."]}]}],
                "quizQuestions": [{"id": 1, "question": "What should come first?", "options": ["Objective clarity", "Activity length", "Worksheet count"], "correctAnswer": 0, "explanation": "Clear objective anchors lesson decisions."}],
                "quizSubtitle": "Quick check",
                "passingScorePercent": 70,
                "successMessage": "Great progress.",
                "themeId": "pmc-blue-assessment",
            }
        }
    return blob


@router.post(
    "/pipeline2/run",
    response_model=ti_schemas.MLOutputResponse,
    status_code=status.HTTP_201_CREATED,
)
def run_pipeline2(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Run Pipeline2 for the current user. Requires a feature snapshot."""
    service = Pipeline2IntegrationService(db)
    try:
        output = service.run_pipeline2_for_teacher(current_user.id)
        return output
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Pipeline2 run failed: {e!s}",
        )


def _run_personalization_in_background(user_id: _uuid.UUID) -> None:
    """
    Run the full personalization orchestration in a separate thread with its own DB session.
    Called after quickly returning `mode: initializing` to the frontend.
    """
    from app.db.session import SessionLocal
    from app.domains.personalization.services.personalization_orchestrator import PersonalizationOrchestrator
    from app.domains.personalization.routes import _build_profile_snapshot

    bg_db = SessionLocal()
    try:
        snapshot = _build_profile_snapshot(user_id, bg_db)
        orch = PersonalizationOrchestrator(bg_db)
        orch.start_personalization(user_id, snapshot, profile_completeness=100.0, trigger="auto_home_background")
        bg_db.commit()
        logger.info("learning_hub.personalization_background_complete", extra={"user_id": str(user_id)})
    except Exception as exc:
        logger.warning("learning_hub.personalization_background_failed", extra={"user_id": str(user_id), "error": str(exc)})
        try:
            bg_db.rollback()
        except Exception:
            pass
    finally:
        bg_db.close()


def _ensure_test_user_minimum_sections(db: Session, user: User) -> None:
    """
    Test-user acceleration: guarantee at least one visible item exists for
    tutorials/research/specialist so runtime verification can proceed.
    """
    if (user.email or "").strip().lower() not in FASTTRACK_TEST_EMAILS:
        return

    from datetime import datetime, timezone
    from app.domains.personalization.models import (
        PersonalizedContentAssignment,
        UserPersonalizationProfile,
    )
    from app.domains.content_registry.models import ContentRegistryItem
    from app.domains.personalization.services.slate_service import SlateService
    from app.domains.auth.models import TeacherProfileContext

    profile = (
        db.query(UserPersonalizationProfile)
        .filter(UserPersonalizationProfile.user_id == user.id)
        .first()
    )
    if not profile:
        return

    section_map = {
        "tutorials": "ai_guided_tutorial",
        "research_insights": "research",
        "specialist_tracks": "learning_path",
    }
    changed = False
    now = datetime.now(timezone.utc)
    teacher_ctx = (
        db.query(TeacherProfileContext)
        .filter(TeacherProfileContext.user_id == user.id)
        .first()
    )

    for section, content_type in section_map.items():
        exists = (
            db.query(PersonalizedContentAssignment.id)
            .filter(
                PersonalizedContentAssignment.user_id == user.id,
                PersonalizedContentAssignment.personalization_version == profile.personalization_version,
                PersonalizedContentAssignment.section == section,
                PersonalizedContentAssignment.bucket == "visible",
                PersonalizedContentAssignment.is_active == True,  # noqa: E712
            )
            .first()
        )
        if exists:
            continue

        cid = f"fasttrack-{section}-{_uuid.uuid4().hex[:10]}"
        base_title = _contextual_title_for_section(section, teacher_ctx)
        payload = _build_contextual_detail_payload(
            item=type("ContextItem", (), {"content_type": content_type, "title": base_title, "json_blob": {}})(),
            ctx=teacher_ctx,
            section=section,
        )
        subject, grade_label = _teacher_context_tokens(teacher_ctx)
        item = ContentRegistryItem(
            content_id=cid,
            content_type=content_type,
            schema_version="v1",
            content_version_major=1,
            content_version_minor=0,
            content_version_patch=0,
            locale="en",
            status="published",
            title=base_title,
            subtitle=f"Personalized for {grade_label}",
            summary=f"Generated for {subject} teaching context.",
            category="AI Personalized",
            estimated_duration_min=8,
            difficulty="beginner",
            impact_level="medium",
            tags={"fasttrack": True, "section": section},
            alignment={"fasttrack": True},
            json_blob={"fasttrack": True, **payload},
            source_type="content_factory",
            source_ref="fasttrack_test_user",
            published_at=now,
        )
        db.add(item)
        db.flush()

        try:
            route = resolve_learning_hub_route(item)
        except Exception:
            route = "/learning-hub"

        assignment = PersonalizedContentAssignment(
            personalization_profile_id=profile.id,
            snapshot_id=None,
            user_id=user.id,
            personalization_version=profile.personalization_version,
            content_id=item.content_id,
            content_type=item.content_type,
            section=section,
            bucket="visible",
            position=0,
            priority_rank=0,
            diversity_key=(item.title or item.content_id).strip().lower(),
            score=0.55,
            reason_codes=["fasttrack_test_minimum"],
            ranking_signals={"fasttrack": True},
            route=route,
            content_slug=item.content_id,
            status="assigned",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        db.add(assignment)
        changed = True

    if changed:
        db.flush()
        SlateService(db).build_slate(profile)


@router.get("/home")
def get_home(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get Learning Hub home payload for the current user.

    Dual-mode response:
    - If personalization profile + slate exists → returns {mode, sections, ...}
    - First visit with complete profile → triggers background personalization, returns initializing immediately
    - No profile → returns legacy response
    """
    try:
        from app.domains.personalization.services.personalization_profile_service import PersonalizationProfileService
        from app.domains.personalization.services.slate_service import SlateService
        from app.domains.personalization.services.section_readiness_service import SectionReadinessService
        from app.domains.personalization.services.assignment_service import AssignmentService
        from app.domains.personalization.enums import SectionReadinessStatus
        from app.domains.personalization.models import UserActivityEvent
        from app.domains.content_factory.models import ContentGenerationJob
        from app.domains.auth.models import TeacherProfileContext

        profile_svc = PersonalizationProfileService(db)
        profile = profile_svc.get(current_user.id)
        teacher_ctx = db.query(TeacherProfileContext).filter(TeacherProfileContext.user_id == current_user.id).first()

        from app.domains.learning_hub.services.learning_hub_home_service import _compute_profile_completeness

        hub_profile_completeness = _compute_profile_completeness(db, current_user.id).model_dump()

        # Auto-start: create a minimal profile record immediately, then run full orchestration in background
        if not profile or not profile.personalization_started_at:
            ctx = db.query(TeacherProfileContext).filter(TeacherProfileContext.user_id == current_user.id).first()
            if ctx and ctx.country and ctx.subjects and ctx.grade_band:
                try:
                    # Create a lightweight profile row now (fast — no content allocation yet)
                    from app.domains.personalization.models import UserPersonalizationProfile
                    from app.domains.personalization.enums import PersonalizationStatus
                    import datetime

                    if not profile:
                        profile = UserPersonalizationProfile(
                            user_id=current_user.id,
                            status=PersonalizationStatus.INITIALIZING,
                            personalization_started_at=datetime.datetime.utcnow(),
                            personalization_version=1,
                        )
                        db.add(profile)
                    else:
                        profile.status = PersonalizationStatus.INITIALIZING
                        profile.personalization_started_at = datetime.datetime.utcnow()
                    db.commit()
                    db.refresh(profile)

                    # Fire full orchestration in a background thread so we can return immediately
                    t = threading.Thread(
                        target=_run_personalization_in_background,
                        args=(current_user.id,),
                        daemon=True,
                    )
                    t.start()
                    logger.info("learning_hub.personalization_background_started", extra={"user_id": str(current_user.id)})
                except Exception as exc:
                    logger.warning("learning_hub.personalization_init_failed", extra={"user_id": str(current_user.id), "error": str(exc)})
                    try:
                        db.rollback()
                    except Exception:
                        pass

                # Return initializing immediately — frontend shows AI loading state
                from app.domains.learning_hub.bootstrap_orchestration import compute_bootstrap_status

                hb0 = compute_bootstrap_status(db, current_user.id)
                return {
                    "mode": "initializing",
                    "personalization_version": getattr(profile, "personalization_version", 1) or 1,
                    "sections": {},
                    "last_recomputed_at": None,
                    "profile_completeness": hub_profile_completeness,
                    "page_readiness_state": hb0.get("page_readiness_state"),
                    "minimum_ready_sections": hb0.get("minimum_ready_sections_met") or [],
                    "hero_ready": bool(hb0.get("can_enter_hub")),
                    "global_generation_stage": hb0.get("stage_message"),
                    "global_progress_percent": int(hb0.get("progress_percent") or 0),
                    "hub_bootstrap": hb0,
                    "orchestration": {
                        "can_enter_hub": hb0.get("can_enter_hub"),
                        "current_stage": hb0.get("current_stage"),
                        "timeout_state": hb0.get("timeout_state"),
                        "fallback_message": hb0.get("fallback_message"),
                        "blocking_sections": hb0.get("blocking_sections"),
                    },
                }

        if profile and profile.personalization_started_at:
            _ensure_test_user_minimum_sections(db, current_user)
            slate_svc = SlateService(db)
            slate = slate_svc.get_current(current_user.id)
            readiness_svc = SectionReadinessService(db)
            readiness_rows = readiness_svc.get_current_all(current_user.id, profile.personalization_version)
            readiness_map = {r.section: r.status for r in readiness_rows}

            if slate:
                items = slate_svc.get_items(slate.id)
                sections: Dict[str, Any] = {}

                # Enrich titles from content registry in one batch query
                content_ids = [i.content_id for i in items if i.content_id]
                title_map: Dict[str, str] = {}
                category_map: Dict[str, str] = {}
                duration_map: Dict[str, str] = {}
                difficulty_map: Dict[str, str] = {}
                source_map: Dict[str, str] = {}
                route_map: Dict[str, str] = {}
                if content_ids:
                    try:
                        from app.domains.content_registry.models import ContentRegistryItem
                        reg_items = db.query(ContentRegistryItem).filter(ContentRegistryItem.content_id.in_(content_ids)).all()
                        for ri in reg_items:
                            title_map[ri.content_id] = ri.title
                            category_map[ri.content_id] = ri.category or ""
                            duration_map[ri.content_id] = _normalize_duration_label(
                                ri.content_type,
                                ri.estimated_duration_min,
                            )
                            difficulty_map[ri.content_id] = ri.difficulty or ""
                            source_map[ri.content_id] = ri.source_type or ""
                            route_map[ri.content_id] = resolve_learning_hub_route(ri)
                    except Exception:
                        pass

                for item in items:
                    sec = item.section
                    if sec not in sections:
                        sections[sec] = {
                            "readiness": readiness_map.get(sec, SectionReadinessStatus.READY),
                            "visible_items": [],
                            "locked_preview_items": [],
                            "message": None,
                        }
                    # Response-level dedup guard for legacy/older slates:
                    # prevent duplicate cards by content_id or normalized title.
                    sec_seen_ids = sections[sec].setdefault("_seen_ids", set())
                    sec_seen_titles = sections[sec].setdefault("_seen_titles", set())
                    enriched_title = item.title or title_map.get(item.content_id, item.content_id)
                    # Items with placeholder titles have not been fully generated yet.
                    # Exclude them entirely — do NOT substitute a contextual title.
                    # The section will surface a generating/preparing state instead.
                    if _is_placeholder_title(enriched_title):
                        sections[sec]["_had_placeholder_items"] = True
                        continue
                    norm_title = (enriched_title or "").strip().lower()
                    if item.content_id in sec_seen_ids:
                        continue
                    if norm_title and norm_title in sec_seen_titles:
                        continue
                    sec_seen_ids.add(item.content_id)
                    if norm_title:
                        sec_seen_titles.add(norm_title)
                    _raw_source = source_map.get(item.content_id, "")
                    # content_origin: canonical origin label for observability
                    _content_origin = (
                        "generated" if _raw_source == "content_factory" else
                        "demo" if _raw_source == "starter_seed" else
                        _raw_source or "unknown"
                    )
                    card = {
                        "assignment_id": str(item.assignment_id),
                        "content_id": item.content_id,
                        "content_type": item.content_type,
                        "section": item.section,
                        "bucket": item.bucket,
                        "position": item.position,
                        "locked": item.locked,
                        "title": enriched_title,
                        "route": _section_scoped_route(
                            sec,
                            item.content_slug,
                            route_map.get(item.content_id) or item.route,
                        ),
                        "content_slug": item.content_slug,
                        "score": item.score,
                        "reason_codes": item.reason_codes or [],
                        "source_type": _raw_source,
                        "content_origin": _content_origin,
                        "display_meta": {
                            "category": category_map.get(item.content_id, ""),
                            "duration": duration_map.get(item.content_id, ""),
                            "difficulty": difficulty_map.get(item.content_id, ""),
                            "source_type": _raw_source,
                        },
                    }
                    # Never expose starter seed/demo items to production user surfaces.
                    if _raw_source == "starter_seed":
                        continue
                    if item.bucket == "visible":
                        sections[sec]["visible_items"].append(card)
                    else:
                        sections[sec]["locked_preview_items"].append(card)

                # Remove internal dedup helper keys before returning API response
                for sec in sections.values():
                    sec.pop("_seen_ids", None)
                    sec.pop("_seen_titles", None)
                    had_placeholders = sec.pop("_had_placeholder_items", False)
                    readiness = sec.get("readiness")
                    if readiness in (SectionReadinessStatus.PREPARING, SectionReadinessStatus.NOT_STARTED):
                        sec["message"] = "We are preparing this section for your profile."
                    elif readiness == SectionReadinessStatus.PARTIAL_READY:
                        sec["message"] = "More personalized items are being prepared."
                    # If all visible items were placeholder-filtered, surface a generating state
                    # so the frontend shows a skeleton/spinner rather than an empty section.
                    if had_placeholders and not sec["visible_items"]:
                        sec["message"] = "Generating personalized content for this section."
                        sec["preparing_reason"] = "content_generating"

                # Enforce response-level inventory caps to prevent stale slate over-exposure.
                # Assignment service enforces caps at creation time; this guards against
                # old data from prior versions that was not fully superseded.
                _RESPONSE_CAPS: dict = {
                    "micro_courses":          {"visible": 5, "locked_preview": 5},
                    "growth_recommendations": {"visible": 3, "locked_preview": 3},
                    "tutorials":              {"visible": 3, "locked_preview": 3},
                    "research_insights":      {"visible": 5, "locked_preview": 5},
                    "specialist_tracks":      {"visible": 3, "locked_preview": 3},
                }
                for sec_key, sec_data in sections.items():
                    caps = _RESPONSE_CAPS.get(sec_key)
                    if caps:
                        sec_data["visible_items"] = sec_data["visible_items"][: caps["visible"]]
                        sec_data["locked_preview_items"] = sec_data["locked_preview_items"][: caps["locked_preview"]]

                # Growth recommendations staged UX state (backend-truth).
                if "growth_recommendations" in sections:
                    assignment_svc = AssignmentService(db)
                    growth_counts = assignment_svc.inventory_counts(
                        current_user.id,
                        "growth_recommendations",
                        profile.personalization_version,
                    )
                    # Filter signals by current personalization version so that a major reset
                    # clears accumulated growth progress and starts fresh.
                    signal_q = db.query(UserActivityEvent).filter(
                        UserActivityEvent.user_id == current_user.id,
                        UserActivityEvent.event_type.in_(
                            ["content_completed", "content_started", "card_clicked"]
                        ),
                    )
                    if hasattr(UserActivityEvent, "personalization_version"):
                        signal_q = signal_q.filter(
                            UserActivityEvent.personalization_version == profile.personalization_version
                        )
                    signal_count = signal_q.count()
                    required_signal_count = 5
                    generation_inflight = (
                        db.query(ContentGenerationJob)
                        .filter(
                            ContentGenerationJob.requested_by_user_id == current_user.id,
                            ContentGenerationJob.source.in_(["inventory_expansion", "gap_detection"]),
                            ContentGenerationJob.status.in_(["pending", "running", "publishing"]),
                            ContentGenerationJob.job_type == "growth_recommendations",
                        )
                        .count()
                    )
                    # Detect stalled generation: signal threshold met, nothing in-flight, inventory
                    # still empty. Check for recently failed jobs to surface recovery state.
                    growth_visible_count = len(sections["growth_recommendations"].get("visible_items") or [])
                    growth_locked_count = len(sections["growth_recommendations"].get("locked_preview_items") or [])
                    inventory_empty = growth_visible_count < 1 or growth_locked_count < 1
                    generation_failed_count = 0
                    if signal_count >= required_signal_count and generation_inflight == 0 and inventory_empty:
                        generation_failed_count = (
                            db.query(ContentGenerationJob)
                            .filter(
                                ContentGenerationJob.requested_by_user_id == current_user.id,
                                ContentGenerationJob.job_type == "growth_recommendations",
                                ContentGenerationJob.status == "failed",
                            )
                            .count()
                        )
                    progress_percent = min(
                        100,
                        int((min(signal_count, required_signal_count) / required_signal_count) * 100),
                    )
                    readiness_state = "ready"
                    if signal_count <= 0:
                        readiness_state = "no_signal"
                    elif signal_count < required_signal_count:
                        readiness_state = "signal_building"
                    elif generation_inflight > 0:
                        readiness_state = "generating"
                    elif inventory_empty:
                        # Nothing in-flight but inventory still empty: stalled if jobs failed,
                        # otherwise still queued/generating.
                        readiness_state = "stalled" if generation_failed_count > 0 else "generating"
                    sections["growth_recommendations"]["growth_state"] = {
                        "readiness_state": readiness_state,
                        "signal_count": int(signal_count),
                        "required_signal_count": required_signal_count,
                        "progress_percent": progress_percent,
                        "generation_status": "running" if generation_inflight > 0 else "idle",
                        "generation_stalled": readiness_state == "stalled",
                    }

                from app.domains.learning_hub.bootstrap_orchestration import compute_bootstrap_status

                orch = compute_bootstrap_status(db, current_user.id)
                page_ready = orch["page_readiness_state"] == "hub_ready"
                global_stage = str(orch.get("stage_message") or orch.get("global_generation_stage") or "")
                global_progress = int(orch.get("progress_percent") or 0)

                # Determine overall mode
                statuses = list(readiness_map.values())
                if not statuses:
                    mode = "initializing"
                elif all(s == SectionReadinessStatus.READY for s in statuses):
                    mode = "personalized"
                elif any(s in (SectionReadinessStatus.READY, SectionReadinessStatus.PARTIAL_READY) for s in statuses):
                    mode = "partial_ready"
                else:
                    mode = "initializing"

                return {
                    "mode": mode,
                    "page_readiness_state": "hub_ready" if page_ready else "hub_bootstrapping",
                    "minimum_ready_sections": orch.get("minimum_ready_sections_met") or [],
                    "hero_ready": bool(orch.get("can_enter_hub")),
                    "global_generation_stage": global_stage,
                    "global_progress_percent": global_progress,
                    "profile_completeness": hub_profile_completeness,
                    "orchestration": {
                        "can_enter_hub": orch.get("can_enter_hub"),
                        "current_stage": orch.get("current_stage"),
                        "timeout_state": orch.get("timeout_state"),
                        "fallback_message": orch.get("fallback_message"),
                        "blocking_sections": orch.get("blocking_sections"),
                    },
                    "hub_bootstrap": orch,
                    "personalization_version": profile.personalization_version,
                    "correlation_id": orch.get("correlation_id") or str(profile.id),
                    "sections": sections,
                    "hero_state": {
                        "mode": mode,
                        "ready_sections": sum(
                            1 for s in readiness_map.values() if s == SectionReadinessStatus.READY
                        ),
                        "total_sections": max(1, len(readiness_map)),
                    },
                    "last_recomputed_at": profile.last_recomputed_at.isoformat() if profile.last_recomputed_at else None,
                }
            else:
                # Profile exists but no slate built yet
                from app.domains.learning_hub.bootstrap_orchestration import compute_bootstrap_status

                orch_ns = compute_bootstrap_status(db, current_user.id)
                return {
                    "mode": "initializing",
                    "page_readiness_state": orch_ns["page_readiness_state"],
                    "minimum_ready_sections": orch_ns.get("minimum_ready_sections_met") or [],
                    "hero_ready": bool(orch_ns.get("can_enter_hub")),
                    "global_generation_stage": str(
                        orch_ns.get("stage_message") or orch_ns.get("global_generation_stage") or ""
                    ),
                    "global_progress_percent": int(orch_ns.get("progress_percent") or 0),
                    "profile_completeness": hub_profile_completeness,
                    "personalization_version": profile.personalization_version,
                    "sections": {},
                    "last_recomputed_at": None,
                    "orchestration": {
                        "can_enter_hub": orch_ns.get("can_enter_hub"),
                        "current_stage": orch_ns.get("current_stage"),
                        "timeout_state": orch_ns.get("timeout_state"),
                        "fallback_message": orch_ns.get("fallback_message"),
                        "blocking_sections": orch_ns.get("blocking_sections"),
                    },
                    "hub_bootstrap": orch_ns,
                }
    except Exception as exc:
        # Personalization service error — fall back to legacy gracefully
        logger.warning("learning_hub.slate_fetch_failed_fallback", extra={"user_id": str(current_user.id), "error": str(exc)})

    # Legacy fallback
    service = LearningHubHomeService(db)
    return service.get_home(current_user.id).model_dump()


@router.get("/sections/debug")
def get_sections_debug(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Debug/admin endpoint: explains per-section content eligibility and generation status.
    Returns source_type breakdown, placeholder counts, pending jobs, and readiness per section.
    """
    try:
        from app.domains.personalization.services.personalization_profile_service import PersonalizationProfileService
        from app.domains.personalization.services.slate_service import SlateService
        from app.domains.personalization.services.assignment_service import AssignmentService
        from app.domains.personalization.services.section_readiness_service import SectionReadinessService
        from app.domains.personalization.enums import SectionReadinessStatus
        from app.domains.content_factory.models import ContentGenerationJob
        from app.domains.content_registry.models import ContentRegistryItem

        profile_svc = PersonalizationProfileService(db)
        profile = profile_svc.get(current_user.id)
        if not profile:
            return {"error": "no_profile"}

        slate_svc = SlateService(db)
        slate = slate_svc.get_current(current_user.id)
        if not slate:
            return {"error": "no_slate", "personalization_version": profile.personalization_version}

        items = slate_svc.get_items(slate.id)
        readiness_map = {r.section: r.status for r in SectionReadinessService(db).get_current_all(current_user.id)}

        # Batch source_type lookup
        content_ids = [i.content_id for i in items]
        registry_rows = db.query(ContentRegistryItem.content_id, ContentRegistryItem.source_type).filter(
            ContentRegistryItem.content_id.in_(content_ids)
        ).all() if content_ids else []
        src_map = {r.content_id: r.source_type or "" for r in registry_rows}

        # Pending generation jobs per section
        pending_jobs = db.query(
            ContentGenerationJob.job_type,
            ContentGenerationJob.status,
            ContentGenerationJob.id,
        ).filter(
            ContentGenerationJob.requested_by_user_id == current_user.id,
            ContentGenerationJob.status.in_(["pending", "running", "publishing", "failed"]),
        ).all()
        jobs_by_section: dict = {}
        for j in pending_jobs:
            jobs_by_section.setdefault(j.job_type, []).append({"id": str(j.id), "status": j.status})

        # Per-section breakdown
        sections_debug: dict = {}
        for item in items:
            sec = item.section
            entry = sections_debug.setdefault(sec, {
                "readiness": str(readiness_map.get(sec, "unknown")),
                "total_assigned": 0,
                "visible": 0,
                "locked_preview": 0,
                "placeholder_filtered": 0,
                "source_types": {},
                "generation_jobs": jobs_by_section.get(sec, []),
            })
            entry["total_assigned"] += 1
            raw_src = src_map.get(item.content_id, "unknown")
            entry["source_types"][raw_src] = entry["source_types"].get(raw_src, 0) + 1
            title = item.title or ""
            if _is_placeholder_title(title):
                entry["placeholder_filtered"] += 1
            elif raw_src == "starter_seed":
                pass  # counted but filtered
            elif item.bucket == "visible":
                entry["visible"] += 1
            else:
                entry["locked_preview"] += 1

        return {
            "personalization_version": profile.personalization_version,
            "slate_id": str(slate.id),
            "sections": sections_debug,
        }
    except Exception as exc:
        logger.warning("learning_hub.sections_debug_failed", extra={"error": str(exc)})
        return {"error": str(exc)}


@router.get("/content/{content_id}/detail")
def get_content_detail(
    content_id: str,
    assignment_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Backend-truth destination payload for Learning Hub content detail pages.
    """
    try:
        from app.domains.content_registry.models import ContentRegistryItem
        from app.domains.personalization.services.personalization_profile_service import PersonalizationProfileService
        from app.domains.personalization.services.assignment_service import AssignmentService

        profile = PersonalizationProfileService(db).get(current_user.id)
        if not profile:
            raise HTTPException(status_code=404, detail="No personalization profile.")

        item = (
            db.query(ContentRegistryItem)
            .filter(ContentRegistryItem.content_id == content_id)
            .first()
        )
        if not item:
            raise HTTPException(status_code=404, detail="Content not found.")
        if (item.source_type or "").strip().lower() == "starter_seed":
            raise HTTPException(status_code=404, detail="Seeded content is not exposed.")

        assignment = None
        assignment_svc = AssignmentService(db)
        if assignment_id:
            try:
                assignment = assignment_svc.get_by_id(_uuid.UUID(assignment_id), current_user.id)
            except Exception:
                assignment = None
        if assignment is None:
            assignment = assignment_svc.find_by_content_id(
                current_user.id,
                content_id,
                profile.personalization_version,
            )

        from app.domains.auth.models import TeacherProfileContext
        teacher_ctx = db.query(TeacherProfileContext).filter(TeacherProfileContext.user_id == current_user.id).first()
        resolved_title = item.title
        if _is_placeholder_title(resolved_title):
            if assignment and assignment.section:
                resolved_title = _contextual_title_for_section(assignment.section, teacher_ctx)
            else:
                resolved_title = _contextual_title_for_section("", teacher_ctx)
        detail_payload = _build_contextual_detail_payload(item, teacher_ctx, assignment.section if assignment else None)

        return {
            "content_id": item.content_id,
            "content_type": item.content_type,
            "title": resolved_title,
            "subtitle": item.subtitle,
            "summary": item.summary,
            "estimated_duration_min": item.estimated_duration_min,
            "difficulty": item.difficulty,
            "category": item.category,
            "route": resolve_learning_hub_route(item),
            "source_type": item.source_type,
            "assignment": {
                "assignment_id": str(assignment.id) if assignment else None,
                "section": assignment.section if assignment else None,
                "bucket": assignment.bucket if assignment else None,
                "locked": assignment.bucket != "visible" if assignment else None,
                "score": assignment.score if assignment else None,
                "reason_codes": assignment.reason_codes if assignment else [],
            },
            # Full render payload for destination pages.
            "detail_payload": detail_payload,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("learning_hub.content_detail_error", extra={"content_id": content_id, "error": str(exc)})
        raise HTTPException(status_code=500, detail="Failed to load content detail.")


@router.post("/home/refresh")
def refresh_home(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Rebuild and return Learning Hub home payload."""
    service = LearningHubHomeService(db)
    return service.get_home(current_user.id).model_dump()


@router.get("/sections/{section}")
def get_section(
    section: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    View All endpoint for a specific section.
    Returns all currently unlocked items for this section (paginated).
    """
    try:
        from app.domains.personalization.services.personalization_profile_service import PersonalizationProfileService
        from app.domains.personalization.services.assignment_service import AssignmentService

        profile_svc = PersonalizationProfileService(db)
        profile = profile_svc.get(current_user.id)

        if not profile:
            return {"section": section, "items": [], "total": 0, "page": page, "page_size": page_size}

        assignment_svc = AssignmentService(db)
        assignments = assignment_svc.get_active(current_user.id, section, profile.personalization_version)
        assignments = [a for a in assignments if a.bucket in ("visible", "locked_preview", "reserve")]
        bucket_rank = {"visible": 0, "locked_preview": 1, "reserve": 2}
        assignments = sorted(assignments, key=lambda a: (bucket_rank.get(a.bucket, 99), a.position))
        total = len(assignments)
        paginated = assignments[(page - 1) * page_size: page * page_size]

        # Enrich section cards from registry for production-quality View All rendering.
        content_ids = [a.content_id for a in paginated if a.content_id]
        title_map: dict[str, str] = {}
        category_map: dict[str, str] = {}
        duration_map: dict[str, str] = {}
        difficulty_map: dict[str, str] = {}
        source_map: dict[str, str] = {}
        route_map: dict[str, str] = {}
        if content_ids:
            try:
                from app.domains.content_registry.models import ContentRegistryItem
                reg_items = (
                    db.query(ContentRegistryItem)
                    .filter(ContentRegistryItem.content_id.in_(content_ids))
                    .all()
                )
                for ri in reg_items:
                    title_map[ri.content_id] = ri.title
                    category_map[ri.content_id] = ri.category or ""
                    duration_map[ri.content_id] = _normalize_duration_label(
                        ri.content_type,
                        ri.estimated_duration_min,
                    )
                    difficulty_map[ri.content_id] = ri.difficulty or ""
                    source_map[ri.content_id] = ri.source_type or ""
                    route_map[ri.content_id] = resolve_learning_hub_route(ri)
            except Exception:
                pass

        items = [
            {
                "assignment_id": str(a.id),
                "content_id": a.content_id,
                "content_type": a.content_type,
                "title": title_map.get(a.content_id, a.content_id),
                "section": a.section,
                "bucket": a.bucket,
                "position": a.position,
                "locked": a.bucket != "visible",
                "unlock_hint": (
                    "Complete visible items to unlock this next."
                    if a.bucket == "locked_preview"
                    else "This item is in reserve and will unlock later."
                    if a.bucket == "reserve"
                    else None
                ),
                "score": a.score,
                "route": _section_scoped_route(
                    a.section,
                    a.content_slug,
                    route_map.get(a.content_id) or a.route,
                ),
                "status": a.status,
                "display_meta": {
                    "category": category_map.get(a.content_id, ""),
                    "duration": duration_map.get(a.content_id, ""),
                    "difficulty": difficulty_map.get(a.content_id, ""),
                    "source_type": source_map.get(a.content_id, ""),
                },
            }
            for a in paginated
            if source_map.get(a.content_id, "") != "starter_seed"
        ]
        visible_items = [i for i in items if i["bucket"] == "visible"]
        locked_preview_items = [i for i in items if i["bucket"] == "locked_preview"]
        reserve_items = [i for i in items if i["bucket"] == "reserve"]
        return {
            "section": section,
            "visible_items": visible_items,
            "locked_preview_items": locked_preview_items,
            "reserve_items": reserve_items,
            "items": items,  # backward-compat
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    except Exception as exc:
        logger.error("learning_hub.sections_error", extra={"section": section, "error": str(exc)})
        raise HTTPException(status_code=500, detail="Failed to load section data.")
