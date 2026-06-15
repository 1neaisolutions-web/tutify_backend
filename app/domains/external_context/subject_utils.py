"""
Normalization utilities for subject values.
All functions are pure, no DB access, safe to import anywhere.
"""
from app.domains.external_context.metadata_data import SUBJECTS, SUBJECT_ALIASES

_SUBJECT_BY_VALUE: dict[str, dict] = {s["value"]: s for s in SUBJECTS}


def resolve_subject_value(raw) -> str | None:
    """Convert any stored subject representation to a canonical SUBJECTS value."""
    if raw is None:
        return None
    normalized = str(raw).strip().lower()
    if normalized in SUBJECT_ALIASES:
        return SUBJECT_ALIASES[normalized]
    stripped = str(raw).strip()
    if stripped in _SUBJECT_BY_VALUE:
        return stripped
    for entry in SUBJECTS:
        if entry.get("teacher_tools", "").lower() == normalized:
            return entry["value"]
        if entry.get("template", "").lower() == normalized:
            return entry["value"]
        if entry["label"].lower() == normalized:
            return entry["value"]
    return None


def subject_label(raw) -> str:
    """Display label for any stored subject. Falls back to original string."""
    canonical = resolve_subject_value(raw)
    if canonical and canonical in _SUBJECT_BY_VALUE:
        return _SUBJECT_BY_VALUE[canonical]["label"]
    return str(raw) if raw is not None else ""


def subject_teacher_tools_label(raw) -> str:
    """Label sent to teacher-tools API payloads."""
    canonical = resolve_subject_value(raw)
    if canonical and canonical in _SUBJECT_BY_VALUE:
        entry = _SUBJECT_BY_VALUE[canonical]
        return entry.get("teacher_tools") or entry["label"]
    return str(raw) if raw is not None else ""


def subject_template_label(raw) -> str:
    """Label sent to AI template / planner API payloads."""
    canonical = resolve_subject_value(raw)
    if canonical and canonical in _SUBJECT_BY_VALUE:
        entry = _SUBJECT_BY_VALUE[canonical]
        return entry.get("template") or entry["label"]
    return str(raw) if raw is not None else ""


def subjects_match(canonical_or_raw, stored) -> bool:
    """True when filter slug/label matches stored teacher-tools subject string."""
    left = resolve_subject_value(canonical_or_raw)
    right = resolve_subject_value(stored)
    if left and right:
        return left == right
    if left:
        entry = _SUBJECT_BY_VALUE.get(left, {})
        tt = entry.get("teacher_tools", entry.get("label", ""))
        return str(stored).strip().lower() == tt.lower()
    return str(canonical_or_raw).strip().lower() == str(stored).strip().lower()
