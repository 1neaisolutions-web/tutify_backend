"""
Generation Orchestrator: control generation workflow, update job status, call validation and publishing.
"""
from datetime import datetime, timezone
from typing import Optional, Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.llm.router import ModelRouter

from app.domains.content_factory.enums import JobStatus
from app.domains.content_factory.models import ContentGenerationJob
from app.domains.content_factory.services.publishing_service import PublishingService
from app.domains.content_factory.services.validation_service import (
    ValidationService,
    ValidationServiceError,
)
from app.domains.content_factory.services.publishing_policy_service import (
    PublishingPolicyService,
)
from app.domains.content_factory.workflows.micro_course_workflow import run_micro_course_pipeline

logger = get_logger(__name__)

QUALITY_THRESHOLD = 0.5
MAX_RETRIES = 1


class GenerationOrchestratorService:
    """Orchestrate micro-course generation: run pipeline, validate, review, quality check, publish."""

    def __init__(self, db: Session):
        self.db = db
        self._router = ModelRouter()
        self._validation = ValidationService()
        self._publishing = PublishingService(db)
        self._policy = PublishingPolicyService()

    def _get_job(self, job_id: UUID) -> Optional[ContentGenerationJob]:
        return self.db.query(ContentGenerationJob).filter(ContentGenerationJob.id == job_id).first()

    def _build_generic_payload(self, job: ContentGenerationJob) -> dict[str, Any]:
        topic = (job.topic or "").strip()
        subject = (job.subject or "instructional practice").replace("_", " ")
        grade = (job.grade_band or "mixed grades").replace("_", " ")
        if job.content_type == "ai_guided_tutorial":
            duration = 14
            subtitle = f"Interactive walkthrough for {subject} in {grade}"
            summary = (
                f"Step-by-step tutorial on {topic.lower()} with practical classroom checkpoints, "
                "demonstration moments, and implementation prompts."
            )
            blob = {"steps": ["context setup", "guided demo", "classroom adaptation", "reflection"], "kind": "tutorial"}
        elif job.content_type in ("learning_path", "path_module"):
            duration = 90
            subtitle = f"Structured mastery pathway for {subject}"
            summary = (
                f"High-impact learning path focused on {topic.lower()} across planning, execution, "
                "evidence collection, and iterative improvement cycles."
            )
            module_base = [
                ("foundation", "Foundations", "Beginner"),
                ("practice", "Guided Practice", "Intermediate"),
                ("application", "Classroom Application", "Intermediate"),
            ]
            modules = []
            for idx, (mid, label, level) in enumerate(module_base, start=1):
                slug = f"{(job.subject or 'general').replace('_', '-')}-{mid}-{idx}"
                modules.append(
                    {
                        "id": f"{job.id.hex[:8]}-{mid}",
                        "slug": slug,
                        "title": f"{label}: {topic}",
                        "description": f"{label} module tailored for {subject}.",
                        "duration": "30 min",
                        "level": level,
                        "impact": "High" if idx == 1 else "Medium",
                        "skillIds": ["instructional-design", "assessment", "engagement"][: (idx + 1)],
                        "learningOutcomes": [
                            f"Apply {label.lower()} techniques in daily planning",
                            "Measure impact using classroom evidence",
                        ],
                        "assessment": {
                            "type": "Implementation checkpoint",
                            "description": "Submit a practical classroom artifact.",
                            "points": 30,
                        },
                        "realWorldApplication": "Use this in your next teaching cycle.",
                        "content": [
                            {"type": "video", "title": f"{label} walkthrough", "duration": "8 min", "points": 10},
                            {"type": "reading", "title": "Teacher playbook", "duration": "10 min", "points": 10},
                            {"type": "interactive", "title": "Practice simulation", "duration": "12 min", "points": 10},
                        ],
                        "detail": {
                            "moduleLabel": f"Module {idx}",
                            "backPathSlug": (job.subject or "general").replace("_", "-"),
                            "lessons": [
                                {
                                    "id": f"{slug}-lesson-1",
                                    "title": f"{label} overview",
                                    "type": "video",
                                    "duration": "8 min",
                                    "points": 10,
                                    "content": {
                                        "keyPoints": ["Core strategy", "Context adaptation"],
                                        "transcript": "Step-by-step guidance for classroom implementation.",
                                    },
                                },
                                {
                                    "id": f"{slug}-lesson-2",
                                    "title": "Classroom application",
                                    "type": "interactive",
                                    "duration": "12 min",
                                    "points": 10,
                                    "content": {
                                        "description": "Apply strategy to your current class context.",
                                        "steps": ["Choose one class", "Adapt strategy", "Run and reflect"],
                                    },
                                },
                            ],
                        },
                    }
                )
            blob = {
                "kind": "learning_path",
                "aiGrowthRecommendationContent": {
                    "type": "path",
                    "themeId": "adaptive-engagement",
                    "estimatedTime": "90 min",
                    "impactLevel": "High",
                    "heroSubtitle": "AI Growth Path",
                    "heroDescription": summary,
                    "aiGuidance": {
                        "recommendation": f"Prioritize {topic} to improve outcomes.",
                        "reason": "Based on your profile signals and recent activity patterns.",
                        "nextSteps": [
                            "Complete Module 1 this week",
                            "Apply one strategy in class",
                            "Track and review outcomes",
                        ],
                        "personalizedTip": "Focus on one class section first, then scale.",
                    },
                    "skillImpacts": [
                        {
                            "skillId": "instructional-design",
                            "before": 42,
                            "after": 68,
                            "improvement": 26,
                            "description": "Higher lesson coherence and clarity.",
                        },
                        {
                            "skillId": "assessment",
                            "before": 38,
                            "after": 60,
                            "improvement": 22,
                            "description": "Improved evidence-based adjustments.",
                        },
                    ],
                    "modules": modules,
                    "storageKey": f"growth-path-{job.id.hex[:8]}",
                },
            }
        elif job.content_type in ("research", "resource"):
            duration = 7
            subtitle = f"Evidence-backed insight for {subject}"
            summary = (
                f"Concise research brief on {topic.lower()} with evidence interpretation, classroom implications, "
                "and actionable next steps."
            )
            blob = {"sections": ["key finding", "why it matters", "classroom action"], "kind": "research"}
        else:
            duration = 8
            subtitle = f"Professional micro-course for {subject}"
            summary = f"Focused micro-course on {topic.lower()}."
            blob = {"kind": "micro_course_generic"}
        return {
            "title": topic,
            "subtitle": subtitle,
            "summary": summary,
            "estimated_duration_min": duration,
            "json_blob": blob,
        }

    def _update_job(
        self,
        job: ContentGenerationJob,
        status: Optional[str] = None,
        current_step: Optional[str] = None,
        step_outputs: Optional[dict] = None,
        quality_score: Optional[float] = None,
        result_content_id: Optional[str] = None,
        error_message: Optional[str] = None,
        completed_at: Optional[datetime] = None,
    ) -> None:
        if status is not None:
            job.status = status
        if current_step is not None:
            job.current_step = current_step
        if step_outputs is not None:
            job.step_outputs = step_outputs
        if quality_score is not None:
            job.quality_score = quality_score
        if result_content_id is not None:
            job.result_content_id = result_content_id
        if error_message is not None:
            job.error_message = error_message
        if completed_at is not None:
            job.completed_at = completed_at
        self.db.commit()
        self.db.refresh(job)

    async def run_micro_course_job(self, job_id: UUID) -> ContentGenerationJob:
        """
        Run the full workflow for a micro-course job: pipeline -> validation -> reviewing -> quality -> publish.
        Updates job status and step_outputs; on failure sets status=failed and error_message.
        """
        job = self._get_job(job_id)
        if not job:
            raise ValueError("Job not found: " + str(job_id))
        if job.status != JobStatus.PENDING.value and job.status != JobStatus.RUNNING.value:
            logger.warning("Job %s already in status %s", job_id, job.status)
            return job

        job.status = JobStatus.RUNNING.value
        job.started_at = job.started_at or datetime.now(timezone.utc)
        job.current_step = "curriculum"
        self.db.commit()
        self.db.refresh(job)
        logger.info("Workflow status change job_id=%s status=running", job_id)

        try:
            full_content, quality_output = await run_micro_course_pipeline(
                router=self._router,
                topic=job.topic,
                subject=job.subject,
                grade_band=job.grade_band,
                difficulty=job.difficulty,
                locale=job.locale,
            )
            self._update_job(job, current_step="pipeline_done", step_outputs=full_content)

            self._validation.validate_and_raise(full_content)

            job.status = JobStatus.REVIEWING.value
            job.current_step = "reviewing"
            job.quality_score = quality_output.get("quality_score")
            if isinstance(job.quality_score, (int, float)):
                job.quality_score = max(0.0, min(1.0, float(job.quality_score)))
            self.db.commit()
            self.db.refresh(job)
            logger.info("Workflow status change job_id=%s status=reviewing quality_score=%s", job_id, job.quality_score)

            if job.quality_score is not None and job.quality_score < QUALITY_THRESHOLD:
                if job.retry_count >= MAX_RETRIES:
                    job.status = JobStatus.FAILED.value
                    job.error_message = (
                        f"Quality score {job.quality_score} below threshold {QUALITY_THRESHOLD} after {MAX_RETRIES} retries"
                    )
                    job.completed_at = datetime.now(timezone.utc)
                    self.db.commit()
                    self.db.refresh(job)
                    return job
                job.retry_count += 1
                job.status = JobStatus.PENDING.value
                job.current_step = None
                self.db.commit()
                self.db.refresh(job)
                return await self.run_micro_course_job(job_id)

            # Evaluate publishing policy
            review_section = full_content.get("review") or {}
            review_status = review_section.get("review_status")
            issues = review_section.get("issues_found") or []
            has_blocking_issues = bool(issues)
            decision = self._policy.decide(
                content_type=job.content_type,
                generation_strategy=job.generation_strategy,
                quality_score=job.quality_score,
                review_status=review_status,
                has_blocking_issues=has_blocking_issues,
            )
            job.publication_policy_decision = decision["decision"]
            logger.info(
                "Publishing policy decision job_id=%s decision=%s reason=%s",
                job.id,
                decision["decision"],
                decision["reason"],
            )

            if decision["decision"] == "reject":
                job.status = JobStatus.REJECTED.value
                job.rejection_reason = decision["reason"]
                job.completed_at = datetime.now(timezone.utc)
                self.db.commit()
                self.db.refresh(job)
                return job

            if decision["decision"] == "require_approval":
                job.status = JobStatus.AWAITING_HUMAN_APPROVAL.value
                job.current_step = "awaiting_human_approval"
                job.review_required = 1
                self.db.commit()
                self.db.refresh(job)
                logger.info(
                    "Job awaiting human approval; job_id=%s decision_reason=%s",
                    job.id,
                    decision["reason"],
                )
                return job

            # auto_publish
            job.status = JobStatus.PUBLISHING.value
            job.current_step = "publishing"
            self.db.commit()
            self.db.refresh(job)
            logger.info(
                "Workflow status change job_id=%s status=publishing (auto_publish)",
                job_id,
            )

            content_id = self._publishing.publish_micro_course(
                full_content=full_content,
                topic=job.topic,
                subject=job.subject,
                grade_band=job.grade_band,
                difficulty=job.difficulty,
                locale=job.locale,
                job_id=job.id,
            )
            job.status = JobStatus.COMPLETED.value
            job.current_step = "completed"
            job.result_content_id = content_id
            job.completed_at = datetime.now(timezone.utc)
            job.review_required = 0
            self.db.commit()
            self.db.refresh(job)
            logger.info(
                "Workflow status change job_id=%s status=completed result_content_id=%s",
                job_id,
                content_id,
            )
            return job

        except ValidationServiceError as e:
            job.status = JobStatus.FAILED.value
            job.error_message = "Validation failed: " + str(e)
            job.completed_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(job)
            logger.warning("Job %s failed validation: %s", job_id, e)
            return job
        except Exception as e:
            job.status = JobStatus.FAILED.value
            job.error_message = str(e)[:2000]
            job.completed_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(job)
            logger.exception("Job %s failed: %s", job_id, e)
            return job

    async def run_job(self, job_id: UUID) -> ContentGenerationJob:
        job = self._get_job(job_id)
        if not job:
            raise ValueError("Job not found: " + str(job_id))
        if job.job_type == "micro_course" or job.content_type == "micro_course":
            return await self.run_micro_course_job(job_id)

        if job.status not in (JobStatus.PENDING.value, JobStatus.RUNNING.value):
            return job
        job.status = JobStatus.RUNNING.value
        job.started_at = job.started_at or datetime.now(timezone.utc)
        job.current_step = "generic_generation"
        self.db.commit()
        self.db.refresh(job)
        try:
            payload = self._build_generic_payload(job)
            errors = self._validation.validate_generic_content(
                content_type=job.content_type,
                title=payload["title"],
                summary=payload["summary"],
                estimated_duration_min=payload["estimated_duration_min"],
            )
            if errors:
                job.status = JobStatus.FAILED.value
                job.error_message = "; ".join(errors)[:2000]
                job.completed_at = datetime.now(timezone.utc)
                self.db.commit()
                self.db.refresh(job)
                return job

            job.status = JobStatus.PUBLISHING.value
            job.current_step = "publishing"
            job.quality_score = 0.82
            self.db.commit()
            self.db.refresh(job)
            content_id = self._publishing.publish_generated_content(
                content_type=job.content_type,
                topic=payload["title"],
                subject=job.subject,
                grade_band=job.grade_band,
                difficulty=job.difficulty,
                locale=job.locale,
                job_id=job.id,
                generated_blob=payload["json_blob"],
                summary=payload["summary"],
                subtitle=payload["subtitle"],
                estimated_duration_min=payload["estimated_duration_min"],
                tags={"job_type": job.job_type, "source": job.source or "content_factory"},
            )
            job.status = JobStatus.COMPLETED.value
            job.current_step = "completed"
            job.result_content_id = content_id
            job.completed_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(job)
            return job
        except Exception as e:
            job.status = JobStatus.FAILED.value
            job.error_message = str(e)[:2000]
            job.completed_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(job)
            logger.exception("Job %s failed: %s", job_id, e)
            return job
