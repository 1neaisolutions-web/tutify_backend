"""
Teacher Intelligence domain enumerations.
"""
import enum


class PipelineRunStatus(str, enum.Enum):
    """Status of an ML pipeline run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class FeatureSchemaVersion(str, enum.Enum):
    """Version of the feature snapshot schema for ML consumption."""

    V1 = "feature_schema_v1"
