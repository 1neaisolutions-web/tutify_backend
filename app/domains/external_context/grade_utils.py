"""
Normalization utilities for grade values.
All functions are pure, no DB access, safe to import anywhere.
"""
from app.domains.external_context.metadata_data import GRADE_ALIASES, US_GRADES

_GRADE_BY_VALUE: dict[str, dict] = {g["value"]: g for g in US_GRADES}


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
