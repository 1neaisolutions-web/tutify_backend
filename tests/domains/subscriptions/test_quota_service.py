"""
Unit tests for QuotaService in app/domains/subscriptions/services/quota_service.py.
"""
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from app.domains.subscriptions.services.quota_service import QuotaCheck, QuotaService
from app.domains.subscriptions.models import UserUsageQuota


def _make_db():
    db = MagicMock()
    return db


def _make_quota(
    daily_messages_limit=20,
    daily_messages_used=0,
    monthly_messages_limit=500,
    monthly_messages_used=0,
    requests_per_minute=3,
    request_window_start=None,
    request_count_in_window=0,
    daily_reset_at=None,
    last_request_at=None,
) -> UserUsageQuota:
    q = MagicMock(spec=UserUsageQuota)
    q.daily_messages_limit = daily_messages_limit
    q.daily_messages_used = daily_messages_used
    q.monthly_messages_limit = monthly_messages_limit
    q.monthly_messages_used = monthly_messages_used
    q.requests_per_minute = requests_per_minute
    q.request_window_start = request_window_start
    q.request_count_in_window = request_count_in_window
    q.daily_reset_at = daily_reset_at
    q.last_request_at = last_request_at
    return q


# ---------------------------------------------------------------------------
# check_quota — daily limit
# ---------------------------------------------------------------------------

class TestCheckQuota:
    def _svc(self, db, quota):
        svc = QuotaService(db)
        svc._get_or_create_quota = MagicMock(return_value=quota)
        return svc

    def test_allowed_when_under_daily_limit(self):
        quota = _make_quota(daily_messages_limit=20, daily_messages_used=5)
        quota.daily_reset_at = datetime.now(timezone.utc) + timedelta(hours=12)
        svc = self._svc(_make_db(), quota)

        result = svc.check_quota(uuid.uuid4(), "chat")
        assert result.allowed is True

    def test_denied_when_daily_limit_reached(self):
        quota = _make_quota(daily_messages_limit=20, daily_messages_used=20)
        quota.daily_reset_at = datetime.now(timezone.utc) + timedelta(hours=12)
        svc = self._svc(_make_db(), quota)

        result = svc.check_quota(uuid.uuid4(), "chat")
        assert result.allowed is False
        assert result.reason == "daily_limit_exceeded"
        assert result.remaining == 0

    def test_allowed_when_no_daily_limit(self):
        quota = _make_quota(daily_messages_limit=None)
        svc = self._svc(_make_db(), quota)

        result = svc.check_quota(uuid.uuid4(), "chat")
        assert result.allowed is True

    def test_increment_increases_usage_counter(self):
        quota = _make_quota(daily_messages_limit=20, daily_messages_used=5)
        quota.daily_reset_at = datetime.now(timezone.utc) + timedelta(hours=12)
        db = _make_db()
        svc = self._svc(db, quota)

        svc.check_quota(uuid.uuid4(), "chat", increment=True)
        assert quota.daily_messages_used == 6
        assert quota.monthly_messages_used == 1

    def test_daily_quota_resets_when_past_reset_time(self):
        quota = _make_quota(daily_messages_limit=20, daily_messages_used=20)
        quota.daily_reset_at = datetime.now(timezone.utc) - timedelta(hours=1)  # past
        db = _make_db()
        svc = self._svc(db, quota)

        result = svc.check_quota(uuid.uuid4(), "chat")
        assert quota.daily_messages_used == 0
        assert result.allowed is True

    def test_dummy_quota_namespace_allows_everything(self):
        dummy = SimpleNamespace(
            daily_messages_limit=None,
            daily_messages_used=0,
            monthly_messages_limit=None,
            monthly_messages_used=0,
            requests_per_minute=None,
            request_window_start=None,
            request_count_in_window=0,
            daily_reset_at=None,
            last_request_at=None,
        )
        db = _make_db()
        svc = QuotaService(db)
        svc._get_or_create_quota = MagicMock(return_value=dummy)

        result = svc.check_quota(uuid.uuid4(), "chat")
        assert result.allowed is True


# ---------------------------------------------------------------------------
# _check_rate_limit
# ---------------------------------------------------------------------------

class TestCheckRateLimit:
    def _svc(self, db):
        return QuotaService(db)

    def test_allows_first_request_initialises_window(self):
        quota = _make_quota(requests_per_minute=3, request_window_start=None, request_count_in_window=0)
        db = _make_db()
        svc = self._svc(db)

        result = svc._check_rate_limit(quota)
        assert result is True
        assert quota.request_window_start is not None

    def test_denies_when_count_exceeds_per_minute_limit(self):
        quota = _make_quota(
            requests_per_minute=3,
            request_window_start=datetime.now(timezone.utc),
            request_count_in_window=3,
        )
        db = _make_db()
        svc = self._svc(db)

        result = svc._check_rate_limit(quota)
        assert result is False

    def test_resets_window_after_60_seconds(self):
        quota = _make_quota(
            requests_per_minute=3,
            request_window_start=datetime.now(timezone.utc) - timedelta(seconds=61),
            request_count_in_window=3,
        )
        db = _make_db()
        svc = self._svc(db)

        result = svc._check_rate_limit(quota)
        assert result is True
        assert quota.request_count_in_window == 0


# ---------------------------------------------------------------------------
# _reset_daily_quota
# ---------------------------------------------------------------------------

class TestResetDailyQuota:
    def test_resets_daily_usage_and_sets_next_reset(self):
        quota = _make_quota(daily_messages_used=15)
        db = _make_db()
        svc = QuotaService(db)

        svc._reset_daily_quota(quota)

        assert quota.daily_messages_used == 0
        assert quota.daily_reset_at is not None
        db.commit.assert_called()


# ---------------------------------------------------------------------------
# log_usage
# ---------------------------------------------------------------------------

class TestLogUsage:
    def test_log_usage_creates_log_entry(self):
        from app.domains.subscriptions.models import UserUsageLog

        uid = uuid.uuid4()
        log_obj = MagicMock(spec=UserUsageLog)
        db = _make_db()

        svc = QuotaService(db)
        with patch("app.domains.subscriptions.services.quota_service.UserUsageLog", return_value=log_obj):
            svc.log_usage(uid, "generate_quiz", tokens_used=100)

        db.add.assert_called_once_with(log_obj)
        db.commit.assert_called()

    def test_log_usage_failure_does_not_propagate(self):
        db = _make_db()
        db.add.side_effect = Exception("DB error")

        svc = QuotaService(db)
        # Should not raise — usage logging is non-blocking
        svc.log_usage(uuid.uuid4(), "action")
