"""
Unit tests for YouTubeQuizService in app/domains/youtube_quiz/service.py.
LLM calls and transcript fetching are mocked.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.domains.youtube_quiz.service import (
    YouTubeQuizService,
    TranscriptContext,
    TranscriptUnavailableError,
)
from app.domains.youtube_quiz.schemas import YouTubeQuizGenerateRequest


# ---------------------------------------------------------------------------
# extract_video_id — pure URL parsing
# ---------------------------------------------------------------------------

class TestExtractVideoId:
    @pytest.mark.parametrize("url,expected", [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ])
    def test_valid_urls(self, url, expected):
        assert YouTubeQuizService.extract_video_id(url) == expected

    @pytest.mark.parametrize("url", [
        "",
        None,
        "https://vimeo.com/12345",
        "not-a-url",
    ])
    def test_invalid_urls_return_none(self, url):
        assert YouTubeQuizService.extract_video_id(url) is None

    def test_url_with_extra_params(self):
        url = "https://www.youtube.com/watch?v=abc123&t=30s&list=PLxxx"
        assert YouTubeQuizService.extract_video_id(url) == "abc123"


# ---------------------------------------------------------------------------
# _extract_json_payload
# ---------------------------------------------------------------------------

class TestExtractJsonPayload:
    def test_plain_json(self):
        raw = '{"title": "Test", "sections": []}'
        result = YouTubeQuizService._extract_json_payload(raw)
        assert result["title"] == "Test"

    def test_json_with_markdown_fences(self):
        raw = '```json\n{"title": "Test"}\n```'
        result = YouTubeQuizService._extract_json_payload(raw)
        assert result["title"] == "Test"

    def test_json_embedded_in_text(self):
        raw = 'Here is the result: {"key": "value"} extra text'
        result = YouTubeQuizService._extract_json_payload(raw)
        assert result["key"] == "value"

    def test_invalid_json_raises(self):
        with pytest.raises(Exception):
            YouTubeQuizService._extract_json_payload("not json at all")


# ---------------------------------------------------------------------------
# _build_style_distribution
# ---------------------------------------------------------------------------

class TestBuildStyleDistribution:
    def test_single_style_gets_all_questions(self):
        dist = YouTubeQuizService._build_style_distribution(["Multiple choice"], 6)
        assert dist["multiple_choice"] == 6

    def test_two_styles_distributed_evenly(self):
        dist = YouTubeQuizService._build_style_distribution(["Multiple choice", "Quick check"], 6)
        assert dist["multiple_choice"] == 3
        assert dist["quick_check"] == 3

    def test_uneven_distribution_fills_round_robin(self):
        dist = YouTubeQuizService._build_style_distribution(["Multiple choice", "Quick check"], 5)
        assert sum(dist.values()) == 5

    def test_empty_styles_returns_empty(self):
        dist = YouTubeQuizService._build_style_distribution([], 5)
        assert dist == {}

    def test_three_styles_total_matches_count(self):
        styles = ["Multiple choice", "Higher-order thinking", "Discussion prompt"]
        dist = YouTubeQuizService._build_style_distribution(styles, 9)
        assert sum(dist.values()) == 9


# ---------------------------------------------------------------------------
# _coerce_legacy_payload
# ---------------------------------------------------------------------------

class TestCoerceLegacyPayload:
    def test_sections_payload_unchanged(self):
        payload = {"title": "T", "summary": "S", "sections": []}
        result = YouTubeQuizService._coerce_legacy_payload(
            payload, title="T", summary="S", question_count=6
        )
        assert result is payload

    def test_legacy_questions_converted_to_sections(self):
        legacy = {
            "questions": [{"id": f"q{i}", "style": "multiple_choice"} for i in range(6)]
        }
        result = YouTubeQuizService._coerce_legacy_payload(
            legacy, title="Quiz", summary="Summary", question_count=6
        )
        assert "sections" in result
        assert len(result["sections"]) == 3

    def test_excess_questions_trimmed_to_count(self):
        legacy = {
            "questions": [{"id": f"q{i}", "style": "multiple_choice"} for i in range(10)]
        }
        result = YouTubeQuizService._coerce_legacy_payload(
            legacy, title="Quiz", summary="Summary", question_count=6
        )
        total = sum(len(s["questions"]) for s in result["sections"])
        assert total == 6

    def test_empty_legacy_questions_unchanged(self):
        payload = {"questions": []}
        result = YouTubeQuizService._coerce_legacy_payload(
            payload, title="T", summary="S", question_count=6
        )
        assert result is payload


# ---------------------------------------------------------------------------
# _build_fallback_quiz
# ---------------------------------------------------------------------------

class TestBuildFallbackQuiz:
    def _payload(self, question_count=6):
        return YouTubeQuizGenerateRequest(
            video_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            grade_band="Grades 6-8",
            subject_lens="Science & STEM",
            learning_focus="Concept comprehension",
            quiz_language="English",
            question_count=question_count,
        )

    def _context(self):
        return TranscriptContext(
            video_id="dQw4w9WgXcQ",
            title="Test Video",
            transcript_text="Sample transcript.",
            used_transcript=True,
        )

    def test_fallback_has_three_sections(self):
        payload = self._payload(6)
        dist = {"multiple_choice": 6}
        result = YouTubeQuizService._build_fallback_quiz(payload, self._context(), dist)
        assert len(result["sections"]) == 3

    def test_fallback_total_questions_matches_count(self):
        payload = self._payload(9)
        dist = {"multiple_choice": 5, "higher_order": 4}
        result = YouTubeQuizService._build_fallback_quiz(payload, self._context(), dist)
        total = sum(len(s["questions"]) for s in result["sections"])
        assert total == 9

    def test_fallback_has_required_section_headings(self):
        # question_count must be >= 4 per schema validation
        payload = self._payload(6)
        result = YouTubeQuizService._build_fallback_quiz(
            payload, self._context(), {"multiple_choice": 6}
        )
        headings = [s["heading"] for s in result["sections"]]
        assert headings == YouTubeQuizService._required_section_headings

    def test_fallback_title_contains_video_title(self):
        payload = self._payload(6)
        result = YouTubeQuizService._build_fallback_quiz(
            payload, self._context(), {"multiple_choice": 6}
        )
        assert "Test Video" in result["title"]


# ---------------------------------------------------------------------------
# _validate_business_rules
# ---------------------------------------------------------------------------

class TestValidateBusinessRules:
    def _make_response(self, distribution, headings=None):
        from app.domains.youtube_quiz.schemas import (
            YouTubeQuizGenerateResponse,
            YouTubeQuizSection,
            YouTubeQuizQuestion,
        )

        headings = headings or YouTubeQuizService._required_section_headings
        style_keys = list(distribution.keys())
        all_questions = []
        for style_key, count in distribution.items():
            for _ in range(count):
                all_questions.append(
                    MagicMock(style=style_key)
                )

        n = len(all_questions)
        per_section = n // 3
        sections = []
        cursor = 0
        for h in headings:
            chunk = all_questions[cursor : cursor + per_section]
            cursor += per_section
            sec = MagicMock()
            sec.heading = h
            sec.questions = chunk
            sections.append(sec)
        # Spill remainder into last section
        while cursor < n:
            sections[-1].questions.append(all_questions[cursor])
            cursor += 1

        resp = MagicMock()
        resp.sections = sections
        return resp

    def test_valid_response_does_not_raise(self):
        dist = {"multiple_choice": 3, "quick_check": 3}
        resp = self._make_response(dist)
        YouTubeQuizService._validate_business_rules(resp, dist, 6)  # no exception

    def test_wrong_section_headings_raises(self):
        dist = {"multiple_choice": 3}
        resp = self._make_response(dist, headings=["Bad", "Headings", "Here"])
        with pytest.raises(ValueError, match="Sections must be exactly"):
            YouTubeQuizService._validate_business_rules(resp, dist, 3)

    def test_wrong_question_count_raises(self):
        dist = {"multiple_choice": 6}
        resp = self._make_response({"multiple_choice": 4})  # only 4
        with pytest.raises(ValueError, match="Expected exactly"):
            YouTubeQuizService._validate_business_rules(resp, dist, 6)

    def test_style_distribution_mismatch_raises(self):
        dist = {"multiple_choice": 3, "quick_check": 3}
        # Response has wrong distribution
        resp = self._make_response({"multiple_choice": 6})
        with pytest.raises(ValueError):
            YouTubeQuizService._validate_business_rules(resp, dist, 6)


# ---------------------------------------------------------------------------
# _normalize_payload
# ---------------------------------------------------------------------------

class TestNormalizePayload:
    def test_adds_id_when_missing(self):
        payload = {
            "sections": [
                {
                    "questions": [
                        {"style": "multiple_choice", "prompt": "Q1"}
                    ]
                }
            ]
        }
        result = YouTubeQuizService._normalize_payload(payload)
        assert result["sections"][0]["questions"][0]["id"] != ""

    def test_strips_whitespace_from_prompt(self):
        payload = {
            "sections": [
                {"questions": [{"id": "q1", "style": "mc", "prompt": "  Hello  "}]}
            ]
        }
        result = YouTubeQuizService._normalize_payload(payload)
        assert result["sections"][0]["questions"][0]["prompt"] == "Hello"

    def test_strips_empty_options(self):
        payload = {
            "sections": [
                {"questions": [{"id": "q1", "options": ["A", "", "C", "  "]}]}
            ]
        }
        result = YouTubeQuizService._normalize_payload(payload)
        assert result["sections"][0]["questions"][0]["options"] == ["A", "C"]
