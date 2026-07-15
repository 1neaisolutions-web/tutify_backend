"""
Qualification / level strings that do not map to a single K-12 grade.
Keys are lowercased; values are inclusive (min_grade, max_grade) using 0=K, 1-12.
"""
from __future__ import annotations

QUALIFICATION_GRADE_RANGES: dict[str, tuple[int, int]] = {
    "as & a level": (11, 12),
    "as and a level": (11, 12),
    "a level": (11, 12),
    "a-level": (11, 12),
    "igcse": (10, 11),
    "o level": (10, 11),
    "gcse": (9, 10),
    "higher_ed": (11, 12),
    "higher education": (11, 12),
    "college": (11, 12),
}
