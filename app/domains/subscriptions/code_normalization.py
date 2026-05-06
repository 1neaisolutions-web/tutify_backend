"""Normalize access codes for storage and lookup (hyphens/spaces ignored)."""


def normalize_access_code(code: str) -> str:
    """Return uppercase A–Z / 0–9 only. Empty string if nothing remains."""
    if not code:
        return ""
    return "".join(c for c in code.strip().upper() if c.isalnum())
