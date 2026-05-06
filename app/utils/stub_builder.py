"""
Generic stub output builder driven by template version output_schema and stub_config.

Builds a dict that conforms to output_schema by walking the schema and filling
values from stub_config (with template/input placeholders) or sensible defaults.

This is intentionally schema-driven so it works for ANY template output shape
(lesson plans, STEAM challenges, checklists, etc.) as long as:
- The TemplateVersion has a JSON Schema in output_schema
- The template/template_version define a stub_config with templates/defaults
"""
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def _normalize_schema_type(prop_schema: Dict[str, Any]) -> str:
    """
    Resolve JSON Schema type; handle union types like ["object", "null"].
    Falls back to "string" when unknown.
    """
    t = prop_schema.get("type")
    if isinstance(t, str):
        return t
    if isinstance(t, list):
        for u in t:
            if u != "null":
                return u
        return "null"
    return "string"


def _format_template(template: str, context: Dict[str, Any]) -> str:
    """
    Format a template string with context; missing keys become empty string.

    This avoids KeyError so stub templates can safely reference optional keys.
    """
    try:
        safe_context = {
            k: (v if v is not None else "")
            for k, v in context.items()
            if isinstance(k, str)
        }
        return template.format(**safe_context)
    except (KeyError, ValueError):
        return template


def _build_context(input_data: Dict[str, Any], template_name: str = "") -> Dict[str, Any]:
    """
    Build formatting context from input_data and template metadata for stub placeholders.

    Common placeholders supported across templates:
    - {template_name}
    - {subject}
    - {topic}
    - {learning_objective}
    - {grade}
    - {activity_type}

    Plus any other primitive fields present in input_data.
    """
    base = {
        "template_name": template_name,
        "subject": input_data.get("subject", input_data.get("subject_default", "general")),
        "topic": input_data.get("topic", "topic"),
        "learning_objective": input_data.get("learning_objective", "Support student learning."),
        "grade": input_data.get("grade", 5),
        "activity_type": input_data.get("activity_type", "hands_on"),
    }

    # Include all simple primitives from input_data so templates can reference them directly
    for k, v in input_data.items():
        if isinstance(v, (str, int, float, bool)):
            base.setdefault(k, v)

    return base


def _fill_from_schema(
    schema: Dict[str, Any],
    stub_config: Dict[str, Any],
    context: Dict[str, Any],
    schema_key: str,
) -> Any:
    """
    Recursively fill a value for schema_key from stub_config according to schema type.

    Rules (high‑level):
    - string:
        - Use `<key>_template` from stub_config when present (format with context)
        - Else use plain string at `<key>` in stub_config (format if string)
        - Else return empty string
    - array of strings:
        - Use list at `<key>_template` or `<key>` and format each
    - array of objects:
        - Prefer list[dict] at `<key>` in stub_config (format any string values)
        - Else build a single default object using the nested properties
    - object:
        - Recurse into its properties using stub_config[key] as nested stub_config
    - other primitives:
        - Return stub_config[key] when present, else None
    """
    props = schema.get("properties") or {}
    prop_schema = props.get(schema_key)
    if not prop_schema:
        return None

    prop_type = _normalize_schema_type(prop_schema)
    stub_val = stub_config.get(schema_key)

    # STRING
    if prop_type == "string":
        template = stub_config.get(f"{schema_key}_template")
        if isinstance(template, str) and template:
            return _format_template(template, context)
        if isinstance(stub_val, str) and stub_val:
            return _format_template(stub_val, context)
        return ""

    # ARRAY
    if prop_type == "array":
        items_schema = prop_schema.get("items") or {}
        item_type = _normalize_schema_type(items_schema) if items_schema else "string"

        # Array of strings
        if item_type == "string":
            templates = stub_config.get(f"{schema_key}_template") or stub_val
            if isinstance(templates, list):
                return [
                    _format_template(str(t), context) if isinstance(t, str) else str(t)
                    for t in templates
                ]
            if isinstance(templates, str):
                return [_format_template(templates, context)]
            return []

        # Array of objects
        if item_type == "object":
            raw = stub_val
            # Backward compat: "steps" from step_titles + step_descriptions_template (seed format)
            if schema_key == "steps":
                step_titles = stub_config.get("step_titles")
                step_desc_tpl = stub_config.get("step_descriptions_template", "Discuss {topic}.")
                if isinstance(step_titles, list) and step_titles:
                    return [
                        {
                            "title": _format_template(str(t), context) if isinstance(t, str) else str(t),
                            "description": _format_template(
                                step_desc_tpl,
                                {**context, "step_title": t if isinstance(t, str) else ""},
                            ),
                        }
                        for t in step_titles
                    ]
            # Prefer explicit list of dicts in stub_config
            if isinstance(raw, list) and raw:
                out = []
                for item in raw:
                    if not isinstance(item, dict):
                        continue
                    formatted_item: Dict[str, Any] = {}
                    for k, v in item.items():
                        if isinstance(v, str):
                            formatted_item[k] = _format_template(v, context)
                        else:
                            formatted_item[k] = v
                    out.append(formatted_item)
                return out

            # Fallback: build a single default object based on nested properties
            item_props = items_schema.get("properties") or {}
            default_item: Dict[str, Any] = {}
            for nested_key in item_props.keys():
                default_item[nested_key] = _fill_from_schema(
                    {"properties": item_props},
                    stub_config.get(schema_key, {}) if isinstance(stub_config.get(schema_key), dict) else {},
                    context,
                    nested_key,
                )
            return [default_item] if default_item else []

        # Unsupported array item type
        return []

    # OBJECT
    if prop_type == "object":
        nested_stub = stub_val if isinstance(stub_val, dict) else {}
        nested_schema = prop_schema.get("properties") or {}
        result: Dict[str, Any] = {}
        for nested_key in nested_schema.keys():
            result[nested_key] = _fill_from_schema(
                {"properties": nested_schema},
                nested_stub,
                context,
                nested_key,
            )
        # Backward compat: seed uses top-level assessment_checks for assessment.checks_for_understanding
        if schema_key == "assessment" and "checks_for_understanding" in nested_schema:
            checks = stub_config.get("assessment_checks")
            if isinstance(checks, list):
                result["checks_for_understanding"] = [
                    _format_template(str(c), context) if isinstance(c, str) else str(c)
                    for c in checks
                ]
        return result

    # OTHER PRIMITIVES (number, integer, boolean, etc.)
    if stub_val is not None:
        return stub_val

    # Reasonable defaults
    if prop_type in ("number", "integer"):
        return 0
    if prop_type == "boolean":
        return False
    if prop_type == "null":
        return None

    return None


def build_stub_output(
    output_schema: Dict[str, Any],
    stub_config: Dict[str, Any],
    input_data: Dict[str, Any],
    template_name: str = "",
) -> Dict[str, Any]:
    """
    Build a stub output dict that conforms to output_schema.

    Uses:
    - output_schema: JSON Schema object with top‑level "properties"
    - stub_config: per‑template config from DB/seed
    - input_data: user input for formatting placeholders
    - template_name: template.display name for placeholders

    Returns:
        Dict with at least all required properties present.
    """
    if not isinstance(output_schema, dict):
        logger.warning("build_stub_output: invalid output_schema (expected dict)")
        return {}

    props = output_schema.get("properties") or {}
    required = output_schema.get("required") or []

    context = _build_context(input_data, template_name)
    stub_config = stub_config or {}

    result: Dict[str, Any] = {}

    for key in props.keys():
        try:
            result[key] = _fill_from_schema(output_schema, stub_config, context, key)
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("build_stub_output: failed to fill key '%s': %s", key, e)
            # Fallback to simple defaults by type
            prop_schema = props.get(key, {})
            t = _normalize_schema_type(prop_schema)
            if t == "string":
                result[key] = ""
            elif t == "array":
                result[key] = []
            elif t == "object":
                result[key] = {}
            elif t in ("number", "integer"):
                result[key] = 0
            elif t == "boolean":
                result[key] = False
            else:
                result[key] = None

    # Ensure required keys exist (with sensible defaults) even if schema/properties mis‑aligned
    for key in required:
        if key not in result:
            prop_schema = props.get(key, {})
            t = _normalize_schema_type(prop_schema)
            if t == "string":
                result[key] = ""
            elif t == "array":
                result[key] = []
            elif t == "object":
                result[key] = {}
            elif t in ("number", "integer"):
                result[key] = 0
            elif t == "boolean":
                result[key] = False
            else:
                result[key] = None

    return result

