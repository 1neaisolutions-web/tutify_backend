import pytest

from app.domains.external_context.grade_utils import grade_label, grade_numeric, resolve_grade_value


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Year 7", "7"),
        ("year 7", "7"),
        ("Grade 8", "8"),
        ("grade 8", "8"),
        ("8", "8"),
        (8, "8"),
        (0, "K"),
        ("0", "K"),
        ("K", "K"),
        ("Kindergarten", "K"),
        ("kinder", "K"),
        ("Grade 12", "12"),
        ("Year 11", "11"),
        ("grade k", "K"),
        ("3rd grade", "3"),
        ("7th grade", "7"),
        ("10th grade", "10"),
        ("1st grade", "1"),
        (None, None),
        ("unknown_value", None),
    ],
)
def test_resolve_grade_value(raw, expected):
    assert resolve_grade_value(raw) == expected


@pytest.mark.parametrize(
    "raw,expected_label",
    [
        ("Year 7", "Grade 7"),
        ("8", "Grade 8"),
        (0, "Kindergarten"),
        ("K", "Kindergarten"),
        ("Grade 12", "Grade 12"),
        ("unknown", "unknown"),
    ],
)
def test_grade_label(raw, expected_label):
    assert grade_label(raw) == expected_label


@pytest.mark.parametrize(
    "raw,expected_numeric",
    [
        ("K", 0),
        ("1", 1),
        ("12", 12),
        ("Year 7", 7),
        ("Grade 8", 8),
        (0, 0),
        (8, 8),
        (None, None),
        ("unknown", None),
    ],
)
def test_grade_numeric(raw, expected_numeric):
    assert grade_numeric(raw) == expected_numeric
