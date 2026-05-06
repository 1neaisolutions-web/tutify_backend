"""
Canonical Learning Hub delivery routes for the frontend.

Backend owns route truth: registry items expose a validated path under /learning-hub/*
(or an explicit delivery.route in json_blob). Never emit generic /learning-hub/content/{id}
unless a matching frontend route exists (currently unsupported).
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

# Avoid importing ContentRegistryItem here (circular import via app.db.base).

# Starter seed slugs -> first-class React routes (see 1ne-frontend/src/routes/config.jsx)
SLUG_TO_ROUTE: Dict[str, str] = {
    "classroom-management-quick-wins": "/learning-hub/classroom-management",
    "classroom-management-learning-path": "/learning-hub/student-engagement-path",
    "student-engagement-strategies": "/learning-hub/student-engagement-course",
    "formative-assessment-essentials": "/learning-hub/assessment-strategies",
    "differentiation-made-simple": "/learning-hub/differentiation-course",
    "lesson-planning-with-ai": "/learning-hub/lesson-planner-tutorial",
    # Learning-path slugs must resolve to growth-path destinations (never micro-course pages).
    "lesson-planning-learning-path": "/learning-hub/ai-assessment-path",
}

FACTORY_CATEGORY_TO_MICRO_COURSE_ROUTE: Dict[str, str] = {
    # Registry `category` is set from `subject` in PublishingService.
    "differentiation": "/learning-hub/differentiation-course",
    "classroom_management": "/learning-hub/classroom-management",
    "student_engagement": "/learning-hub/student-engagement-course",
    "assessment_strategies": "/learning-hub/assessment-strategies",
    # For lesson-planning micro-courses we route to the closest existing surface.
    "lesson_planning": "/learning-hub/digital-literacy-course",
}

FACTORY_CATEGORY_TO_GROWTH_PATH_ROUTE: Dict[str, str] = {
    "student_engagement": "/learning-hub/student-engagement-path",
    "differentiation": "/learning-hub/advanced-differentiation-path",
    "assessment_strategies": "/learning-hub/ai-assessment-path",
    # Safe fallback for adjacent generated themes.
    "lesson_planning": "/learning-hub/ai-assessment-path",
    "classroom_management": "/learning-hub/student-engagement-path",
}

GROWTH_PATH_ROUTES = {
    "/learning-hub/student-engagement-path",
    "/learning-hub/advanced-differentiation-path",
    "/learning-hub/ai-assessment-path",
}

FACTORY_CATEGORY_TO_TUTORIAL_ROUTE: Dict[str, str] = {
    "differentiation": "/learning-hub/differentiation-tutorial",
    "lesson_planning": "/learning-hub/lesson-planner-tutorial",
    "assessment_strategies": "/learning-hub/assessment-tutorial",
}

_STARTER_SLUG_RE = re.compile(r"^starter-[a-z]{2}-(.+)$", re.IGNORECASE)
_NON_SLUG_RE = re.compile(r"[^a-z0-9\-]+")


def parse_starter_slug(content_id: str) -> Optional[str]:
    """Extract slug from starter-{locale}-{slug} content_id pattern."""
    if not content_id:
        return None
    m = _STARTER_SLUG_RE.match(str(content_id).strip())
    return m.group(1) if m else None


def validate_frontend_route(route: Optional[str]) -> Optional[str]:
    """Return normalized route if allowed, else None."""
    if not route or not isinstance(route, str):
        return None
    r = route.strip()
    if not r.startswith("/"):
        r = f"/{r}"
    # Unsupported generic content shell in current frontend
    if "/learning-hub/content/" in r:
        return None
    if r == "/learning-hub" or r.startswith("/learning-hub/"):
        return r
    if r.startswith("/profile"):
        return r
    return None


def resolve_delivery_slug(item: Any) -> Optional[str]:
    blob: Dict[str, Any] = item.json_blob or {}
    delivery = blob.get("delivery") or {}
    slug = delivery.get("slug")
    if slug and isinstance(slug, str) and slug.strip():
        return slug.strip()
    tags = item.tags or {}
    if isinstance(tags, dict):
        tslug = tags.get("slug")
        if tslug and isinstance(tslug, str) and tslug.strip():
            return tslug.strip()
    return parse_starter_slug(item.content_id)


def resolve_learning_hub_route(item: Any) -> str:
    """
    Resolve a safe, frontend-supported path for this registry item.

    Priority:
    1. json_blob.delivery.route (validated)
    2. slug from delivery / tags / content_id -> SLUG_TO_ROUTE
    3. content_type hint -> safe hub default (no dead-end generic routes)
    """
    blob: Dict[str, Any] = item.json_blob or {}
    delivery = blob.get("delivery") or {}
    explicit = validate_frontend_route(delivery.get("route"))
    slug = resolve_delivery_slug(item)

    ct = str(item.content_type or "").strip().lower()

    def _route_allowed_for_type(route: Optional[str], content_type: str) -> bool:
        if not route:
            return False
        if content_type in ("learning_path", "path_module"):
            return route in GROWTH_PATH_ROUTES
        return True

    # AI-generated content from content_factory does not have starter slug mappings.
    # We route these items based on their semantic registry `category` when possible.
    source_type = getattr(item, "source_type", None)
    if explicit and _route_allowed_for_type(explicit, ct):
        return explicit

    if slug and slug in SLUG_TO_ROUTE:
        mapped = SLUG_TO_ROUTE[slug]
        if _route_allowed_for_type(mapped, ct):
            return mapped

    if source_type == "content_factory":
        raw_slug = (slug or str(getattr(item, "content_id", "") or "")).strip().lower().replace("_", "-")
        content_slug = _NON_SLUG_RE.sub("-", raw_slug).strip("-") or "generated-content"
        cat = str(getattr(item, "category", "") or "").strip().lower()
        if ct == "ai_guided_tutorial":
            return f"/learning-hub/ai-guided-tutorials-demonstrations/{content_slug}"
        if ct == "learning_path":
            if cat in ("specialist", "specialist_tracks"):
                return f"/learning-hub/specialist-deep-dive-tracks/{content_slug}"
            return f"/learning-hub/ai-growth-recommendations/{content_slug}"
        if ct == "micro_course":
            return f"/learning-hub/personalized-micro-courses/{content_slug}"
        if ct in ("research", "resource"):
            return f"/learning-hub/research-insights-library/{content_slug}"
        return "/learning-hub"

    if ct == "ai_guided_tutorial":
        return "/learning-hub"
    if ct in ("micro_course", "learning_path", "path_module"):
        return "/learning-hub"

    return "/learning-hub"


def build_delivery_blob(
    slug: str,
    *,
    media_steps: Optional[list] = None,
    publishing_notes: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Structured json_blob.delivery fragment for registry create/update."""
    route = SLUG_TO_ROUTE.get(slug)
    payload: Dict[str, Any] = {
        "slug": slug,
        "route": route,
        "route_source": "registry_slug_map",
    }
    if media_steps:
        payload["media_steps"] = media_steps
    if publishing_notes:
        payload["publishing"] = publishing_notes
    return {"delivery": payload}
