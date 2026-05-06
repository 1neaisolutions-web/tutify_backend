"""
Publishing Service: convert generated draft to canonical content_registry item.
Uses ContentRegistryService.create_item and publish_item.
"""
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domains.content_registry.enums import ContentStatus, ContentType
from app.domains.content_registry.schemas import ContentRegistryCreate
from app.domains.content_registry.services import (
    ContentRegistryService,
    ContentRegistryServiceError,
)

logger = get_logger(__name__)


class PublishingServiceError(Exception):
    """Raised when publishing fails."""
    pass


class PublishingService:
    """Convert generated content to content_registry item and publish."""

    def __init__(self, db: Session):
        self.db = db
        self._registry = ContentRegistryService(db)

    def _slug(self, topic: str) -> str:
        """Simple slug from topic for content_id."""
        base = "".join(c if c.isalnum() or c in " -" else "" for c in topic.strip())
        return base.replace(" ", "-").lower()[:80] or "micro-course"

    def _duration_for_type(self, content_type: str, duration: int | None) -> int:
        ct = (content_type or "").strip().lower()
        val = int(duration or 0)
        if ct == ContentType.MICRO_COURSE.value:
            return min(12, max(5, val or 8))
        if ct == ContentType.AI_GUIDED_TUTORIAL.value:
            return min(25, max(8, val or 14))
        if ct in (ContentType.LEARNING_PATH.value, ContentType.PATH_MODULE.value):
            return min(180, max(60, val or 90))
        if ct in (ContentType.RESEARCH.value, ContentType.RESOURCE.value):
            return min(10, max(5, val or 7))
        return max(5, val or 10)

    def publish_micro_course(
        self,
        full_content: Dict[str, Any],
        topic: str,
        subject: Optional[str] = None,
        grade_band: Optional[str] = None,
        difficulty: Optional[str] = None,
        locale: str = "en",
        job_id: Optional[UUID] = None,
    ) -> str:
        """
        Create and publish a content_registry item from full_content.
        Returns content_id.
        """
        base_id = self._slug(topic)
        content_id = f"factory-{base_id}"
        if job_id:
            content_id = f"factory-{job_id.hex[:8]}-{base_id}"[:150]
        else:
            # Ensure uniqueness
            existing = self._registry.get_item_by_content_id(content_id)
            if existing:
                import uuid
                content_id = f"factory-{uuid.uuid4().hex[:8]}-{base_id}"[:150]

        title = topic[:300] if len(topic) <= 300 else topic[:297] + "..."
        summary = ""
        curriculum = full_content.get("curriculum") or {}
        if isinstance(curriculum.get("learning_objectives"), list) and curriculum["learning_objectives"]:
            summary = " ".join(str(o) for o in curriculum["learning_objectives"][:3])[:2000]

        try:
            data = ContentRegistryCreate(
                content_id=content_id,
                content_type=ContentType.MICRO_COURSE.value,
                schema_version="1.0",
                locale=locale,
                status=ContentStatus.DRAFT.value,
                title=title,
                subtitle=None,
                summary=summary or None,
                category=subject or None,
                difficulty=difficulty,
                impact_level=None,
                tags={"grade_band": grade_band} if grade_band else {},
                alignment={},
                json_blob=full_content,
                source_type="content_factory",
                source_ref=str(job_id) if job_id else None,
            )
            item = self._registry.create_item(data)
            self._registry.publish_item(item.id)
            logger.info("Published micro-course content_id=%s job_id=%s", content_id, job_id)
            return item.content_id
        except ContentRegistryServiceError as e:
            raise PublishingServiceError(str(e)) from e

    def publish_generated_content(
        self,
        *,
        content_type: str,
        topic: str,
        subject: Optional[str] = None,
        grade_band: Optional[str] = None,
        difficulty: Optional[str] = None,
        locale: str = "en",
        job_id: Optional[UUID] = None,
        generated_blob: Optional[Dict[str, Any]] = None,
        summary: Optional[str] = None,
        subtitle: Optional[str] = None,
        estimated_duration_min: Optional[int] = None,
        tags: Optional[Dict[str, Any]] = None,
    ) -> str:
        base_id = self._slug(topic)
        content_id = f"factory-{base_id}"
        if job_id:
            content_id = f"factory-{job_id.hex[:8]}-{base_id}"[:150]
        title = topic[:300] if len(topic) <= 300 else topic[:297] + "..."
        data = ContentRegistryCreate(
            content_id=content_id,
            content_type=content_type,
            schema_version="1.0",
            locale=locale,
            status=ContentStatus.DRAFT.value,
            title=title,
            subtitle=subtitle,
            summary=(summary or "")[:2000] or None,
            category=subject or None,
            estimated_duration_min=self._duration_for_type(content_type, estimated_duration_min),
            difficulty=difficulty,
            impact_level=None,
            tags={**(tags or {}), **({"grade_band": grade_band} if grade_band else {})},
            alignment={},
            json_blob=generated_blob or {},
            source_type="content_factory",
            source_ref=str(job_id) if job_id else None,
        )
        try:
            item = self._registry.create_item(data)
            self._registry.publish_item(item.id)
            logger.info("Published generated content_id=%s type=%s", item.content_id, content_type)
            return item.content_id
        except ContentRegistryServiceError as e:
            raise PublishingServiceError(str(e)) from e
