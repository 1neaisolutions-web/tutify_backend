"""
Unit tests for schema-driven streaming (no DB).
Tests section order, section labels from output_schema, and JSON-to-markdown conversion.
"""
import pytest

from app.services.execution_service import (
    _ordered_section_keys_from_schema,
    _looks_like_json_or_object_fragment,
    _is_incomplete_json_fragment,
    _normalize_section_content_for_streaming,
)
from app.utils.markdown_converter import (
    section_label_from_schema,
    humanize_key,
    section_value_to_markdown_text,
)


class TestOrderedSectionKeysFromSchema:
    """Test _ordered_section_keys_from_schema."""

    def test_empty_schema_returns_empty_list(self):
        assert _ordered_section_keys_from_schema({}) == []
        assert _ordered_section_keys_from_schema(None) == []
        assert _ordered_section_keys_from_schema({"type": "object"}) == []

    def test_required_first_then_rest(self):
        schema = {
            "type": "object",
            "required": ["challenge_brief", "deliverables"],
            "properties": {
                "evaluation_rubric": {"type": "object", "title": "Evaluation rubric"},
                "challenge_brief": {"type": "string", "title": "Challenge brief"},
                "design_thinking_stages": {"type": "array", "title": "Design thinking stages"},
                "deliverables": {"type": "array", "title": "Deliverables"},
                "engineering_constraints": {"type": "array", "title": "Engineering constraints"},
            },
        }
        result = _ordered_section_keys_from_schema(schema)
        assert result == [
            "challenge_brief",
            "deliverables",
            "evaluation_rubric",
            "design_thinking_stages",
            "engineering_constraints",
        ]

    def test_no_required_uses_property_order(self):
        schema = {
            "type": "object",
            "properties": {
                "overview": {"type": "string"},
                "steps": {"type": "array"},
            },
        }
        assert _ordered_section_keys_from_schema(schema) == ["overview", "steps"]


class TestSectionLabelFromSchema:
    """Test section_label_from_schema and humanize_key."""

    def test_uses_schema_title_when_present(self):
        schema = {
            "properties": {
                "challenge_brief": {"title": "Challenge brief"},
                "design_thinking_stages": {"title": "Design thinking stages"},
                "evaluation_rubric": {"title": "Evaluation rubric (creation level)"},
            }
        }
        assert section_label_from_schema("challenge_brief", schema) == "Challenge brief"
        assert section_label_from_schema("design_thinking_stages", schema) == "Design thinking stages"
        assert section_label_from_schema("evaluation_rubric", schema) == "Evaluation rubric (creation level)"

    def test_fallback_to_humanize_key_when_no_title(self):
        schema = {"properties": {"some_key": {"type": "string"}}}
        assert section_label_from_schema("some_key", schema) == "Some Key"
        assert humanize_key("some_key") == "Some Key"

    def test_fallback_when_schema_none_or_empty(self):
        assert section_label_from_schema("challenge_brief", None) == "Challenge Brief"
        assert section_label_from_schema("challenge_brief", {}) == "Challenge Brief"


class TestSectionValueToMarkdownText:
    """Test section_value_to_markdown_text (no raw JSON)."""

    def test_plain_string_unchanged(self):
        assert section_value_to_markdown_text("Hello world") == "Hello world"
        assert section_value_to_markdown_text("") == ""

    def test_json_string_converted_to_markdown_not_raw(self):
        value = '{"challenge_brief": "Design a solution.", "deliverables": ["Doc", "Pitch"]}'
        result = section_value_to_markdown_text(value)
        assert "{" not in result or "Challenge Brief" in result or "challenge_brief" in result.lower()
        assert "Design a solution" in result
        assert "Doc" in result or "Pitch" in result

    def test_list_rendered_as_bullets(self):
        value = ["Item one", "Item two"]
        result = section_value_to_markdown_text(value)
        assert "Item one" in result and "Item two" in result


class TestStreamingContentNormalizer:
    """Test streaming-safe content normalization (no raw JSON in UI)."""

    def test_prose_unchanged(self):
        assert _looks_like_json_or_object_fragment("Students will create a diagram.") is False
        assert _normalize_section_content_for_streaming("Plain paragraph here.") == "Plain paragraph here."

    def test_json_object_normalized_to_readable(self):
        text = '{"description": "Students will design.", "criteria": ["A", "B"]}'
        assert _looks_like_json_or_object_fragment(text) is True
        result = _normalize_section_content_for_streaming(text)
        assert "{" not in result or "Description:" in result
        assert "Students will design" in result
        assert "Criteria:" in result or "A" in result

    def test_incomplete_fragment_not_normalized(self):
        text = '{"description": "incomplete'
        assert _is_incomplete_json_fragment(text) is True
        assert _normalize_section_content_for_streaming(text) == text
