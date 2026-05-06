"""
Content Factory domain enumerations.
Stored as string values in DB.
"""
import enum


class ContentGenerationStrategy(str, enum.Enum):
    """Strategy used to drive content generation."""

    TOPIC_BASED = "topic_based"
    GAP_BASED = "gap_based"
    CURRICULUM_BASED = "curriculum_based"
    ON_DEMAND = "on_demand"


class JobStatus(str, enum.Enum):
    """Status of a content generation job."""

    PENDING = "pending"
    RUNNING = "running"
    REVIEWING = "reviewing"  # system validation / quality checking
    AWAITING_HUMAN_APPROVAL = "awaiting_human_approval"
    PUBLISHING = "publishing"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"
