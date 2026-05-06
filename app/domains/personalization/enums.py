"""Enums for the personalization domain."""
import enum


class PersonalizationStatus(str, enum.Enum):
    NO_PROFILE = "no_profile"
    ACTIVE = "active"
    INITIALIZING = "initializing"
    STALE = "stale"
    FAILED = "failed"
    RESET_PENDING = "reset_pending"


class AssignmentStatus(str, enum.Enum):
    ASSIGNED = "assigned"
    STARTED = "started"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    SUPERSEDED = "superseded"


class AssignmentBucket(str, enum.Enum):
    VISIBLE = "visible"
    LOCKED_PREVIEW = "locked_preview"
    RESERVE = "reserve"


class SectionReadinessStatus(str, enum.Enum):
    NOT_STARTED = "not_started"
    PREPARING = "preparing"
    PARTIAL_READY = "partial_ready"
    READY = "ready"
    STALE = "stale"
    FAILED = "failed"


class PersonalizationJobType(str, enum.Enum):
    START = "start"
    RECOMPUTE = "recompute"
    RESET = "reset"
    EXPAND_ASSIGNMENTS = "expand_assignments"
    REBUILD_SLATE = "rebuild_slate"
    RECONCILE_UNLOCKS = "reconcile_unlocks"


class PersonalizationJobStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class UnlockTriggerType(str, enum.Enum):
    COMPLETION_COUNT = "completion_count"
    ENGAGEMENT_COUNT = "engagement_count"
    TIME_ELAPSED = "time_elapsed"
    MANUAL_ADMIN = "manual_admin"
    PROFILE_EVENT = "profile_event"


class UnlockSelection(str, enum.Enum):
    NEXT_BY_POSITION = "next_by_position"
    HIGHEST_SCORE = "highest_score"
    RANDOM_WEIGHTED = "random_weighted"


class ProfileChangeSeverity(str, enum.Enum):
    NONE = "none"
    MINOR_RECOMPUTE = "minor_recompute"
    MAJOR_RESET = "major_reset"


class SectionKey(str, enum.Enum):
    MICRO_COURSES = "micro_courses"
    GROWTH_RECOMMENDATIONS = "growth_recommendations"
    TUTORIALS = "tutorials"
    RESEARCH_INSIGHTS = "research_insights"
    SPECIALIST_TRACKS = "specialist_tracks"


# Maps frontend section key (from ProfessionalLearningHub) to SectionKey enum
FRONTEND_SECTION_MAP: dict[str, str] = {
    "personalized-micro-courses": SectionKey.MICRO_COURSES,
    "ai-growth-recommendations": SectionKey.GROWTH_RECOMMENDATIONS,
    "ai-guided-tutorials-demonstrations": SectionKey.TUTORIALS,
    "research-insights-library": SectionKey.RESEARCH_INSIGHTS,
    "specialist-deep-dive-tracks": SectionKey.SPECIALIST_TRACKS,
}

# Content types allowed per section
SECTION_CONTENT_TYPES: dict[str, list[str]] = {
    SectionKey.MICRO_COURSES: ["micro_course"],
    SectionKey.GROWTH_RECOMMENDATIONS: ["learning_path", "path_module"],
    SectionKey.TUTORIALS: ["ai_guided_tutorial"],
    SectionKey.RESEARCH_INSIGHTS: ["research", "resource"],
    SectionKey.SPECIALIST_TRACKS: ["learning_path", "path_module"],
}

# Trigger event types per unlock trigger type
TRIGGER_EVENT_TYPES: dict[str, list[str]] = {
    UnlockTriggerType.COMPLETION_COUNT: ["content_completed"],
    UnlockTriggerType.ENGAGEMENT_COUNT: ["content_completed", "content_started", "card_clicked"],
    UnlockTriggerType.TIME_ELAPSED: [],          # Evaluated by time math, not events
    UnlockTriggerType.MANUAL_ADMIN: [],          # Always true when admin calls
    UnlockTriggerType.PROFILE_EVENT: ["profile_updated", "profile_completed"],
}
