"""
Regression tests for pending-gap-worker filters when PERSONALIZATION_LLM_OUTBOUND_ENABLED is false.

Full integration coverage lives behind Postgres models (JSONB); here we assert clause shape/count only.
"""
from app.domains.content_factory.services.gap_generation_worker import pending_gap_worker_job_filters


def test_personalization_disabled_adds_extra_guard_clause():
    enabled = pending_gap_worker_job_filters(True)
    disabled = pending_gap_worker_job_filters(False)
    assert len(enabled) == 2
    assert len(disabled) == 3


def test_personalization_disabled_clause_references_user_scope():
    blob = " ".join(str(c).lower() for c in pending_gap_worker_job_filters(False))
    assert "requested_by_user_id" in blob
