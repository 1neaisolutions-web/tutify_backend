import pytest

from app.domains.external_context.band_utils import band_label, resolve_band_value


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("6-8", "6-8"),
        ("Grades 6-8", "6-8"),
        ("grades 6-8", "6-8"),
        ("Middle School (6-8)", "6-8"),
        ("9-12", "9-12"),
        ("Grades 9-10", "9-12"),
        ("Higher Education", "higher_ed"),
        ("higher_ed", "higher_ed"),
        ("College", "higher_ed"),
        (None, None),
        ("unknown_band", None),
    ],
)
def test_resolve_band_value(raw, expected):
    assert resolve_band_value(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("6-8", "6–8"),
        ("Grades 6-8", "6–8"),
        ("unknown", "unknown"),
    ],
)
def test_band_label(raw, expected):
    assert band_label(raw) == expected
