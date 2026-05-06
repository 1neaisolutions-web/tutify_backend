"""Unit tests for personalization snapshot comparison and sync planning."""
from __future__ import annotations

from app.domains.personalization.services.personalization_sync_service import (
    _snapshots_equal,
    plan_sync,
)


def test_snapshots_equal_stable():
    a = {"country": "US", "identity_fingerprint": "abc", "subjects": ["math"]}
    b = {"subjects": ["math"], "country": "US", "identity_fingerprint": "abc"}
    assert _snapshots_equal(a, b) is True


def test_snapshots_equal_detects_change():
    a = {"identity_fingerprint": "abc"}
    b = {"identity_fingerprint": "def"}
    assert _snapshots_equal(a, b) is False


def test_plan_sync_noop_when_equal():
    from unittest.mock import MagicMock
    import uuid

    db = MagicMock()
    uid = uuid.uuid4()
    snap = {"country": "US", "identity_fingerprint": "x"}
    op, reason = plan_sync(db, uid, snap, snap)
    assert op == "noop"
    assert reason == "unchanged"
