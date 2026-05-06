"""Tests for video library mapping, selection, cache, and quiz payload merge."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.domains.external_context.service import TeacherContextService
from app.domains.video_library import cache as rec_cache
from app.domains.video_library.mapping import library_keys_for_profile_slugs, subject_lens_for_granular
from app.domains.video_library.quiz_merge import apply_video_id_to_request_dict, derive_learning_focus_and_styles
from app.domains.video_library.selector import _allocate_channel_slots, _week_seed, select_recommendations
from app.domains.video_library.service import load_library, validate_library_file_on_disk, video_library_service
from app.domains.youtube_quiz.schemas import YouTubeQuizGenerateRequest


def test_library_json_structure():
    validate_library_file_on_disk()


def test_profile_slug_maps_to_library_keys():
    assert "Mathematics" in library_keys_for_profile_slugs(["math"])
    keys = library_keys_for_profile_slugs(["math", "science", "history"])
    assert "Mathematics" in keys and "Science_STEM" in keys and "Social_Sciences" in keys


def test_granular_subject_maps_to_lens():
    assert subject_lens_for_granular("History") == "Social Sciences"
    assert subject_lens_for_granular("Biology") == "Science & STEM"
    assert subject_lens_for_granular("Mathematics") == "Mathematics"


def test_allocate_channel_slots_even_distribution():
    # 6 slots / 3 subjects → 2 each (stable grouped order)
    assert _allocate_channel_slots(["A", "B", "C"], 6) == ["A", "A", "B", "B", "C", "C"]
    assert _allocate_channel_slots(["A"], 6) == ["A"] * 6


def test_week_seed_stable_per_iso_week():
    uid = uuid.uuid4()
    d1 = datetime(2026, 4, 27, 12, 0, tzinfo=timezone.utc)
    d2 = datetime(2026, 4, 30, 12, 0, tzinfo=timezone.utc)
    d3 = datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc)
    assert _week_seed(uid, d1) == _week_seed(uid, d2)
    assert _week_seed(uid, d1) != _week_seed(uid, d3)


def test_select_recommendations_one_subject_six_channels():
    lib = load_library()
    uid = uuid.uuid4()
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    chans = select_recommendations(lib, ["Mathematics"], uid, now)
    assert len(chans) == 6
    for ch in chans:
        assert len(ch.videos) == 3


def test_select_recommendations_multi_subject_distribution():
    lib = load_library()
    uid = uuid.uuid4()
    now = datetime(2026, 6, 2, tzinfo=timezone.utc)
    keys = ["Mathematics", "Science_STEM", "Social_Sciences"]
    chans = select_recommendations(lib, keys, uid, now)
    assert len(chans) == 6
    counts: dict[str, int] = {k: 0 for k in keys}
    for ch in chans:
        for k in keys:
            if ch.id.startswith(k.lower()):
                counts[k] += 1
                break
    assert max(counts.values()) - min(counts.values()) <= 1


def test_recommendation_cache_hit(monkeypatch):
    class FakeCtx:
        subjects = ["math"]

    monkeypatch.setattr(
        TeacherContextService,
        "get_by_user_id",
        lambda self, user_id: FakeCtx(),
    )

    user_id = uuid.uuid4()
    db = MagicMock()
    rec_cache.invalidate_recommendations(user_id)
    t0 = datetime(2026, 1, 5, tzinfo=timezone.utc)
    first = video_library_service.get_recommendations(db, user_id, now=t0)
    second = video_library_service.get_recommendations(db, user_id, now=t0)
    assert first.model_dump() == second.model_dump()


def test_recommendation_cache_regenerates_after_ttl(monkeypatch):
    class FakeCtx:
        subjects = ["math"]

    monkeypatch.setattr(
        TeacherContextService,
        "get_by_user_id",
        lambda self, user_id: FakeCtx(),
    )

    user_id = uuid.uuid4()
    db = MagicMock()
    rec_cache.invalidate_recommendations(user_id)
    t0 = datetime(2026, 1, 5, tzinfo=timezone.utc)
    first = video_library_service.get_recommendations(db, user_id, now=t0)
    t_late = t0 + timedelta(days=8)
    later = video_library_service.get_recommendations(db, user_id, now=t_late)
    assert len(later.channels) == 6
    assert len(first.channels) == 6


def test_recommendation_new_selection_when_subjects_fingerprint_changes(monkeypatch):
    class FakeCtx:
        def __init__(self, subjects):
            self.subjects = subjects

    seq = {"ctx": FakeCtx(["math"])}

    def get_uid(self, user_id):
        return seq["ctx"]

    monkeypatch.setattr(TeacherContextService, "get_by_user_id", get_uid)

    user_id = uuid.uuid4()
    db = MagicMock()
    rec_cache.invalidate_recommendations(user_id)
    now = datetime(2026, 3, 1, tzinfo=timezone.utc)
    first = video_library_service.get_recommendations(db, user_id, now=now)
    seq["ctx"] = FakeCtx(["science"])
    second = video_library_service.get_recommendations(db, user_id, now=now)
    assert len(first.channels) == len(second.channels) == 6


def test_apply_video_id_merges_request_dict():
    lib = load_library()
    data = {
        "videoId": "mathematics_ch01_v01",
        "video_url": "https://www.youtube.com/watch?v=invalidinvalid",
        "grade_band": "Grades 11-12",
        "subject_lens": "Creative Arts & Media",
        "learning_focus": "Project reflection",
        "quiz_language": "English",
        "question_styles": ["Discussion prompt"],
        "question_count": 6,
    }
    merged = apply_video_id_to_request_dict(data, lib)
    assert "videoId" not in merged and "video_id" not in merged
    assert merged["video_url"] == "https://www.youtube.com/watch?v=sQK3Yr4Sc_k"
    assert merged["grade_band"] == "Grades 3-5"
    assert merged["subject_lens"] == "Mathematics"


def test_youtube_request_accepts_video_id_alias():
    req = YouTubeQuizGenerateRequest(
        videoId="mathematics_ch01_v01",
        video_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        grade_band="Grades 6-8",
        subject_lens="Science & STEM",
        learning_focus="Concept comprehension",
        quiz_language="English",
        question_styles=["Multiple choice"],
        question_count=6,
    )
    assert req.video_url == "https://www.youtube.com/watch?v=sQK3Yr4Sc_k"
    assert req.subject_lens == "Mathematics"
    assert req.video_id is None


def test_derive_learning_focus_and_styles():
    lf, styles = derive_learning_focus_and_styles("Vocabulary + Multiple choice")
    assert lf == "Vocabulary development"
    assert "Multiple choice" in styles


def test_invalidate_recommendations_clears_cache_entry():
    from app.domains.video_library.cache import get_cached, invalidate_recommendations, set_cached
    from app.domains.video_library.schemas import RecommendationsResponse

    user_id = uuid.uuid4()
    empty = RecommendationsResponse(channels=[]).model_dump(mode="json")
    set_cached(user_id, ("math",), 9e12, empty)
    assert get_cached(user_id, ("math",), 0.0) is not None
    invalidate_recommendations(user_id)
    assert get_cached(user_id, ("math",), 0.0) is None
