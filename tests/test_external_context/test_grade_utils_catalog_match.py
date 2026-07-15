"""Tests for grade_filter_matches used by quiz catalog filtering."""
import pytest

from app.domains.external_context.grade_utils import grade_filter_matches


@pytest.mark.parametrize(
    "stored, filter_grade, expected",
    [
        ("8", "8", True),
        ("Grade 8", "8", True),
        ("Year 8", "8", True),
        ("6-8", "8", True),
        ("9-12", "11", True),
        ("9", "8", False),
        ("Grade 9", "8", False),
        ("AS & A Level", "11", True),
        ("AS & A Level", "12", True),
        ("AS & A Level", "8", False),
        ("higher_ed", "11", True),
        (None, "8", False),
        ("8", None, True),
        ("", "8", False),
    ],
)
def test_grade_filter_matches(stored, filter_grade, expected):
    assert grade_filter_matches(stored, filter_grade) is expected
