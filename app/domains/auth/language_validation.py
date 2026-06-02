"""IETF BCP 47 language tag validation for user preferences."""
import re

_LANGUAGE_TAG_RE = re.compile(r"^[a-zA-Z]{2,8}(-[a-zA-Z0-9]{1,8})*$")


def is_valid_language_tag(tag: str) -> bool:
    """Accept any IETF BCP 47 language tag (e.g. 'en-US', 'fr', 'zh-Hant-TW')."""
    return bool(_LANGUAGE_TAG_RE.match(tag or ""))
