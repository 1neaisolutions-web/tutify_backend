"""
Content Registry domain enumerations.
Stored as string values in DB.
"""
import enum


class ContentType(str, enum.Enum):
    """Type of learning content."""

    MICRO_COURSE = "micro_course"
    AI_GUIDED_TUTORIAL = "ai_guided_tutorial"
    LEARNING_PATH = "learning_path"
    PATH_MODULE = "path_module"
    RESEARCH = "research"
    RESOURCE = "resource"


class ContentStatus(str, enum.Enum):
    """Publication status of content."""

    DRAFT = "draft"
    REVIEWED = "reviewed"
    PUBLISHED = "published"
    ARCHIVED = "archived"
