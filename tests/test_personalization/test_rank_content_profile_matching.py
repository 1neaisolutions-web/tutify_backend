"""
Unit tests for _score_item_for_profile and _rank_content_for_section profile-aware filtering.

Key invariants:
- Content whose alignment/category/tags match the profile subject scores above threshold.
- Content with no matching signals scores 0.0 and is excluded.
- A subject change produces a disjoint ranked set.
- Incomplete profiles (no subjects, no grade_band) pass items through neutrally.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.domains.personalization.services.personalization_orchestrator import (
    _PROFILE_MATCH_THRESHOLD,
    _score_item_for_profile,
)


def _item(
    *,
    alignment: dict | None = None,
    category: str = "",
    tags: dict | list | None = None,
    content_id: str = "c1",
    content_type: str = "micro_course",
    source_type: str = "content_factory",
    title: str = "A Good Title For Testing Purposes",
    estimated_duration_min: int | None = 8,
) -> SimpleNamespace:
    """Build a minimal mock ContentRegistryItem."""
    return SimpleNamespace(
        content_id=content_id,
        content_type=content_type,
        source_type=source_type,
        title=title,
        estimated_duration_min=estimated_duration_min,
        category=category,
        tags=tags or {},
        alignment=alignment or {},
    )


# ─── _score_item_for_profile ────────────────────────────────────────────────

class TestScoreItemForProfile:
    def test_alignment_subject_match_scores_high(self):
        item = _item(alignment={"subjects": ["mathematics"]})
        score = _score_item_for_profile(item, {"subjects": ["mathematics"], "grade_band": ""})
        assert score >= 0.40

    def test_alignment_grade_band_match_adds_score(self):
        item = _item(alignment={"subjects": ["mathematics"], "grade_band": "middle_school"})
        score = _score_item_for_profile(
            item, {"subjects": ["mathematics"], "grade_band": "middle_school"}
        )
        assert score >= 0.65  # 0.40 subject + 0.25 grade

    def test_category_match_when_no_alignment(self):
        item = _item(category="mathematics")
        score = _score_item_for_profile(item, {"subjects": ["mathematics"], "grade_band": ""})
        assert score >= 0.20
        assert score >= _PROFILE_MATCH_THRESHOLD

    def test_tag_match_passes_threshold(self):
        item = _item(tags={"subjects": ["social_studies"]})
        score = _score_item_for_profile(item, {"subjects": ["social_studies"], "grade_band": ""})
        assert score >= _PROFILE_MATCH_THRESHOLD

    def test_no_match_scores_zero(self):
        item = _item(
            alignment={"subjects": ["mathematics"]},
            category="mathematics",
        )
        # Profile is social_studies only — nothing should match
        score = _score_item_for_profile(item, {"subjects": ["social_studies"], "grade_band": ""})
        assert score == 0.0

    def test_incomplete_profile_returns_neutral(self):
        """No subjects + no grade_band → neutral 0.5 so nothing is wrongly excluded."""
        item = _item(alignment={"subjects": ["mathematics"]})
        score = _score_item_for_profile(item, {"subjects": [], "grade_band": ""})
        assert score == 0.5

    def test_curriculum_adds_bonus(self):
        item = _item(
            alignment={"subjects": ["science"], "curriculum_framework": "common_core"}
        )
        base_score = _score_item_for_profile(item, {"subjects": ["science"], "grade_band": ""})
        bonus_score = _score_item_for_profile(
            item,
            {"subjects": ["science"], "grade_band": "", "curriculum_framework": "common_core"},
        )
        assert bonus_score > base_score

    def test_score_capped_at_one(self):
        item = _item(
            alignment={"subjects": ["science"], "grade_band": "high_school"},
            category="science",
            tags={"subjects": ["science"]},
        )
        score = _score_item_for_profile(
            item,
            {
                "subjects": ["science"],
                "grade_band": "high_school",
                "curriculum_framework": "",
            },
        )
        assert score <= 1.0

    def test_subject_change_produces_zero_for_old_subject(self):
        """Simulates a profile subject change: old math item gets 0 under new social_studies profile."""
        math_item = _item(
            alignment={"subjects": ["mathematics"], "grade_band": "primary"},
            category="mathematics",
            content_id="math-1",
        )
        ss_profile = {"subjects": ["social_studies"], "grade_band": "primary"}
        assert _score_item_for_profile(math_item, ss_profile) == 0.0

    def test_subject_change_scores_new_subject_item(self):
        ss_item = _item(
            alignment={"subjects": ["social_studies"], "grade_band": "primary"},
            category="social_studies",
            content_id="ss-1",
        )
        ss_profile = {"subjects": ["social_studies"], "grade_band": "primary"}
        assert _score_item_for_profile(ss_item, ss_profile) >= 0.40


# ─── _rank_content_for_section integration ──────────────────────────────────

class TestRankContentForSection:
    """
    Smoke-test _rank_content_for_section with a mocked DB.
    Verifies that subject change produces a different content_id set.
    """

    def _make_db(self, items: list) -> MagicMock:
        """Return a mock Session whose .query chain returns `items`."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = items
        db = MagicMock()
        db.query.return_value = mock_query
        return db

    def test_math_profile_returns_math_items_only(self):
        from app.domains.personalization.services.personalization_orchestrator import (
            _rank_content_for_section,
            _CONTENT_REGISTRY_AVAILABLE,
        )
        if not _CONTENT_REGISTRY_AVAILABLE:
            pytest.skip("ContentRegistryItem not available")

        math_item = _item(
            content_id="math-micro-1",
            title="Fractions Practice Activity For Primary Grades",
            alignment={"subjects": ["mathematics"], "grade_band": "primary"},
            category="mathematics",
        )
        sci_item = _item(
            content_id="sci-micro-1",
            title="Photosynthesis Lab Activity For Middle School",
            alignment={"subjects": ["science"], "grade_band": "middle_school"},
            category="science",
        )

        db = self._make_db([math_item, sci_item])
        math_profile = {"subjects": ["mathematics"], "grade_band": "primary"}

        with patch(
            "app.domains.learning_hub.route_resolver.resolve_learning_hub_route",
            return_value="/learning-hub",
        ):
            ranked = _rank_content_for_section(db, "micro_courses", math_profile)

        content_ids = [r["content_id"] for r in ranked]
        assert "math-micro-1" in content_ids, "math item must be included for math profile"
        assert "sci-micro-1" not in content_ids, "science item must be excluded for math profile"

    def test_subject_change_produces_disjoint_set(self):
        from app.domains.personalization.services.personalization_orchestrator import (
            _rank_content_for_section,
            _CONTENT_REGISTRY_AVAILABLE,
        )
        if not _CONTENT_REGISTRY_AVAILABLE:
            pytest.skip("ContentRegistryItem not available")

        math_item = _item(
            content_id="math-1",
            title="Number Sense Foundations For Elementary Teachers",
            alignment={"subjects": ["mathematics"]},
            category="mathematics",
        )
        ss_item = _item(
            content_id="ss-1",
            title="Geography Map Skills Lesson For Primary Grades",
            alignment={"subjects": ["social_studies"]},
            category="social_studies",
        )

        db_math = self._make_db([math_item, ss_item])
        db_ss = self._make_db([math_item, ss_item])

        with patch(
            "app.domains.learning_hub.route_resolver.resolve_learning_hub_route",
            return_value="/learning-hub",
        ):
            ranked_math = _rank_content_for_section(db_math, "micro_courses", {"subjects": ["mathematics"], "grade_band": ""})
            ranked_ss = _rank_content_for_section(db_ss, "micro_courses", {"subjects": ["social_studies"], "grade_band": ""})

        math_ids = {r["content_id"] for r in ranked_math}
        ss_ids = {r["content_id"] for r in ranked_ss}
        assert math_ids != ss_ids, "subject change must produce different content set"
        assert "math-1" in math_ids and "math-1" not in ss_ids
        assert "ss-1" in ss_ids and "ss-1" not in math_ids

    def test_no_match_returns_empty(self):
        from app.domains.personalization.services.personalization_orchestrator import (
            _rank_content_for_section,
            _CONTENT_REGISTRY_AVAILABLE,
        )
        if not _CONTENT_REGISTRY_AVAILABLE:
            pytest.skip("ContentRegistryItem not available")

        math_item = _item(
            content_id="math-1",
            title="Algebra Concepts Activity For High School",
            alignment={"subjects": ["mathematics"]},
            category="mathematics",
        )
        db = self._make_db([math_item])

        with patch(
            "app.domains.learning_hub.route_resolver.resolve_learning_hub_route",
            return_value="/learning-hub",
        ):
            ranked = _rank_content_for_section(db, "micro_courses", {"subjects": ["physical_education"], "grade_band": ""})

        assert ranked == [], "no matching items → must return empty, not generic picks"
