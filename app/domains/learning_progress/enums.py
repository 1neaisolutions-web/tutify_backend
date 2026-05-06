"""Enumerations for learning progress and engagement analytics."""
import enum


class LearningSessionStatus(str, enum.Enum):
    """Lifecycle status of a learning session."""

    STARTED = "started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class LearningEventType(str, enum.Enum):
    """Granular learning event types."""

    CONTENT_OPENED = "content_opened"
    LESSON_OPENED = "lesson_opened"
    LESSON_COMPLETED = "lesson_completed"
    STEP_OPENED = "step_opened"
    STEP_COMPLETED = "step_completed"
    QUIZ_ATTEMPTED = "quiz_attempted"
    QUIZ_PASSED = "quiz_passed"
    QUIZ_FAILED = "quiz_failed"
    REFLECTION_SUBMITTED = "reflection_submitted"
    CONTENT_COMPLETED = "content_completed"


class RecommendationEventType(str, enum.Enum):
    """Events around recommendation interactions."""

    SHOWN = "shown"
    CLICKED = "clicked"
    DISMISSED = "dismissed"
    STARTED_LEARNING = "started_learning"
    COMPLETED_LEARNING = "completed_learning"

