"""
Shared helpers for content factory agents.
"""
import json
import re
from typing import Any, Dict

from app.core.logging import get_logger

logger = get_logger(__name__)


def parse_json_from_llm(content: str) -> Dict[str, Any]:
    """
    Parse JSON from LLM response. Handles optional markdown code fence.
    Returns dict; on failure returns empty dict and logs.
    """
    text = (content or "").strip()
    if not text:
        return {}
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        text = match.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning("Agent response was not valid JSON: %s", e)
        return {}
