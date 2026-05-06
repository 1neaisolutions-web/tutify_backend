"""
Publishing Policy Service: decide whether a job may auto-publish, require approval, or be rejected.
Code-based, deterministic V1 policy.
"""
from typing import Literal, TypedDict

from app.core.logging import get_logger
from app.domains.content_factory.enums import ContentGenerationStrategy

logger = get_logger(__name__)


DecisionType = Literal["auto_publish", "require_approval", "reject"]


class PublishingPolicyDecision(TypedDict):
    decision: DecisionType
    reason: str


class PublishingPolicyService:
    """
    Determine safe publishing policy for a generated job.

    Inputs:
        - content_type (str)
        - generation_strategy (str)
        - quality_score (float | None)
        - review_status (str | None) from review_agent
        - blocking_issues (bool) derived from review issues
    """

    def decide(
        self,
        *,
        content_type: str,
        generation_strategy: str,
        quality_score: float | None,
        review_status: str | None,
        has_blocking_issues: bool,
        min_quality: float = 0.3,
        auto_publish_threshold: float = 0.5,
    ) -> PublishingPolicyDecision:
        # 1. Quality too low => reject
        if quality_score is not None and quality_score < min_quality:
            reason = f"Quality score {quality_score:.2f} below minimum {min_quality:.2f}"
            logger.info("Publishing policy: reject low quality - %s", reason)
            return {"decision": "reject", "reason": reason}

        # 2. Blocking issues from review_agent => require approval or reject
        if has_blocking_issues:
            reason = "Blocking issues found by review agent; requires human review"
            logger.info("Publishing policy: require_approval - %s", reason)
            return {"decision": "require_approval", "reason": reason}

        # 3. Strategy-based rules
        strat = generation_strategy or ""
        if strat in (
            ContentGenerationStrategy.GAP_BASED.value,
            ContentGenerationStrategy.CURRICULUM_BASED.value,
        ):
            if quality_score is not None and quality_score >= auto_publish_threshold:
                reason = (
                    f"Gap-based strategy quality_score {quality_score:.2f} "
                    f">= auto_publish_threshold {auto_publish_threshold:.2f}; auto_publish"
                )
                logger.info("Publishing policy: auto_publish - %s", reason)
                return {"decision": "auto_publish", "reason": reason}
            reason = f"Generation strategy {strat} requires human approval"
            logger.info("Publishing policy: require_approval - %s", reason)
            return {"decision": "require_approval", "reason": reason}

        # 4. Content-type rules
        ctype = (content_type or "").lower()
        if ctype in ("learning_path", "ai_guided_tutorial"):
            if quality_score is not None and quality_score >= auto_publish_threshold:
                reason = (
                    f"Content type {ctype} quality_score {quality_score:.2f} "
                    f">= auto_publish_threshold {auto_publish_threshold:.2f}; auto_publish"
                )
                logger.info("Publishing policy: auto_publish - %s", reason)
                return {"decision": "auto_publish", "reason": reason}
            reason = f"Content type {ctype} requires human approval"
            logger.info("Publishing policy: require_approval - %s", reason)
            return {"decision": "require_approval", "reason": reason}

        # 5. MICRO_COURSE auto-publish rule
        if ctype == "micro_course":
            if quality_score is not None and quality_score >= auto_publish_threshold:
                reason = (
                    f"Micro-course with quality_score {quality_score:.2f} "
                    f">= auto_publish_threshold {auto_publish_threshold:.2f}"
                )
                logger.info("Publishing policy: auto_publish - %s", reason)
                return {"decision": "auto_publish", "reason": reason}
            else:
                reason = (
                    f"Micro-course quality_score {quality_score if quality_score is not None else 'N/A'} "
                    f"below auto_publish_threshold {auto_publish_threshold:.2f}; human approval required"
                )
                logger.info("Publishing policy: require_approval - %s", reason)
                return {"decision": "require_approval", "reason": reason}

        # 6. Default: require approval
        reason = "Default policy: require human approval"
        logger.info("Publishing policy: require_approval - %s", reason)
        return {"decision": "require_approval", "reason": reason}

