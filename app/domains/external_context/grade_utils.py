"""
Normalization utilities for grade values.
All functions are pure, no DB access, safe to import anywhere.
"""
from __future__ import annotations

import re

from app.domains.external_context.metadata_data import GRADE_ALIASES, GRADE_BAND_ALIASES, US_GRADES
from app.domains.external_context.qualification_levels import QUALIFICATION_GRADE_RANGES

_GRADE_BY_VALUE: dict[str, dict] = {g["value"]: g for g in US_GRADES}

# Canonical grade-band slug → inclusive numeric range (0=K, 1–12)
_GRADE_BAND_NUMERIC_RANGES: dict[str, tuple[int, int]] = {
    "K-2": (0, 2),
    "3-5": (3, 5),
    "6-8": (6, 8),
    "9-12": (9, 12),
    "higher_ed": (11, 12),
}

_NUMERIC_RANGE_RE = re.compile(r"(\d+)\s*[–\-]\s*(\d+)")


def resolve_grade_value(raw) -> str | None:
    """
    Convert any stored grade representation to a canonical US_GRADES value.
    Returns None if the input cannot be resolved.

    Examples:
        "Year 7"   → "7"
        "Grade 8"  → "8"
        "8"        → "8"
        7          → "7"
        0          → "K"
        "K"        → "K"
    """
    if raw is None:
        return None
    normalized = str(raw).strip().lower()
    if normalized in GRADE_ALIASES:
        return GRADE_ALIASES[normalized]
    # Direct match against canonical values (case-insensitive for K)
    stripped = str(raw).strip()
    if stripped.upper() == "K":
        return "K"
    if stripped in _GRADE_BY_VALUE:
        return stripped
    return None


def grade_label(raw) -> str:
    """
    Convert any stored grade to the US display label.
    Falls back to the original string if unresolvable (never breaks display).

    Examples:
        "Year 7"  → "Grade 7"
        "8"       → "Grade 8"
        0         → "Kindergarten"
    """
    canonical = resolve_grade_value(raw)
    if canonical and canonical in _GRADE_BY_VALUE:
        return _GRADE_BY_VALUE[canonical]["label"]
    return str(raw) if raw is not None else ""


def grade_numeric(raw) -> int | None:
    """
    Convert any stored grade to an integer 0–12 for the template/LLM API.
    0 = Kindergarten, 1–12 = Grade 1–12. Returns None if unresolvable.
    """
    canonical = resolve_grade_value(raw)
    if canonical and canonical in _GRADE_BY_VALUE:
        return _GRADE_BY_VALUE[canonical]["numeric"]
    return None


def _canonical_to_numeric(canonical: str) -> int | None:
    if canonical == "K":
        return 0
    if canonical in _GRADE_BY_VALUE:
        return _GRADE_BY_VALUE[canonical]["numeric"]
    return None


def _parse_numeric_range_from_string(raw: str) -> tuple[int, int] | None:
    """Extract min/max from strings like '6-8', 'Grade 6-8', '9–12'."""
    text = (raw or "").strip()
    if not text:
        return None
    match = _NUMERIC_RANGE_RE.search(text)
    if not match:
        return None
    low, high = int(match.group(1)), int(match.group(2))
    if low > high:
        low, high = high, low
    return (low, high)


def _stored_grade_numeric_range(stored_raw) -> tuple[int, int] | None:
    """Resolve stored pack grade to an inclusive numeric range, if possible."""
    if stored_raw is None or str(stored_raw).strip() == "":
        return None

    normalized = str(stored_raw).strip().lower()

    qual = QUALIFICATION_GRADE_RANGES.get(normalized)
    if qual:
        return qual

    band_slug = GRADE_BAND_ALIASES.get(normalized)
    if band_slug and band_slug in _GRADE_BAND_NUMERIC_RANGES:
        return _GRADE_BAND_NUMERIC_RANGES[band_slug]

    parsed = _parse_numeric_range_from_string(str(stored_raw))
    if parsed:
        return parsed

    canonical = resolve_grade_value(stored_raw)
    if canonical:
        num = _canonical_to_numeric(canonical)
        if num is not None:
            return (num, num)

    return None


def grade_filter_matches(stored_raw, filter_raw) -> bool:
    """
    True when a content-pack grade matches a catalog filter grade.

    Handles canonical grades, labels, bands (6-8, 9-12), and qualification strings.
    When filter is empty/None, all stored grades match (no grade constraint).
    When stored is empty/None, only matches if filter is also empty.
    """
    if filter_raw is None or str(filter_raw).strip() == "":
        return True
    if stored_raw is None or str(stored_raw).strip() == "":
        return False

    filter_canonical = resolve_grade_value(filter_raw)
    if not filter_canonical:
        return False
    filter_num = _canonical_to_numeric(filter_canonical)
    if filter_num is None:
        return False

    stored_range = _stored_grade_numeric_range(stored_raw)
    if stored_range:
        return stored_range[0] <= filter_num <= stored_range[1]

    return False
