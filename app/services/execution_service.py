"""
Execution service for templates with stubbed (fake) or real LLM output.
"""
import asyncio
import json
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple, AsyncIterator

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.llm.config import llm_settings
from app.llm.router import ModelRouter
from app.llm.cache import ResponseCache
from app.llm.rate_limiter import RateLimiter
from app.llm.cost_tracker import CostTracker
from app.llm.toon_handler import TOONHandler
from app.llm.prompt_builder import TOONPromptBuilder
from app.models.template import Template, TemplateCategory
from app.models.template_version import TemplateVersion
from app.models.template_execution import TemplateExecution
from app.schemas.template import (
    UniversalTemplateOutput,
    LessonStep,
    BloomAlignmentItem,
    BloomLevel,
    AssessmentSection,
    AssessmentQuestion,
    CommunicationSection,
)
from app.utils.stub_builder import build_stub_output as generic_build_stub_output
from app.utils.markdown_converter import section_value_to_markdown_text, section_label_from_schema
from app.template_schema import load_template_schema

logger = get_logger(__name__)


def _ordered_section_keys_from_schema(output_schema: Dict[str, Any]) -> list:
    """Return section keys in order: required first, then remaining properties."""
    if not output_schema or not isinstance(output_schema, dict):
        return []
    props = output_schema.get("properties") or {}
    if not isinstance(props, dict):
        return []
    required = output_schema.get("required")
    if isinstance(required, list):
        # Required first (preserve order), then any properties not in required
        seen = set(required)
        ordered = [k for k in required if k in props]
        for k in props:
            if k not in seen:
                ordered.append(k)
                seen.add(k)
        return ordered
    return list(props.keys())


SECTION_MARKER_PREFIX = "[[SECTION:"
SECTION_MARKER_SUFFIX = "]]"


def _strip_section_markers(text: str) -> str:
    """Remove any [[SECTION:...]] markers from text. Markers must never reach the UI."""
    if not text or SECTION_MARKER_PREFIX not in text:
        return text
    out: List[str] = []
    i = 0
    while i < len(text):
        idx = text.find(SECTION_MARKER_PREFIX, i)
        if idx == -1:
            out.append(text[i:])
            break
        out.append(text[i:idx])
        end = text.find(SECTION_MARKER_SUFFIX, idx)
        if end == -1:
            i = idx + len(SECTION_MARKER_PREFIX)
            continue
        i = end + len(SECTION_MARKER_SUFFIX)
    return "".join(out)


def _looks_like_json_or_object_fragment(text: str) -> bool:
    """True if text clearly looks like raw JSON/object/array syntax (not prose)."""
    if not text or len(text) < 4:
        return False
    s = text.strip()
    if s.startswith("{") and ("}" in s or '"' in s or ":" in s):
        return True
    if s.startswith("[") and ("]" in s or '"' in s):
        return True
    if '"' in s and ":" in s and ("{" in s or s.strip().startswith('"')):
        return True
    return False


def _is_incomplete_json_fragment(text: str) -> bool:
    """True if text looks like JSON but is clearly incomplete (unbalanced, trailing comma)."""
    if not text:
        return False
    s = text.strip()
    if s.endswith(",") or s.endswith('"') or (s.startswith("{") and s.count("}") < s.count("{")):
        return True
    if s.startswith("[") and s.count("]") < s.count("["):
        return True
    return False


def _normalize_section_content_for_streaming(text: str) -> str:
    """
    Convert JSON/object-like section chunks into readable text so the UI never shows raw syntax.
    Only normalizes when content clearly looks structured; leaves prose unchanged.
    Skips incomplete fragments so the next chunk can complete them.
    """
    if not text or not _looks_like_json_or_object_fragment(text):
        return text
    if _is_incomplete_json_fragment(text):
        return text
    out: List[str] = []
    s = text.strip()
    try:
        parsed = json.loads(s)
        if isinstance(parsed, dict):
            for k, v in parsed.items():
                label = str(k).replace("_", " ").title()
                if isinstance(v, list):
                    out.append(f"{label}:")
                    for item in v:
                        out.append(f"- {item}" if isinstance(item, str) else f"- {json.dumps(item)}")
                elif isinstance(v, dict):
                    out.append(f"{label}: {json.dumps(v)}")
                else:
                    out.append(f"{label}: {v}")
            return "\n".join(out) if out else text
        if isinstance(parsed, list):
            for item in parsed:
                out.append(f"- {item}" if isinstance(item, str) else f"- {json.dumps(item)}")
            return "\n".join(out) if out else text
    except (json.JSONDecodeError, TypeError):
        pass
    lines: List[str] = []
    i = 0
    while i < len(s):
        if s[i] == "{":
            depth = 1
            j = i + 1
            while j < len(s) and depth > 0:
                if s[j] == "{":
                    depth += 1
                elif s[j] == "}":
                    depth -= 1
                j += 1
            chunk = s[i:j]
            if '"' in chunk and ":" in chunk:
                try:
                    obj = json.loads(chunk)
                    for k, v in obj.items():
                        label = str(k).replace("_", " ").title()
                        lines.append(f"{label}: {v}")
                except (json.JSONDecodeError, TypeError):
                    lines.append(chunk)
            else:
                lines.append(chunk)
            i = j
            continue
        if s[i] == "[":
            depth = 1
            j = i + 1
            while j < len(s) and depth > 0:
                if s[j] == "[":
                    depth += 1
                elif s[j] == "]":
                    depth -= 1
                j += 1
            chunk = s[i:j]
            if '"' in chunk:
                try:
                    arr = json.loads(chunk)
                    for item in arr:
                        lines.append(f"- {item}" if isinstance(item, str) else f"- {json.dumps(item)}")
                except (json.JSONDecodeError, TypeError):
                    lines.append(chunk)
            else:
                lines.append(chunk)
            i = j
            continue
        nl = s.find("\n", i)
        if nl == -1:
            line = s[i:].strip()
            if line and _looks_like_json_or_object_fragment(line):
                if line.startswith('"') and ":" in line:
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        key = parts[0].strip().strip('"').replace("_", " ").title()
                        val = parts[1].strip().strip('"')
                        lines.append(f"{key}: {val}")
                    else:
                        lines.append(line)
                else:
                    lines.append(line)
            elif line:
                lines.append(line)
            break
        line = s[i:nl].strip()
        if line and _looks_like_json_or_object_fragment(line):
            if '": "' in line or '":' in line:
                try:
                    idx = line.find(":")
                    if idx != -1:
                        key = line[:idx].strip().strip('"').replace("_", " ").title()
                        val = line[idx + 1 :].strip().strip('"')
                        if key and val:
                            lines.append(f"{key}: {val}")
                        else:
                            lines.append(line)
                    else:
                        lines.append(line)
                except Exception:
                    lines.append(line)
            else:
                lines.append(line)
        elif line:
            lines.append(line)
        i = nl + 1
    result = "\n".join(lines).strip()
    return result if result else text


def _streaming_section_marker_instruction(section_keys: List[str]) -> str:
    """Return prompt suffix instructing the LLM to use [[SECTION:key]] markers and stream-friendly content."""
    lines = [
        "OUTPUT FORMAT (required for streaming):",
        "You MUST start each section with the exact marker on its own line, then the section content.",
        "Use ONLY these markers with the exact keys below. Do not add extra text before or inside the marker.",
        "",
        "CONTENT STYLE INSIDE EACH SECTION (critical for clean streaming):",
        "- Write HUMAN-READABLE content only: prose, bullet lists (- item), numbered lists (1. item), or markdown.",
        "- Do NOT output raw JSON or object syntax inside section content (no {\"key\": \"value\"}, no [\"a\",\"b\"]).",
        "- Use plain text with labels, e.g. 'Description:\\nStudents will...' or 'Criteria:\\n- A\\n- B\\n- C'.",
        "- Tables: use markdown table syntax (| A | B |) only when complete; otherwise use bullet or numbered list.",
        "- Write as if for a document a teacher will read. No raw API-style structures.",
        "",
    ]
    for key in section_keys:
        lines.append(f"  [[SECTION:{key}]]")
    lines.extend([
        "",
        "Example:",
        "[[SECTION:challenge_title]]",
        "Bridge Engineering Challenge",
        "",
        "[[SECTION:challenge_brief]]",
        "Design a bridge that holds the most coins.",
        "",
        "Begin your response with the first section marker and content. No preamble.",
    ])
    return "\n".join(lines)


def _parse_section_marker_response(raw: str, section_keys: List[str]) -> Dict[str, Any]:
    """Parse response that uses [[SECTION:key]] markers into a dict. Returns {} if no markers found."""
    if not raw or not section_keys:
        return {}
    out: Dict[str, Any] = {}
    remaining = raw
    for key in section_keys:
        marker = f"{SECTION_MARKER_PREFIX}{key}{SECTION_MARKER_SUFFIX}"
        if marker not in remaining:
            continue
        start = remaining.find(marker) + len(marker)
        next_marker_pos = len(remaining)
        for other in section_keys:
            if other == key:
                continue
            other_marker = f"{SECTION_MARKER_PREFIX}{other}{SECTION_MARKER_SUFFIX}"
            idx = remaining.find(other_marker, start)
            if idx != -1 and idx < next_marker_pos:
                next_marker_pos = idx
        content = remaining[start:next_marker_pos].strip()
        if content:
            out[key] = content
    return out


# ---------------------------------------------------------------------------
# Stream FSM: deterministic section lifecycle (section_start -> content -> section_end)
# ---------------------------------------------------------------------------

STREAM_DEBUG = True  # Set to False to reduce log noise
FAILSAFE_NO_MARKER_CHARS = 2000  # If no marker seen in this many chars, start first section
STALL_FAULT_TOLERANT_CHARS = 300  # If in section and no new marker in this many chars, flush and emit all remaining sections (GPT-style: never stick on one card)


def _find_complete_marker(buffer: str, start: int) -> Optional[Tuple[int, int, str]]:
    """
    Find the next complete [[SECTION:key]] marker in buffer from start.
    Returns (marker_start, marker_end, section_key) or None if no complete marker.
    marker_end is the index after the closing ]].
    """
    idx = buffer.find(SECTION_MARKER_PREFIX, start)
    if idx == -1:
        return None
    end_bracket = buffer.find(SECTION_MARKER_SUFFIX, idx)
    if end_bracket == -1:
        return None  # Incomplete marker, need more data
    key_part = buffer[idx + len(SECTION_MARKER_PREFIX):end_bracket].strip()
    section_key = "".join(c for c in key_part if c.isalnum() or c == "_").strip() or None
    if not section_key:
        return None
    return (idx, end_bracket + len(SECTION_MARKER_SUFFIX), section_key)


def _process_stream_buffer(
    buffer: str,
    pos: int,
    current_section: Optional[str],
    emitted_section_keys: set,
    section_keys: List[str],
    output_schema: Dict[str, Any],
    template_slug: str,
    stream_finished: bool,
) -> Tuple[List[Dict[str, Any]], int, Optional[str], set]:
    """
    FSM: process buffer from pos, yield section events. Never emits partial marker text.
    Returns (events, new_pos, new_current_section, new_emitted).
    When stream_finished is False and we need more data to see a complete marker, returns empty events.
    """
    events: List[Dict[str, Any]] = []
    emitted = set(emitted_section_keys)
    if not section_keys:
        return (events, pos, current_section, emitted)

    # --- Before first section: wait for complete first marker or failsafe ---
    if current_section is None:
        found = _find_complete_marker(buffer, pos)
        if found:
            marker_start, marker_end, section_key = found
            if section_key not in section_keys:
                # Unknown key: skip this marker, advance pos and retry
                return _process_stream_buffer(
                    buffer, marker_end, None, emitted, section_keys,
                    output_schema, template_slug, stream_finished,
                )
            content_before = buffer[pos:marker_start]
            if content_before.strip():
                clean = _strip_section_markers(content_before.strip())
                if clean:
                    first_key = section_keys[0]
                    if section_key == first_key:
                        # Content belongs to this section
                        label = section_label_from_schema(section_key, output_schema)
                        events.append({"type": "section_start", "section": section_key, "label": label, "template_slug": template_slug})
                        norm_clean = _normalize_section_content_for_streaming(clean)
                        events.append({"type": "section_content", "section": section_key, "chunk": norm_clean, "content": norm_clean, "template_slug": template_slug})
                        emitted.add(section_key)
                        return (events, marker_end, section_key, emitted)
                    # Model skipped first section: emit first with content, then this section
                    label_first = section_label_from_schema(first_key, output_schema)
                    events.append({"type": "section_start", "section": first_key, "label": label_first, "template_slug": template_slug})
                    norm_clean = _normalize_section_content_for_streaming(clean)
                    events.append({"type": "section_content", "section": first_key, "chunk": norm_clean, "content": norm_clean, "template_slug": template_slug})
                    events.append({"type": "section_end", "section": first_key, "template_slug": template_slug})
                    emitted.add(first_key)
            # If we already emitted this section (e.g. from stall failsafe), don't duplicate section_start
            if section_key in emitted:
                return (events, marker_end, section_key, emitted)
            label = section_label_from_schema(section_key, output_schema)
            events.append({"type": "section_start", "section": section_key, "label": label, "template_slug": template_slug})
            emitted.add(section_key)
            return (events, marker_end, section_key, emitted)
        # Failsafe: no marker yet but lots of content
        if (len(buffer) - pos) >= FAILSAFE_NO_MARKER_CHARS and not stream_finished:
            first_key = section_keys[0]
            label = section_label_from_schema(first_key, output_schema)
            chunk = _strip_section_markers(buffer[pos:].strip())
            if not chunk:
                chunk = "Content unavailable."
            events.append({"type": "section_start", "section": first_key, "label": label, "template_slug": template_slug})
            norm_chunk = _normalize_section_content_for_streaming(chunk)
            events.append({"type": "section_content", "section": first_key, "chunk": norm_chunk, "content": norm_chunk, "template_slug": template_slug})
            emitted.add(first_key)
            return (events, len(buffer), first_key, emitted)
        return (events, pos, current_section, emitted)

    # --- In section: emit content up to next complete marker or end of buffer ---
    next_marker = _find_complete_marker(buffer, pos)
    if next_marker is None:
        # No complete marker: emit everything from pos to end (or to start of partial marker)
        # If we see [[SECTION: but no ]], hold that in buffer (don't emit partial)
        partial = buffer.find(SECTION_MARKER_PREFIX, pos)
        if partial != -1 and not stream_finished:
            # Emit only up to partial so we don't emit partial marker
            content = buffer[pos:partial]
            clean = _strip_section_markers(content)
            if clean.strip():
                norm_clean = _normalize_section_content_for_streaming(clean)
                events.append({"type": "section_content", "section": current_section, "chunk": norm_clean, "content": norm_clean, "template_slug": template_slug})
            return (events, partial, current_section, emitted)
        # Emit to end of buffer
        content = buffer[pos:]
        clean = _strip_section_markers(content)
        if clean.strip():
            norm_clean = _normalize_section_content_for_streaming(clean)
            events.append({"type": "section_content", "section": current_section, "chunk": norm_clean, "content": norm_clean, "template_slug": template_slug})
        return (events, len(buffer), current_section, emitted)

    marker_start, marker_end, section_key = next_marker
    # Emit content before marker, then section_end, then section_start for new section
    content_before = buffer[pos:marker_start]
    clean_before = _strip_section_markers(content_before)
    if clean_before.strip():
        norm_before = _normalize_section_content_for_streaming(clean_before)
        events.append({"type": "section_content", "section": current_section, "chunk": norm_before, "content": norm_before, "template_slug": template_slug})
    events.append({"type": "section_end", "section": current_section, "template_slug": template_slug})

    if section_key not in section_keys:
        # Unknown key: stay in same section, advance past this marker and continue
        return (events, marker_end, current_section, emitted)

    label = section_label_from_schema(section_key, output_schema)
    events.append({"type": "section_start", "section": section_key, "label": label, "template_slug": template_slug})
    emitted.add(section_key)
    return (events, marker_end, section_key, emitted)


def _flush_end_of_stream(
    buffer: str,
    pos: int,
    current_section: Optional[str],
    emitted_section_keys: set,
    section_keys: List[str],
    output_schema: Dict[str, Any],
    template_slug: str,
) -> List[Dict[str, Any]]:
    """Flush remaining buffer to current section, close it, emit any missing schema sections, then caller emits done."""
    events: List[Dict[str, Any]] = []
    emitted = set(emitted_section_keys)

    if current_section is not None:
        remainder = buffer[pos:]
        clean = _strip_section_markers(remainder.strip())
        if clean:
            norm_clean = _normalize_section_content_for_streaming(clean)
            events.append({"type": "section_content", "section": current_section, "chunk": norm_clean, "content": norm_clean, "template_slug": template_slug})
        events.append({"type": "section_end", "section": current_section, "template_slug": template_slug})

    for key in section_keys:
        if key in emitted:
            continue
        label = section_label_from_schema(key, output_schema)
        events.append({"type": "section_start", "section": key, "label": label, "template_slug": template_slug})
        events.append({"type": "section_content", "section": key, "chunk": "Content unavailable.", "content": "Content unavailable.", "template_slug": template_slug})
        events.append({"type": "section_end", "section": key, "template_slug": template_slug})
    return events


class ExecutionService:
    """
    Service responsible for executing templates.

    Can use either stubbed output (default) or real LLM (when USE_REAL_LLM=True).
    """

    DUMMY_MODEL_USED = "stub-model"
    DUMMY_PROVIDER_USED = "stub-provider"
    
    _model_router: Optional[ModelRouter] = None
    _toon_handler: Optional[TOONHandler] = None
    _prompt_builder: Optional[TOONPromptBuilder] = None
    _cache: Optional[ResponseCache] = None
    _rate_limiter: Optional[RateLimiter] = None
    _cost_tracker: Optional[CostTracker] = None
    
    @classmethod
    def _get_model_router(cls) -> ModelRouter:
        """Get or create model router instance with cache, rate limiter, and cost tracker."""
        if cls._model_router is None:
            # Initialize cache
            if cls._cache is None and llm_settings.CACHE_ENABLED:
                cls._cache = ResponseCache(
                    ttl_seconds=llm_settings.CACHE_TTL_SECONDS,
                    redis_url=llm_settings.REDIS_URL
                )
            
            # Initialize rate limiter
            if cls._rate_limiter is None and llm_settings.RATE_LIMIT_ENABLED:
                cls._rate_limiter = RateLimiter(llm_settings)
            
            # Initialize cost tracker
            if cls._cost_tracker is None and llm_settings.COST_TRACKING_ENABLED:
                cls._cost_tracker = CostTracker()
            
            cls._model_router = ModelRouter(
                config=llm_settings,
                cache=cls._cache,
                rate_limiter=cls._rate_limiter,
                cost_tracker=cls._cost_tracker,
            )
        return cls._model_router
    
    @classmethod
    def _get_toon_handler(cls) -> TOONHandler:
        """Get or create TOON handler instance."""
        if cls._toon_handler is None:
            cls._toon_handler = TOONHandler()
        return cls._toon_handler
    
    @classmethod
    def _get_prompt_builder(cls) -> TOONPromptBuilder:
        """Get or create prompt builder instance."""
        if cls._prompt_builder is None:
            cls._prompt_builder = TOONPromptBuilder(cls._get_toon_handler())
        return cls._prompt_builder

    @classmethod
    def _ensure_real_llm_configured(cls) -> None:
        """
        When USE_REAL_LLM is True, ensure at least one provider API key is set.
        Raises ValueError with clear message so template execution does not fail silently.
        """
        if not llm_settings.USE_REAL_LLM:
            return
        has_key = bool(
            llm_settings.OPENAI_API_KEY
            or llm_settings.ANTHROPIC_API_KEY
            or llm_settings.GOOGLE_API_KEY
        )
        if not has_key:
            raise ValueError(
                "USE_REAL_LLM is true but no LLM API key is set. "
                "Set OPENAI_API_KEY, ANTHROPIC_API_KEY, or GOOGLE_API_KEY in .env, "
                "or set USE_REAL_LLM=false to use stub output."
            )

    @classmethod
    def _build_stub_output_dict(
        cls,
        template: Template,
        template_version: Optional[TemplateVersion],
        input_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Build stub output as a dict from template version's output_schema and stub_config.
        Generic: works for any template shape (lesson plan, STEAM, assessment, etc.).
        """
        output_schema = {}
        if template_version and getattr(template_version, "output_schema", None):
            output_schema = template_version.output_schema or {}
        if not isinstance(output_schema, dict):
            output_schema = {}

        stub_config = (
            (template_version and getattr(template_version, "stub_config", None))
            or getattr(template, "stub_config", None)
            or {}
        )
        if not isinstance(stub_config, dict):
            stub_config = {}

        return generic_build_stub_output(
            output_schema=output_schema,
            stub_config=stub_config,
            input_data=input_data,
            template_name=template.name,
        )

    @classmethod
    def _build_prompt(
        cls,
        template: Template,
        template_version: TemplateVersion,
        input_data: Dict[str, Any],
    ) -> Tuple[str, str]:
        """
        Build prompt using TOON-aware prompt builder.
        
        Returns:
            Tuple of (system_message, user_prompt)
        """
        prompt_builder = cls._get_prompt_builder()
        prompt_definition = template_version.prompt_definition or {}
        
        system_message, user_prompt = prompt_builder.build_prompt(
            input_data=input_data,
            prompt_definition=prompt_definition,
            template_category=template.category,
            model_config=template_version.model_config,
            output_schema=template_version.output_schema if getattr(template_version, "output_schema", None) else None,
        )
        
        return system_message, user_prompt

    @classmethod
    def _unwrap_schema_shaped_output(cls, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """
        If the LLM returned a JSON Schema-shaped object (type, title, required, properties)
        with the actual content inside 'properties', return the inner data so the API
        returns a flat output dict. Frontend expects output.title, output.overview, etc.
        """
        if not isinstance(parsed, dict) or not parsed:
            return parsed
        props = parsed.get("properties")
        if not isinstance(props, dict) or not props:
            return parsed
        # Schema "properties" have values like {"type": "string", "title": "..."}.
        # Data "properties" have values like "Lesson title", ["goal1"], {"level": "Create"}, etc.
        first_val = next(iter(props.values()), None)
        if first_val is None:
            return parsed
        if isinstance(first_val, dict) and "type" in first_val and "title" in first_val:
            # Looks like a schema property definition, not actual data
            return parsed
        # Unwrap: use properties as the output
        logger.info("Unwrapping schema-shaped LLM output (content was in 'properties')")
        return props

    @classmethod
    def _parse_llm_response(
        cls,
        content: str,
        template: Template,
        template_version: Optional[TemplateVersion] = None,
        input_data: Optional[Dict[str, Any]] = None,
        use_stub_on_failure: bool = True,
    ) -> Dict[str, Any]:
        """
        Parse LLM response into a dict matching the template's output shape.
        Uses TOON handler; unwraps if LLM returned schema-shaped output (data in 'properties').
        When use_stub_on_failure=True, on failure returns stub dict. When False (e.g. real LLM path),
        returns {} so caller does not show stub instead of LLM output.
        """
        toon_handler = cls._get_toon_handler()
        try:
            schema = None
            if template_version and getattr(template_version, "output_schema", None):
                schema = json.dumps(template_version.output_schema) if isinstance(template_version.output_schema, dict) else str(template_version.output_schema)
            parsed = toon_handler.parse_output(content, schema=schema)
            if isinstance(parsed, dict) and parsed:
                return cls._unwrap_schema_shaped_output(parsed)
            try:
                raw_json = json.loads(content.strip())
                if isinstance(raw_json, dict) and raw_json:
                    return cls._unwrap_schema_shaped_output(raw_json)
            except Exception:
                pass
            if use_stub_on_failure:
                return cls._build_stub_output_dict(template, template_version, input_data=input_data or {"topic": "Parsed response was empty"})
            logger.warning("Parse returned empty; use_stub_on_failure=False so returning {}")
            return {}
        except Exception as e:
            logger.error(f"Error parsing LLM response: {e}")
            try:
                raw_json = json.loads(content.strip())
                if isinstance(raw_json, dict) and raw_json:
                    return cls._unwrap_schema_shaped_output(raw_json)
            except Exception:
                pass
            if use_stub_on_failure:
                return cls._build_stub_output_dict(template, template_version, input_data=input_data or {"topic": "Error parsing response"})
            return {}

    @classmethod
    def _naive_parse_text(cls, text: str) -> Dict[str, Any]:
        """Very naive text parser - extracts basic structure from text."""
        # This is a placeholder - in production, use more sophisticated parsing
        return {
            "overview": text[:200] if len(text) > 200 else text,
            "learning_goals": ["Extracted from response"],
            "materials": ["Materials needed"],
            "steps": [{"title": "Step 1", "description": text[:500]}],
            "differentiation": ["Differentiation strategies"],
            "teacher_notes": ["See generated content"],
        }

    @classmethod
    def _build_output_from_dict(
        cls,
        data: Dict[str, Any],
        template: Template,
    ) -> UniversalTemplateOutput:
        """Build UniversalTemplateOutput from parsed dictionary."""
        # Extract steps
        steps = []
        if "steps" in data and isinstance(data["steps"], list):
            for step in data["steps"]:
                if isinstance(step, dict):
                    steps.append(LessonStep(
                        title=step.get("title", "Step"),
                        description=step.get("description", "")
                    ))
                elif isinstance(step, str):
                    steps.append(LessonStep(title="Step", description=step))
        
        # Extract bloom alignment
        bloom_alignment = []
        if "bloom_alignment" in data and isinstance(data["bloom_alignment"], list):
            for item in data["bloom_alignment"]:
                if isinstance(item, dict):
                    level_str = item.get("level", "understand")
                    try:
                        level = BloomLevel(level_str)
                    except ValueError:
                        level = BloomLevel.UNDERSTAND
                    bloom_alignment.append(BloomAlignmentItem(
                        level=level,
                        description=item.get("description", "")
                    ))
        
        # Extract assessment
        assessment = None
        if "assessment" in data and isinstance(data["assessment"], dict):
            assessment = AssessmentSection(
                checks_for_understanding=data["assessment"].get("checks_for_understanding", []),
                rubric=data["assessment"].get("rubric")
            )
        
        # Extract questions (for assessment templates)
        questions = None
        if template.category == TemplateCategory.ASSESSMENT and "questions" in data:
            if isinstance(data["questions"], list):
                questions = []
                for q in data["questions"]:
                    if isinstance(q, dict):
                        questions.append(AssessmentQuestion(
                            question_text=q.get("question_text", ""),
                            type=q.get("type", "short_answer"),
                            answer_key=q.get("answer_key"),
                            difficulty=q.get("difficulty")
                        ))
        
        # Extract communication (for communication templates)
        communication = None
        if template.category == TemplateCategory.COMMUNICATION and "communication" in data:
            if isinstance(data["communication"], dict):
                comm_data = data["communication"]
                communication = CommunicationSection(
                    subject_line=comm_data.get("subject_line", ""),
                    message_body=comm_data.get("message_body", ""),
                    key_details=comm_data.get("key_details", []),
                    call_to_action=comm_data.get("call_to_action", "")
                )
        
        try:
            return UniversalTemplateOutput(
                overview=data.get("overview", "") or "Generated content",
                learning_goals=data.get("learning_goals", []) or [],
                materials=data.get("materials", []) or [],
                steps=steps if steps else [LessonStep(title="Step 1", description="See generated content")],
                differentiation=data.get("differentiation", []) or [],
                assessment=assessment,
                teacher_notes=data.get("teacher_notes", []) or [],
                bloom_alignment=bloom_alignment if bloom_alignment else [],
                questions=questions,
                communication=communication,
            )
        except Exception as e:
            logger.error(f"Error building UniversalTemplateOutput: {e}, data keys: {list(data.keys()) if isinstance(data, dict) else 'not a dict'}")
            # Return minimal valid output
            return UniversalTemplateOutput(
                overview=data.get("overview", "Generated content") if isinstance(data, dict) else "Generated content",
                learning_goals=[],
                materials=[],
                steps=[LessonStep(title="Step 1", description="See generated content")],
                differentiation=[],
                assessment=None,
                teacher_notes=[],
                bloom_alignment=[],
                questions=None,
                communication=None,
            )

    @classmethod
    async def execute(
        cls,
        db: Session,
        *,
        template: Template,
        template_version: TemplateVersion,
        input_data: Dict[str, Any],
        user_id: Optional[uuid.UUID] = None,
        tenant_id: Optional[uuid.UUID] = None,
        is_demo: bool = False,
    ) -> Tuple[TemplateExecution, Dict[str, Any]]:
        """
        Execute a template with stubbed or real LLM output and persist a TemplateExecution.

        Returns the persisted TemplateExecution and the output as a dict (shape from template's output_schema).
        """
        start_time = time.perf_counter()
        use_real_llm = bool(
            llm_settings.USE_REAL_LLM and getattr(llm_settings, "LLM_OUTBOUND_ENABLED", True)
        )
        llm_response = None

        if use_real_llm:
            cls._ensure_real_llm_configured()
            logger.info(f"Using real LLM with TOON for template execution: {template.slug}")
            system_message, user_prompt = cls._build_prompt(template, template_version, input_data)
            model_config = template_version.model_config
            router = cls._get_model_router()
            llm_response = await router.generate(
                system_message=system_message,
                prompt=user_prompt,
                model_config=model_config,
            )
            output_dict = cls._parse_llm_response(llm_response.content, template, template_version)
            model_used = llm_response.model_used
            provider_used = llm_response.provider
            token_usage_dict = {
                "prompt": llm_response.token_usage.prompt if llm_response.token_usage else 0,
                "completion": llm_response.token_usage.completion if llm_response.token_usage else 0,
                "total": llm_response.token_usage.total if llm_response.token_usage else 0,
            }
            latency_ms = llm_response.latency_ms
            cost_estimate = llm_response.cost_estimate
        else:
            if llm_settings.USE_REAL_LLM and not getattr(llm_settings, "LLM_OUTBOUND_ENABLED", True):
                logger.info(
                    f"Using stubbed output for template execution (LLM_OUTBOUND_ENABLED=false): {template.slug}"
                )
            else:
                logger.info(f"Using stubbed output for template execution: {template.slug}")
            output_dict = cls._build_stub_output_dict(template, template_version, input_data)
            model_used = cls.DUMMY_MODEL_USED
            provider_used = cls.DUMMY_PROVIDER_USED
            token_usage_dict = {"prompt": 0, "completion": 0, "total": 0}
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            cost_estimate = 0

        cache_hit = getattr(llm_response, "cache_hit", False) if llm_response is not None else False

        execution = TemplateExecution(
            template_id=template.id,
            template_version_id=template_version.id,
            template_version=template_version.version,
            user_id=user_id,
            tenant_id=tenant_id,
            input_data=input_data,
            output_data=output_dict,
            model_used=model_used,
            provider_used=provider_used,
            token_usage=token_usage_dict,
            cost_estimate=cost_estimate,
            latency_ms=latency_ms,
            cache_hit=cache_hit,
            alignment_flags=None,
        )

        db.add(execution)
        db.commit()
        db.refresh(execution)

        return execution, output_dict

    @classmethod
    async def execute_stream(
        cls,
        db: Session,
        *,
        template: Template,
        template_version: TemplateVersion,
        input_data: Dict[str, Any],
        user_id: Optional[uuid.UUID] = None,
        tenant_id: Optional[uuid.UUID] = None,
        is_demo: bool = False,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Execute a template with streaming LLM output, yielding domain events.

        Yields structured domain events (JSON-serializable dictionaries):
        - {"type": "meta", "template_slug": "...", "timestamp": "..."}
        - {"type": "section_start", "section": "...", "label": "...", "template_slug": "..."}
        - {"type": "section_content", "chunk": "...", "template_slug": "..."}
        - {"type": "done", "execution_id": "...", "template_slug": "..."}
        - {"type": "error", "message": "...", "template_slug": "..."}
        Does NOT yield raw "content" events; only schema-based section events.

        Args:
            db: Database session
            template: Template instance
            template_version: TemplateVersion instance
            input_data: Input data dictionary
            user_id: Optional user ID
            tenant_id: Optional tenant ID
            is_demo: Whether this is a demo execution

        Yields:
            Domain events as dictionaries
        """
        start_time = time.perf_counter()
        output_schema = (template_version and getattr(template_version, "output_schema", None)) or {}
        if not isinstance(output_schema, dict):
            output_schema = {}
        sections_schema = load_template_schema(template.slug, output_schema)
        # Use template JSON sections as source of truth so we always stream all cards (GPT-style)
        section_keys = [s["key"] for s in sections_schema] if sections_schema else _ordered_section_keys_from_schema(output_schema)
        if not section_keys:
            section_keys = _ordered_section_keys_from_schema(output_schema)
        if not section_keys:
            section_keys = list((output_schema.get("properties") or {}).keys())

        # Emit meta event with schema for frontend-driven rendering
        meta_ev = {
            "type": "meta",
            "template": template.slug,
            "template_slug": template.slug,
            "template_name": template.name,
            "timestamp": time.time(),
            "sections": sections_schema,
        }
        if STREAM_DEBUG:
            logger.info("stream_ev: meta")
        yield meta_ev

        use_real_llm = bool(
            llm_settings.USE_REAL_LLM and getattr(llm_settings, "LLM_OUTBOUND_ENABLED", True)
        )

        if not use_real_llm:
            output_dict = cls._build_stub_output_dict(template, template_version, input_data)
            if not section_keys and output_dict:
                section_keys = list(output_dict.keys())
            if not section_keys:
                section_keys = list((output_schema.get("properties") or {}).keys())
            for section_key in section_keys:
                value = output_dict.get(section_key)
                section_text = section_value_to_markdown_text(value) if value is not None else ""
                if not (section_text and section_text.strip()):
                    section_text = "Content."
                label = section_label_from_schema(section_key, output_schema)
                yield {
                    "type": "section_start",
                    "section": section_key,
                    "label": label,
                    "template_slug": template.slug,
                }
                words = section_text.strip().split(" ")
                for i, word in enumerate(words):
                    chunk_to_send = _strip_section_markers(word if i == 0 else " " + word)
                    if chunk_to_send:
                        yield {
                            "type": "section_content",
                            "section": section_key,
                            "chunk": chunk_to_send,
                            "content": chunk_to_send,
                            "template_slug": template.slug,
                        }
                        await asyncio.sleep(0)
                yield {"type": "section_end", "section": section_key, "template_slug": template.slug}
            execution = TemplateExecution(
                template_id=template.id,
                template_version_id=template_version.id,
                template_version=template_version.version,
                user_id=user_id,
                tenant_id=tenant_id,
                input_data=input_data,
                output_data=output_dict,
                model_used=cls.DUMMY_MODEL_USED,
                provider_used=cls.DUMMY_PROVIDER_USED,
                token_usage={"prompt": 0, "completion": 0, "total": 0},
                cost_estimate=0,
                latency_ms=int((time.perf_counter() - start_time) * 1000),
                cache_hit=False,
                alignment_flags=None,
            )
            db.add(execution)
            db.commit()
            db.refresh(execution)
            
            yield {
                "type": "done",
                "execution_id": str(execution.id),
                "template_slug": template.slug,
            }
            return

        # Real LLM: stream with FSM (section_start -> section_content -> section_end per section, then done)
        cls._ensure_real_llm_configured()
        try:
            logger.info(f"Streaming LLM execution for template: {template.slug}")
            system_message, user_prompt = cls._build_prompt(template, template_version, input_data)
            if not section_keys and sections_schema:
                section_keys = [s["key"] for s in sections_schema]
            if not section_keys:
                section_keys = list((output_schema.get("properties") or {}).keys())
            if section_keys:
                marker_instruction = _streaming_section_marker_instruction(section_keys)
                user_prompt = user_prompt.rstrip() + "\n\n" + marker_instruction

            model_config = template_version.model_config or {}
            router = cls._get_model_router()
            full_content: List[str] = []

            buffer = ""
            pos = 0
            current_section: Optional[str] = None
            emitted_section_keys: set = set()

            def _log_ev(ev: Dict[str, Any]) -> None:
                if not STREAM_DEBUG:
                    return
                t = ev.get("type", "")
                sec = ev.get("section", "")
                if t == "section_content":
                    logger.info("stream_ev: section_content %s len=%s", sec, len(ev.get("chunk", "")))
                else:
                    logger.info("stream_ev: %s %s", t, sec or "")

            async for token in router.stream(
                system_message=system_message,
                prompt=user_prompt,
                model_config=model_config,
            ):
                if not token:
                    continue
                full_content.append(token)
                buffer += token

                while True:
                    events, new_pos, new_section, new_emitted = _process_stream_buffer(
                        buffer, pos, current_section, emitted_section_keys,
                        section_keys, output_schema, template.slug, stream_finished=False,
                    )
                    if not events:
                        # Stall failsafe (GPT-style): if stuck in one section with no new marker, close it and emit ALL remaining sections so UI never sticks
                        if current_section and (len(buffer) - pos) >= STALL_FAULT_TOLERANT_CHARS:
                            raw_remainder = buffer[pos:]
                            if raw_remainder.lstrip().startswith(SECTION_MARKER_PREFIX) and SECTION_MARKER_SUFFIX not in raw_remainder[:100]:
                                first_nl = raw_remainder.find("\n")
                                raw_remainder = raw_remainder[first_nl + 1:] if first_nl != -1 else ""
                            remainder = _strip_section_markers(raw_remainder.strip())
                            if remainder:
                                norm_rem = _normalize_section_content_for_streaming(remainder)
                                yield {"type": "section_content", "section": current_section, "chunk": norm_rem, "content": norm_rem, "template_slug": template.slug}
                                _log_ev({"type": "section_content", "section": current_section, "chunk": norm_rem})
                            yield {"type": "section_end", "section": current_section, "template_slug": template.slug}
                            _log_ev({"type": "section_end", "section": current_section})
                            pos = len(buffer)
                            emitted_section_keys.add(current_section)
                            current_section = None
                            # Emit every remaining schema section so all cards appear (no stuck UI)
                            for key in section_keys:
                                if key in emitted_section_keys:
                                    continue
                                label = section_label_from_schema(key, output_schema)
                                yield {"type": "section_start", "section": key, "label": label, "template_slug": template.slug}
                                _log_ev({"type": "section_start", "section": key})
                                yield {"type": "section_content", "section": key, "chunk": "Content unavailable.", "content": "Content unavailable.", "template_slug": template.slug}
                                yield {"type": "section_end", "section": key, "template_slug": template.slug}
                                _log_ev({"type": "section_end", "section": key})
                                emitted_section_keys.add(key)
                            continue
                        break
                    for ev in events:
                        _log_ev(ev)
                        yield ev
                        await asyncio.sleep(0)
                    pos, current_section, emitted_section_keys = new_pos, new_section, new_emitted
                    if pos >= len(buffer):
                        break

            if STREAM_DEBUG:
                logger.info("stream_ev: parser at stream finish buffer_len=%s pos=%s current_section=%s", len(buffer), pos, current_section)

            # End of stream: flush remainder, close open section, emit missing schema sections
            end_events = _flush_end_of_stream(
                buffer, pos, current_section, emitted_section_keys,
                section_keys, output_schema, template.slug,
            )
            for ev in end_events:
                _log_ev(ev)
                yield ev
                await asyncio.sleep(0)

            if STREAM_DEBUG:
                logger.info("stream_ev: done (about to emit)")

            raw_content = "".join(full_content)
            output_dict = _parse_section_marker_response(raw_content, section_keys or [])
            if not output_dict:
                output_dict = cls._parse_llm_response(
                    raw_content, template, template_version,
                    input_data=input_data,
                    use_stub_on_failure=False,
                )
            if not isinstance(output_dict, dict):
                output_dict = {}
            if not section_keys and output_dict:
                section_keys = list(output_dict.keys())
            if not section_keys:
                section_keys = list((output_schema.get("properties") or {}).keys()) or list(output_dict.keys())
            for k, v in list(output_dict.items()):
                if isinstance(v, str) and _looks_like_json_or_object_fragment(v):
                    output_dict[k] = _normalize_section_content_for_streaming(v)
            stub_dict = cls._build_stub_output_dict(template, template_version, input_data) if section_keys else {}
            merged_output = {}
            for key in section_keys:
                merged_output[key] = output_dict.get(key) if output_dict.get(key) is not None else stub_dict.get(key)
            output_dict = merged_output

            token_usage = {"prompt": 0, "completion": 0, "total": 0}
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            execution = TemplateExecution(
                template_id=template.id,
                template_version_id=template_version.id,
                template_version=template_version.version,
                user_id=user_id,
                tenant_id=tenant_id,
                input_data=input_data,
                output_data=output_dict,
                model_used=model_config.get("model") or llm_settings.DEFAULT_MODEL,
                provider_used=model_config.get("provider") or llm_settings.DEFAULT_MODEL_PROVIDER,
                token_usage=token_usage,
                cost_estimate=0.0,
                latency_ms=latency_ms,
                cache_hit=False,
                alignment_flags=None,
            )
            db.add(execution)
            db.commit()
            db.refresh(execution)
            yield {
                "type": "done",
                "execution_id": str(execution.id),
                "template_slug": template.slug,
                "output_data": output_dict,
            }
        except Exception as e:
            logger.error(f"Streaming execution error for template {template.slug}: {e}", exc_info=True)

            pd: Dict[str, Any] = {}
            raw_pd = getattr(template_version, "prompt_definition", None)
            if isinstance(raw_pd, dict):
                pd = raw_pd
            elif isinstance(raw_pd, str):
                try:
                    pd = json.loads(raw_pd)
                except Exception:
                    pd = {}
            exemplar_dict = pd.get("exemplar_output") if isinstance(pd, dict) else None
            if not isinstance(exemplar_dict, dict):
                exemplar_dict = {}

            def _exemplar_has_content() -> bool:
                for key in section_keys:
                    val = exemplar_dict.get(key)
                    if val is None:
                        continue
                    text = section_value_to_markdown_text(val)
                    if isinstance(text, str) and text.strip():
                        return True
                return False

            if _exemplar_has_content():
                failure_msg = (
                    "The AI provider could not complete this request. "
                    "Below is the exemplar output from this template."
                )
                for section_key in section_keys:
                    label = section_label_from_schema(section_key, output_schema)
                    raw_val = exemplar_dict.get(section_key)
                    section_text = (
                        section_value_to_markdown_text(raw_val) if raw_val is not None else ""
                    )
                    if not (section_text and section_text.strip()):
                        section_text = "*(No exemplar content for this section.)*"
                    yield {
                        "type": "section_start",
                        "section": section_key,
                        "label": label,
                        "template_slug": template.slug,
                    }
                    words = section_text.strip().split(" ")
                    for i, word in enumerate(words):
                        chunk_to_send = _strip_section_markers(word if i == 0 else " " + word)
                        if chunk_to_send:
                            yield {
                                "type": "section_content",
                                "section": section_key,
                                "chunk": chunk_to_send,
                                "content": chunk_to_send,
                                "template_slug": template.slug,
                            }
                            await asyncio.sleep(0)
                    yield {"type": "section_end", "section": section_key, "template_slug": template.slug}
                yield {
                    "type": "done",
                    "execution_id": None,
                    "template_slug": template.slug,
                    "provider_failed": True,
                    "failure_message": failure_msg,
                    "output_data": exemplar_dict,
                }
            else:
                yield {
                    "type": "error",
                    "message": f"Error during template execution: {str(e)}",
                    "template_slug": template.slug,
                }


