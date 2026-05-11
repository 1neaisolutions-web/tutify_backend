"""
Unit tests for app/domains/user_history/repository.py.
Tests pure logic (filter building, toggle_pin, upsert_feedback) using mocked DB.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call

import pytest

from app.domains.user_history.repository import (
    SOURCE_TYPES_ALL,
    clear_history,
    toggle_pin,
    upsert_feedback,
)


def _make_db():
    db = MagicMock()
    db.execute.return_value.mappings.return_value.all.return_value = []
    db.execute.return_value.scalar.return_value = 0
    db.execute.return_value.rowcount = 0
    return db


# ---------------------------------------------------------------------------
# SOURCE_TYPES_ALL contract
# ---------------------------------------------------------------------------

class TestSourceTypesAll:
    def test_contains_all_expected_types(self):
        expected = {
            "quiz", "assignment", "worksheet", "exam",
            "chatbot_conversation", "pixgen_generation",
            "youtube_quiz", "template_execution",
        }
        assert set(SOURCE_TYPES_ALL) == expected


# ---------------------------------------------------------------------------
# toggle_pin
# ---------------------------------------------------------------------------

class TestTogglePin:
    def test_pin_creates_new_pin_when_not_exists(self):
        db = _make_db()
        db.query.return_value.filter.return_value.first.return_value = None

        pin_obj = MagicMock()

        with patch(
            "app.domains.user_history.models.UserContentPin",
            return_value=pin_obj,
        ):
            toggle_pin(
                db=db,
                user_id=str(uuid.uuid4()),
                source_type="quiz",
                source_id=str(uuid.uuid4()),
                pinned=True,
            )

        db.add.assert_called_once_with(pin_obj)
        db.commit.assert_called()

    def test_pin_is_noop_when_already_exists(self):
        existing_pin = MagicMock()
        db = _make_db()
        db.query.return_value.filter.return_value.first.return_value = existing_pin

        toggle_pin(
            db=db,
            user_id=str(uuid.uuid4()),
            source_type="quiz",
            source_id=str(uuid.uuid4()),
            pinned=True,
        )

        db.add.assert_not_called()

    def test_unpin_deletes_existing_pin(self):
        existing_pin = MagicMock()
        db = _make_db()
        db.query.return_value.filter.return_value.first.return_value = existing_pin

        toggle_pin(
            db=db,
            user_id=str(uuid.uuid4()),
            source_type="quiz",
            source_id=str(uuid.uuid4()),
            pinned=False,
        )

        db.delete.assert_called_once_with(existing_pin)
        db.commit.assert_called()

    def test_unpin_is_noop_when_not_pinned(self):
        db = _make_db()
        db.query.return_value.filter.return_value.first.return_value = None

        toggle_pin(
            db=db,
            user_id=str(uuid.uuid4()),
            source_type="quiz",
            source_id=str(uuid.uuid4()),
            pinned=False,
        )

        db.delete.assert_not_called()


# ---------------------------------------------------------------------------
# upsert_feedback
# ---------------------------------------------------------------------------

class TestUpsertFeedback:
    def test_creates_new_feedback_when_not_exists(self):
        db = _make_db()
        db.query.return_value.filter.return_value.first.return_value = None
        feedback_obj = MagicMock()

        with patch(
            "app.domains.user_history.models.UserContentFeedback",
            return_value=feedback_obj,
        ):
            upsert_feedback(
                db=db,
                user_id=str(uuid.uuid4()),
                source_type="quiz",
                source_id=str(uuid.uuid4()),
                hint="helpful",
                note="great quiz",
            )

        db.add.assert_called_once_with(feedback_obj)
        db.commit.assert_called()

    def test_updates_existing_feedback(self):
        existing = MagicMock()
        existing.hint = "neutral"
        existing.note = None
        db = _make_db()
        db.query.return_value.filter.return_value.first.return_value = existing

        upsert_feedback(
            db=db,
            user_id=str(uuid.uuid4()),
            source_type="quiz",
            source_id=str(uuid.uuid4()),
            hint="helpful",
            note="updated note",
        )

        assert existing.hint == "helpful"
        assert existing.note == "updated note"
        assert existing.updated_at is not None
        db.add.assert_not_called()
        db.commit.assert_called()


# ---------------------------------------------------------------------------
# clear_history — filter validation
# ---------------------------------------------------------------------------

class TestClearHistoryFilters:
    def test_invalid_source_type_returns_zero_without_db_call(self):
        db = _make_db()

        total = clear_history(
            db=db,
            user_id=str(uuid.uuid4()),
            source_types=["not_a_real_type"],
            search=None,
            date_from=None,
            date_to=None,
            keep_pinned=False,
        )

        assert total == 0
        db.execute.assert_not_called()

    def test_each_valid_source_type_triggers_delete(self):
        for source_type in SOURCE_TYPES_ALL:
            db = _make_db()
            db.execute.return_value.rowcount = 1

            total = clear_history(
                db=db,
                user_id=str(uuid.uuid4()),
                source_types=[source_type],
                search=None,
                date_from=None,
                date_to=None,
                keep_pinned=False,
            )

            db.execute.assert_called_once()
            assert total == 1

    def test_none_source_types_runs_all_types(self):
        db = _make_db()
        db.execute.return_value.rowcount = 0

        clear_history(
            db=db,
            user_id=str(uuid.uuid4()),
            source_types=None,
            search=None,
            date_from=None,
            date_to=None,
            keep_pinned=False,
        )

        assert db.execute.call_count == len(SOURCE_TYPES_ALL)
