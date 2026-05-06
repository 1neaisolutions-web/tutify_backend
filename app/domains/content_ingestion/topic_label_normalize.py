"""
Normalize topic / chapter titles for any locale or script (future-proof catalog UX).

Used when building chapter_map and fallback chunk topic_title values so strands
stay readable and dedupe sensibly across Arabic, CJK, Latin, etc.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional


_WS_RE = re.compile(r"\s+")


def normalize_topic_label(value: Optional[str], *, max_len: int = 500) -> str:
    """
    NFKC normalize, collapse whitespace, trim, truncate for DB/UI.

    Does not transliterate — preserves original scripts.
    """
    if value is None:
        return ""
    s = str(value).replace("\u0000", "")
    s = unicodedata.normalize("NFKC", s)
    s = _WS_RE.sub(" ", s).strip()
    if not s:
        return ""
    if len(s) > max_len:
        s = s[: max_len - 1] + "\u2026"
    return s
