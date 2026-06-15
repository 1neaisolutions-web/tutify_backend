"""
Normalization utilities for grade band values.
All functions are pure, no DB access, safe to import anywhere.
"""
from app.domains.external_context.metadata_data import GRADE_BANDS, GRADE_BAND_ALIASES

_BAND_BY_VALUE: dict[str, dict] = {b["value"]: b for b in GRADE_BANDS}


def resolve_band_value(raw) -> str | None:
    """Convert any stored band representation to a canonical GRADE_BANDS value."""
    if raw is None:
        return None
    normalized = str(raw).strip().lower()
    if normalized in GRADE_BAND_ALIASES:
        return GRADE_BAND_ALIASES[normalized]
    stripped = str(raw).strip()
    if stripped in _BAND_BY_VALUE:
        return stripped
    return None


def band_label(raw) -> str:
    """Convert any stored band to display label; falls back to original string."""
    canonical = resolve_band_value(raw)
    if canonical and canonical in _BAND_BY_VALUE:
        return _BAND_BY_VALUE[canonical]["label"]
    return str(raw) if raw is not None else ""
