"""
Content Registry Service: CRUD and publish for canonical content items.
"""
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.core.logging import get_logger
from app.domains.content_registry.models import ContentRegistryItem
from app.domains.content_registry.schemas import ContentRegistryCreate, ContentRegistryUpdate
from app.domains.content_registry.enums import ContentStatus, ContentType

logger = get_logger(__name__)


class ContentRegistryServiceError(Exception):
    """Raised when registry operation fails (e.g. duplicate content_id)."""
    pass


class ContentRegistryService:
    """CRUD and publish for content registry items."""

    def __init__(self, db: Session):
        self.db = db

    def create_item(self, data: ContentRegistryCreate) -> ContentRegistryItem:
        """Create a new content registry item. Raises ContentRegistryServiceError if content_id exists."""
        existing = (
            self.db.query(ContentRegistryItem)
            .filter(ContentRegistryItem.content_id == data.content_id)
            .first()
        )
        if existing:
            raise ContentRegistryServiceError("Content ID already exists: " + data.content_id)

        item = ContentRegistryItem(
            content_id=data.content_id,
            content_type=data.content_type,
            schema_version=data.schema_version,
            content_version_major=data.content_version_major,
            content_version_minor=data.content_version_minor,
            content_version_patch=data.content_version_patch,
            locale=data.locale,
            status=data.status,
            title=data.title,
            subtitle=data.subtitle,
            summary=data.summary,
            category=data.category,
            estimated_duration_min=data.estimated_duration_min,
            difficulty=data.difficulty,
            impact_level=data.impact_level,
            tags=data.tags,
            alignment=data.alignment,
            json_blob=data.json_blob,
            source_type=data.source_type,
            source_ref=data.source_ref,
        )
        self.db.add(item)
        try:
            self.db.commit()
            self.db.refresh(item)
        except IntegrityError:
            # Concurrency-safe idempotency:
            # if another transaction inserted the same `content_id` after our pre-check,
            # return the existing row instead of failing the request.
            try:
                self.db.rollback()
            except Exception:
                pass
            existing = self.get_item_by_content_id(data.content_id)
            if existing:
                return existing
            raise
        logger.info("Created content registry item id=%s content_id=%s", item.id, item.content_id)
        return item

    def get_item_by_id(self, id: UUID) -> Optional[ContentRegistryItem]:
        """Get item by primary key."""
        return self.db.query(ContentRegistryItem).filter(ContentRegistryItem.id == id).first()

    def get_item_by_content_id(self, content_id: str) -> Optional[ContentRegistryItem]:
        """Get item by content_id."""
        return (
            self.db.query(ContentRegistryItem)
            .filter(ContentRegistryItem.content_id == content_id)
            .first()
        )

    def list_items(
        self,
        content_type: Optional[str] = None,
        status: Optional[str] = None,
        locale: Optional[str] = None,
        category: Optional[str] = None,
        difficulty: Optional[str] = None,
        source_type: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[ContentRegistryItem]:
        """List items with optional filters. Returns items only."""
        q = self.db.query(ContentRegistryItem)
        if content_type is not None:
            q = q.filter(ContentRegistryItem.content_type == content_type)
        if status is not None:
            q = q.filter(ContentRegistryItem.status == status)
        if locale is not None:
            q = q.filter(ContentRegistryItem.locale == locale)
        if category is not None:
            q = q.filter(ContentRegistryItem.category == category)
        if difficulty is not None:
            q = q.filter(ContentRegistryItem.difficulty == difficulty)
        if source_type is not None:
            q = q.filter(ContentRegistryItem.source_type == source_type)
        return q.order_by(ContentRegistryItem.created_at.desc()).offset(skip).limit(limit).all()

    def update_item(self, id: UUID, data: ContentRegistryUpdate) -> Optional[ContentRegistryItem]:
        """Update item by id. Returns updated item or None."""
        item = self.get_item_by_id(id)
        if not item:
            return None
        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if hasattr(item, key):
                setattr(item, key, value)
        self.db.commit()
        self.db.refresh(item)
        logger.info("Updated content registry item id=%s", id)
        return item

    def delete_item(self, id: UUID) -> bool:
        """Hard delete item by id."""
        item = self.get_item_by_id(id)
        if not item:
            return False
        self.db.delete(item)
        self.db.commit()
        logger.info("Deleted content registry item id=%s", id)
        return True

    def publish_item(self, id: UUID) -> Optional[ContentRegistryItem]:
        """Set status=PUBLISHED and published_at if not set. Returns updated item or None."""
        item = self.get_item_by_id(id)
        if not item:
            return None
        item.status = ContentStatus.PUBLISHED.value
        if item.published_at is None:
            item.published_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(item)
        logger.info("Published content registry item id=%s", id)
        return item

    def seed_sample_content(self) -> List[ContentRegistryItem]:
        """
        Insert minimal sample items if not present: one MICRO_COURSE, one AI_GUIDED_TUTORIAL,
        one LEARNING_PATH. Idempotent (skips existing content_id). Returns list of created items.
        """
        created: List[ContentRegistryItem] = []
        samples = [
            {
                "content_id": "sample-micro-course-classroom-mgmt",
                "content_type": ContentType.MICRO_COURSE.value,
                "title": "Classroom Management Essentials",
                "subtitle": "Build a positive and productive learning environment.",
                "summary": "A short micro-course on core classroom management strategies.",
                "category": "classroom_management",
                "estimated_duration_min": 30,
                "difficulty": "beginner",
            },
            {
                "content_id": "sample-ai-tutorial-lesson-planning",
                "content_type": ContentType.AI_GUIDED_TUTORIAL.value,
                "title": "Lesson Planning with AI",
                "subtitle": "Design effective lessons with guided support.",
                "summary": "AI-guided tutorial for structuring and improving lesson plans.",
                "category": "lesson_planning",
                "estimated_duration_min": 45,
                "difficulty": "intermediate",
            },
            {
                "content_id": "sample-learning-path-assessment",
                "content_type": ContentType.LEARNING_PATH.value,
                "title": "Assessment Design",
                "subtitle": "From formative checks to summative assessments.",
                "summary": "A learning path covering assessment design and implementation.",
                "category": "assessment",
                "estimated_duration_min": 120,
                "difficulty": "intermediate",
            },
        ]
        for s in samples:
            if self.get_item_by_content_id(s["content_id"]):
                continue
            data = ContentRegistryCreate(
                content_id=s["content_id"],
                content_type=s["content_type"],
                schema_version="1.0",
                locale="en",
                status=ContentStatus.PUBLISHED.value,
                title=s["title"],
                subtitle=s.get("subtitle"),
                summary=s.get("summary"),
                category=s.get("category"),
                estimated_duration_min=s.get("estimated_duration_min"),
                difficulty=s.get("difficulty"),
            )
            item = self.create_item(data)
            published = self.publish_item(item.id)
            created.append(published if published else item)
        return created

    def seed_learning_hub_starter_content(self, locales: Optional[List[str]] = None) -> List[ContentRegistryItem]:
        """
        Seed starter Learning Hub content across locales.

        - Idempotent: skips content_ids that already exist.
        - Covers core themes: classroom management, engagement, assessment, differentiation, lesson planning.
        - Includes all primary types: micro_course, ai_guided_tutorial, learning_path.
        """
        created: List[ContentRegistryItem] = []
        target_locales = locales or ["en"]

        # Base starter definitions (locale-agnostic; content_id gets locale suffix).
        starters: List[Dict[str, Any]] = [
            # Classroom management (micro course + path)
            {
                "slug": "classroom-management-quick-wins",
                "content_type": ContentType.MICRO_COURSE.value,
                "title": "Quick wins: Classroom management essentials",
                "subtitle": "Practical strategies to stabilize your classroom this week.",
                "summary": "A focused micro-course on routines, expectations, and low-prep strategies for calm classrooms.",
                "category": "classroom_management",
                "estimated_duration_min": 20,
                "difficulty": "beginner",
                "tags": {"theme": "classroom_management", "starter": True},
            },
            {
                "slug": "classroom-management-learning-path",
                "content_type": ContentType.LEARNING_PATH.value,
                "title": "Classroom management deep dive",
                "subtitle": "From chaos to calm: building sustainable systems.",
                "summary": "A structured learning path on proactive management, relationships, and routines.",
                "category": "classroom_management",
                "estimated_duration_min": 120,
                "difficulty": "intermediate",
                "tags": {"theme": "classroom_management", "starter": True},
            },
            # Student engagement
            {
                "slug": "student-engagement-strategies",
                "content_type": ContentType.MICRO_COURSE.value,
                "title": "Engaging reluctant learners",
                "subtitle": "Low-lift tactics to get every student participating.",
                "summary": "Micro-course on engagement hooks, choice, and collaborative structures.",
                "category": "student_engagement",
                "estimated_duration_min": 25,
                "difficulty": "beginner",
                "tags": {"theme": "student_engagement", "starter": True},
            },
            # Assessment strategies
            {
                "slug": "formative-assessment-essentials",
                "content_type": ContentType.MICRO_COURSE.value,
                "title": "Formative assessment strategies that work",
                "subtitle": "Check for understanding without slowing down your lesson.",
                "summary": "A short course on quick checks, exit tickets, and feedback loops.",
                "category": "assessment_strategies",
                "estimated_duration_min": 30,
                "difficulty": "beginner",
                "tags": {"theme": "assessment", "starter": True},
            },
            # Differentiation
            {
                "slug": "differentiation-made-simple",
                "content_type": ContentType.MICRO_COURSE.value,
                "title": "Differentiation made simple",
                "subtitle": "Scalable approaches to meet diverse needs in one classroom.",
                "summary": "Micro-course on tiered tasks, scaffolds, and flexible grouping.",
                "category": "differentiation",
                "estimated_duration_min": 35,
                "difficulty": "beginner",
                "tags": {"theme": "differentiation", "starter": True},
            },
            # Lesson planning (tutorial + path)
            {
                "slug": "lesson-planning-with-ai",
                "content_type": ContentType.AI_GUIDED_TUTORIAL.value,
                "title": "Lesson planning with AI: a guided tutorial",
                "subtitle": "See how to turn standards into engaging lessons step by step.",
                "summary": "AI-guided tutorial for chunking objectives, selecting strategies, and planning checks.",
                "category": "lesson_planning",
                "estimated_duration_min": 40,
                "difficulty": "intermediate",
                "tags": {"theme": "lesson_planning", "starter": True},
            },
            {
                "slug": "lesson-planning-learning-path",
                "content_type": ContentType.LEARNING_PATH.value,
                "title": "Lesson planning mastery path",
                "subtitle": "From yearly maps to daily plans that actually work.",
                "summary": "A multi-step learning path on backwards design, alignment, and daily planning.",
                "category": "lesson_planning",
                "estimated_duration_min": 150,
                "difficulty": "intermediate",
                "tags": {"theme": "lesson_planning", "starter": True},
            },
        ]

        for locale in target_locales:
            for s in starters:
                content_id = f"starter-{locale}-{s['slug']}"
                if self.get_item_by_content_id(content_id):
                    continue
                from app.domains.learning_hub.route_resolver import build_delivery_blob

                tags = {**(s.get("tags") or {}), "slug": s["slug"]}
                json_blob = build_delivery_blob(s["slug"])
                data = ContentRegistryCreate(
                    content_id=content_id,
                    content_type=s["content_type"],
                    schema_version="1.0",
                    locale=locale,
                    status=ContentStatus.PUBLISHED.value,
                    title=s["title"],
                    subtitle=s.get("subtitle"),
                    summary=s.get("summary"),
                    category=s.get("category"),
                    estimated_duration_min=s.get("estimated_duration_min"),
                    difficulty=s.get("difficulty"),
                    tags=tags,
                    alignment={},
                    json_blob=json_blob,
                    source_type="starter_seed",
                    source_ref=None,
                )
                item = self.create_item(data)
                # publish_item is idempotent and ensures published_at is set
                published = self.publish_item(item.id)
                created.append(published if published else item)

        if created:
            logger.info(
                "Seeded starter Learning Hub content count=%s locales=%s",
                len(created),
                target_locales,
            )
        return created

    def validate_learning_hub_ready(self, locales: Optional[List[str]] = None) -> bool:
        """
        Validate that Learning Hub has enough published content per locale.

        - At least MIN_CONTENT_PER_LOCALE items per locale.
        - All primary content types present (micro_course, ai_guided_tutorial, learning_path) for the default locale.
        """
        from app.core.config import settings as app_settings  # lazy import to avoid cycles

        target_locales = locales or ["en"]
        ok = True
        for locale in target_locales:
            q = (
                self.db.query(ContentRegistryItem)
                .filter(
                    ContentRegistryItem.status == ContentStatus.PUBLISHED.value,
                    ContentRegistryItem.locale == locale,
                )
            )
            count = q.count()
            if count < app_settings.MIN_CONTENT_PER_LOCALE:
                logger.warning(
                    "Learning Hub validation failed for locale=%s: published_count=%s < MIN_CONTENT_PER_LOCALE=%s",
                    locale,
                    count,
                    app_settings.MIN_CONTENT_PER_LOCALE,
                )
                ok = False

        # Check type coverage for default locale
        default_locale = target_locales[0]
        for ctype in (ContentType.MICRO_COURSE.value, ContentType.AI_GUIDED_TUTORIAL.value, ContentType.LEARNING_PATH.value):
            exists = (
                self.db.query(ContentRegistryItem)
                .filter(
                    ContentRegistryItem.status == ContentStatus.PUBLISHED.value,
                    ContentRegistryItem.locale == default_locale,
                    ContentRegistryItem.content_type == ctype,
                )
                .first()
            )
            if not exists:
                logger.warning(
                    "Learning Hub validation failed for locale=%s: missing content_type=%s",
                    default_locale,
                    ctype,
                )
                ok = False

        if ok:
            logger.info("Learning Hub validation passed for locales=%s", target_locales)
        return ok

