"""
Load template render schema from backend/templates/{slug}.json for schema-driven streaming.
Falls back to template version output_schema when no file exists.
"""
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


def _schema_type_from_property(prop: Dict[str, Any]) -> str:
    """Infer section type from JSON schema property."""
    if not isinstance(prop, dict):
        return "markdown"
    t = prop.get("type")
    if t == "string":
        return "markdown"
    if t == "array":
        items = prop.get("items") or {}
        if isinstance(items, dict) and items.get("type") == "object":
            return "numbered_list"
        return "bullet_list"
    if t == "object":
        return "table"
    return "markdown"


def load_template_schema(slug: str, output_schema: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    Load sections list for a template: from templates/{slug}.json if present,
    else build from output_schema (required order + properties with title and inferred type).

    Returns list of {"key": str, "label": str, "type": str} for meta event.
    """
    # 1) Try file
    path = _TEMPLATES_DIR / f"{slug}.json"
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            sections = data.get("sections")
            if isinstance(sections, list) and sections:
                return [
                    {
                        "key": s.get("key", ""),
                        "label": s.get("label", s.get("key", "")),
                        "type": s.get("type", "markdown"),
                    }
                    for s in sections
                    if s.get("key")
                ]
        except Exception as e:
            logger.warning("Failed to load template schema from %s: %s", path, e)

    # 2) Build from output_schema
    if not output_schema or not isinstance(output_schema, dict):
        return []
    props = output_schema.get("properties") or {}
    if not isinstance(props, dict):
        return []
    required = output_schema.get("required")
    if isinstance(required, list):
        order = [k for k in required if k in props]
        for k in props:
            if k not in order:
                order.append(k)
    else:
        order = list(props.keys())

    result = []
    for key in order:
        prop = props.get(key) if isinstance(props, dict) else {}
        label = key.replace("_", " ").title()
        if isinstance(prop, dict) and prop.get("title"):
            label = prop["title"]
        result.append({
            "key": key,
            "label": label,
            "type": _schema_type_from_property(prop),
        })
    return result
