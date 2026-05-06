"""Config-driven unlock service. Reads rules from DB; cached 60s."""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domains.personalization.enums import TRIGGER_EVENT_TYPES, SectionReadinessStatus
from app.domains.personalization.models import (
    PersonalizedContentAssignment,
    UnlockEvent,
    UnlockRule,
    UnlockState,
)

logger = get_logger(__name__)

# Simple in-process cache: {section: (rules_list, expiry_ts)}
_RULES_CACHE: dict[str, tuple[list, float]] = {}
_CACHE_TTL = 60.0  # seconds


class UnlockService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _load_rules(self, section: str) -> list[UnlockRule]:
        now = time.monotonic()
        cached = _RULES_CACHE.get(section)
        if cached and now < cached[1]:
            return cached[0]

        rules = (
            self.db.query(UnlockRule)
            .filter(UnlockRule.section == section, UnlockRule.enabled == True)  # noqa: E712
            .order_by(UnlockRule.priority.desc(), UnlockRule.batch_order.asc())
            .all()
        )
        _RULES_CACHE[section] = (rules, now + _CACHE_TTL)
        return rules

    @classmethod
    def invalidate_cache(cls, section: Optional[str] = None) -> None:
        if section:
            _RULES_CACHE.pop(section, None)
        else:
            _RULES_CACHE.clear()

    def initialize_unlock_states(
        self,
        user_id: uuid.UUID,
        assignments: list[PersonalizedContentAssignment],
    ) -> list[UnlockState]:
        states = []
        for assignment in assignments:
            existing = (
                self.db.query(UnlockState)
                .filter(UnlockState.assignment_id == assignment.id)
                .first()
            )
            if existing:
                states.append(existing)
                continue

            locked = assignment.bucket != "visible"
            state = UnlockState(
                assignment_id=assignment.id,
                user_id=user_id,
                section=assignment.section,
                personalization_version=assignment.personalization_version,
                locked=locked,
                bucket=assignment.bucket,
            )
            self.db.add(state)
            states.append(state)
        self.db.flush()
        return states

    def evaluate_unlocks(
        self,
        user_id: uuid.UUID,
        section: str,
        version: int,
        trigger_event_id: Optional[uuid.UUID] = None,
    ) -> list[uuid.UUID]:
        """Evaluate unlock rules for a section. Returns newly unlocked assignment_ids."""
        from app.domains.personalization.models import UserActivityEvent  # avoid circular

        rules = self._load_rules(section)
        newly_unlocked: list[uuid.UUID] = []

        for rule in rules:
            event_types = TRIGGER_EVENT_TYPES.get(rule.trigger_type, [])
            if not event_types:
                continue

            # Count qualifying events
            count = (
                self.db.query(UserActivityEvent)
                .filter(
                    UserActivityEvent.user_id == user_id,
                    UserActivityEvent.section == rule.trigger_section,
                    UserActivityEvent.event_type.in_(event_types),
                )
                .count()
            )

            if count < rule.trigger_threshold:
                continue

            # Check cooldown
            if rule.cooldown_seconds > 0:
                last_unlock = (
                    self.db.query(UnlockEvent)
                    .filter(
                        UnlockEvent.user_id == user_id,
                        UnlockEvent.section == section,
                        UnlockEvent.rule_id == rule.rule_id,
                    )
                    .order_by(UnlockEvent.created_at.desc())
                    .first()
                )
                if last_unlock:
                    elapsed = (datetime.now(timezone.utc) - last_unlock.created_at).total_seconds()
                    if elapsed < rule.cooldown_seconds:
                        continue

            # Check idempotency: already satisfied batch?
            batch_events = (
                self.db.query(UnlockEvent)
                .filter(
                    UnlockEvent.user_id == user_id,
                    UnlockEvent.section == section,
                    UnlockEvent.rule_id == rule.rule_id,
                )
                .count()
            )
            if batch_events >= rule.unlock_count:
                # Already fired enough times for this rule
                continue

            # Select locked assignments to unlock
            locked_states = (
                self.db.query(UnlockState)
                .join(PersonalizedContentAssignment, UnlockState.assignment_id == PersonalizedContentAssignment.id)
                .filter(
                    UnlockState.user_id == user_id,
                    UnlockState.section == section,
                    UnlockState.locked == True,  # noqa: E712
                    PersonalizedContentAssignment.personalization_version == version,
                )
                .order_by(PersonalizedContentAssignment.position)
                .limit(rule.unlock_count)
                .all()
            )

            for state in locked_states:
                state.locked = False
                state.unlocked_at = datetime.now(timezone.utc)
                state.unlock_rule_id = rule.rule_id
                state.updated_at = datetime.now(timezone.utc)

                event = UnlockEvent(
                    assignment_id=state.assignment_id,
                    user_id=user_id,
                    section=section,
                    personalization_version=version,
                    rule_id=rule.rule_id,
                    from_state="locked",
                    to_state="unlocked",
                    trigger_event_id=trigger_event_id,
                )
                self.db.add(event)
                newly_unlocked.append(state.assignment_id)

        self.db.flush()

        if newly_unlocked:
            logger.info(
                "personalization.unlock_evaluated",
                extra={
                    "user_id": str(user_id),
                    "section": section,
                    "items_unlocked": len(newly_unlocked),
                },
            )

        return newly_unlocked

    def get_states(self, user_id: uuid.UUID, section: Optional[str] = None) -> list[UnlockState]:
        q = self.db.query(UnlockState).filter(UnlockState.user_id == user_id)
        if section:
            q = q.filter(UnlockState.section == section)
        return q.all()
