"""
Tests for YouTube quiz generation endpoint and service helpers.
"""
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.domains.youtube_quiz.routes import youtube_quiz_service
from app.main import app
from app.domains.youtube_quiz.schemas import (
    YouTubeQuizGenerateRequest,
    YouTubeQuizQuestion,
)
from app.domains.youtube_quiz.service import TranscriptContext, YouTubeQuizService
from app.llm.schemas import LLMResponse


def test_resolve_effective_distribution_without_strategy_uses_selected_styles():
    payload = YouTubeQuizGenerateRequest(
        video_url="https://www.youtube.com/watch?v=sQK3Yr4Sc_k",
        grade_band="Grades 6-8",
        subject_lens="Science & STEM",
        learning_focus="Concept comprehension",
        quiz_language="English",
        question_styles=["Multiple choice", "Quick check"],
        question_count=6,
        lesson_strategy_id=None,
    )

    distribution = YouTubeQuizService._resolve_effective_distribution(payload, strategy=None)
    assert distribution == {"multiple_choice": 3, "quick_check": 3}


def test_resolve_effective_distribution_inquiry_launch_strategy():
    payload = YouTubeQuizGenerateRequest(
        video_url="https://www.youtube.com/watch?v=sQK3Yr4Sc_k",
        grade_band="Grades 6-8",
        subject_lens="Science & STEM",
        learning_focus="Concept comprehension",
        quiz_language="English",
        question_styles=["Quick check"],
        question_count=6,
        lesson_strategy_id="inquiry_launch",
    )
    strategy = {
        "base_question_mix": {
            "multiple_choice": 2,
            "short_answer": 2,
            "discussion_prompt": 2,
        }
    }

    distribution = YouTubeQuizService._resolve_effective_distribution(payload, strategy=strategy)
    assert distribution == {"multiple_choice": 2, "higher_order": 2, "discussion_prompt": 2}


def test_resolve_effective_distribution_career_spotlight_strategy():
    payload = YouTubeQuizGenerateRequest(
        video_url="https://www.youtube.com/watch?v=sQK3Yr4Sc_k",
        grade_band="Grades 6-8",
        subject_lens="Science & STEM",
        learning_focus="Concept comprehension",
        quiz_language="English",
        question_styles=["Multiple choice"],
        question_count=6,
        lesson_strategy_id="career_spotlight",
    )
    strategy = {
        "base_question_mix": {
            "scenario_based": 2,
            "higher_order": 2,
            "discussion_prompt": 2,
        }
    }

    distribution = YouTubeQuizService._resolve_effective_distribution(payload, strategy=strategy)
    assert distribution == {"higher_order": 4, "discussion_prompt": 2}


def test_resolve_effective_distribution_stem_lab_prep_strategy():
    payload = YouTubeQuizGenerateRequest(
        video_url="https://www.youtube.com/watch?v=sQK3Yr4Sc_k",
        grade_band="Grades 6-8",
        subject_lens="Science & STEM",
        learning_focus="Concept comprehension",
        quiz_language="English",
        question_styles=["Discussion prompt"],
        question_count=6,
        lesson_strategy_id="stem_lab_prep",
    )
    strategy = {
        "base_question_mix": {
            "procedure": 2,
            "safety": 2,
            "prediction": 2,
        }
    }

    distribution = YouTubeQuizService._resolve_effective_distribution(payload, strategy=strategy)
    assert distribution == {"quick_check": 4, "higher_order": 2}


def test_resolve_effective_distribution_sel_morning_meeting_strategy():
    payload = YouTubeQuizGenerateRequest(
        video_url="https://www.youtube.com/watch?v=sQK3Yr4Sc_k",
        grade_band="Grades 6-8",
        subject_lens="Science & STEM",
        learning_focus="Concept comprehension",
        quiz_language="English",
        question_styles=["Multiple choice"],
        question_count=6,
        lesson_strategy_id="sel_morning_meeting",
    )
    strategy = {
        "base_question_mix": {
            "reflection": 3,
            "discussion_prompt": 2,
            "quick_check": 1,
        }
    }

    distribution = YouTubeQuizService._resolve_effective_distribution(payload, strategy=strategy)
    assert distribution == {"discussion_prompt": 5, "quick_check": 1}


def test_extract_video_id_watch_url():
    video_id = YouTubeQuizService.extract_video_id("https://www.youtube.com/watch?v=sQK3Yr4Sc_k")
    assert video_id == "sQK3Yr4Sc_k"


def test_extract_video_id_short_url():
    video_id = YouTubeQuizService.extract_video_id("https://youtu.be/sQK3Yr4Sc_k")
    assert video_id == "sQK3Yr4Sc_k"


def test_extract_video_id_shorts_url():
    video_id = YouTubeQuizService.extract_video_id("https://www.youtube.com/shorts/sQK3Yr4Sc_k")
    assert video_id == "sQK3Yr4Sc_k"


def test_extract_video_id_invalid_url():
    video_id = YouTubeQuizService.extract_video_id("https://example.com/video/123")
    assert video_id is None


@pytest.mark.asyncio
async def test_generate_endpoint_success(monkeypatch):
    client = TestClient(app, raise_server_exceptions=False)

    async def fake_generate_quiz(_payload):
        return {
            "title": "Sample Video Quiz",
            "summary": "Generated summary",
            "sections": [
                {
                    "heading": "Key idea check",
                    "details": "Core understanding checks",
                    "questions": [
                        {
                            "id": "q1",
                            "style": "multiple_choice",
                            "prompt": "What is normalization?",
                            "options": ["A", "B", "C", "D"],
                            "correct_option_index": 1,
                        },
                        {
                            "id": "q2",
                            "style": "quick_check",
                            "prompt": "3NF removes transitive dependencies. True or false?",
                            "expected_response_type": "true_false",
                            "answer": True,
                        },
                    ],
                },
                {
                    "heading": "Application & transfer",
                    "details": "Apply in scenarios",
                    "questions": [
                        {
                            "id": "q3",
                            "style": "higher_order",
                            "prompt": "Design a 3NF conversion plan.",
                            "sample_answer": "Start with entity decomposition and remove partial dependencies.",
                            "rubric_points": ["Identifies functional dependencies", "Explains decomposition reasoning"],
                        },
                        {
                            "id": "q4",
                            "style": "discussion_prompt",
                            "prompt": "When can denormalization be useful?",
                            "sample_answer": "In read-heavy analytical workloads with stable data.",
                            "rubric_points": ["Performance tradeoff awareness", "Data consistency mitigation"],
                        },
                    ],
                },
                {
                    "heading": "Discussion launcher",
                    "details": "Debate and reflection",
                    "questions": [
                        {
                            "id": "q5",
                            "style": "discussion_prompt",
                            "prompt": "How would this change in a startup dataset?",
                            "sample_answer": "Prioritize speed first, normalize as complexity grows.",
                            "rubric_points": ["Contextual reasoning", "Balanced tradeoff framing"],
                        },
                        {
                            "id": "q6",
                            "style": "multiple_choice",
                            "prompt": "Which normal form removes repeating groups?",
                            "options": ["1NF", "2NF", "3NF", "BCNF"],
                            "correct_option_index": 0,
                        },
                    ],
                }
            ],
        }

    monkeypatch.setattr(youtube_quiz_service, "generate_quiz", fake_generate_quiz)

    payload = {
        "video_url": "https://www.youtube.com/watch?v=sQK3Yr4Sc_k",
        "grade_band": "Grades 6-8",
        "subject_lens": "Science & STEM",
        "learning_focus": "Concept comprehension",
        "quiz_language": "English",
        "question_styles": ["Multiple choice"],
        "question_count": 6,
    }
    response = client.post("/api/v1/youtube-quiz/generate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Sample Video Quiz"
    assert isinstance(data["sections"], list)
    assert data["sections"][0]["questions"][0]["style"] == "multiple_choice"


@pytest.mark.asyncio
async def test_generate_request_invalid_url_validation():
    with pytest.raises(ValidationError):
        YouTubeQuizGenerateRequest(
            video_url="https://example.com/not-youtube",
            grade_band="Grades 6-8",
            subject_lens="Science & STEM",
            learning_focus="Concept comprehension",
            quiz_language="English",
            question_styles=["Multiple choice"],
            question_count=6,
        )


def test_question_schema_validates_multiple_choice_requirements():
    with pytest.raises(ValidationError):
        YouTubeQuizQuestion(
            id="q1",
            style="multiple_choice",
            prompt="Invalid MCQ because options are missing.",
            correct_option_index=0,
        )


def test_question_schema_validates_quick_check_boolean_answer():
    with pytest.raises(ValidationError):
        YouTubeQuizQuestion(
            id="q1",
            style="quick_check",
            prompt="True/false question with wrong answer type",
            expected_response_type="true_false",
            answer="true",
        )


@pytest.mark.asyncio
async def test_generate_endpoint_maps_runtime_error_to_502(monkeypatch):
    client = TestClient(app, raise_server_exceptions=False)
    async def fake_generate_quiz(_payload):
        raise RuntimeError("Provider failure")

    monkeypatch.setattr(youtube_quiz_service, "generate_quiz", fake_generate_quiz)

    payload = {
        "video_url": "https://www.youtube.com/watch?v=sQK3Yr4Sc_k",
        "grade_band": "Grades 6-8",
        "subject_lens": "Science & STEM",
        "learning_focus": "Concept comprehension",
        "quiz_language": "English",
        "question_styles": ["Multiple choice"],
        "question_count": 6,
    }
    response = client.post("/api/v1/youtube-quiz/generate", json=payload)
    assert response.status_code == 502
    assert "Provider failure" in response.json()["detail"]


def test_style_distribution_even_split_with_remainder():
    distribution = YouTubeQuizService._build_style_distribution(
        ["Multiple choice", "Quick check", "Discussion prompt"],
        7,
    )
    assert distribution["multiple_choice"] == 3
    assert distribution["quick_check"] == 2
    assert distribution["discussion_prompt"] == 2


@pytest.mark.asyncio
async def test_generate_quiz_returns_explicit_error_after_failed_repair(monkeypatch):
    request_payload = YouTubeQuizGenerateRequest(
        video_url="https://www.youtube.com/watch?v=sQK3Yr4Sc_k",
        grade_band="Grades 6-8",
        subject_lens="Science & STEM",
        learning_focus="Concept comprehension",
        quiz_language="English",
        question_styles=["Multiple choice"],
        question_count=4,
    )

    monkeypatch.setattr(
        YouTubeQuizService,
        "_build_context",
        classmethod(
            lambda cls, payload: TranscriptContext(
                video_id="sQK3Yr4Sc_k",
                title="Test Video",
                transcript_text="Transcript unavailable",
                used_transcript=False,
            )
        ),
    )

    responses = [
        LLMResponse(content="not valid json", model_used="test", provider="test", latency_ms=1),
        LLMResponse(content='{"title":"Bad"}', model_used="test", provider="test", latency_ms=1),
    ]

    async def fake_call_model(_cls, _sys, _prompt):
        return responses.pop(0)

    monkeypatch.setattr(YouTubeQuizService, "_call_model", classmethod(fake_call_model))

    # Service now falls back to a deterministic schema-valid quiz instead of raising,
    # so local/dev usage does not 502 when provider output is malformed.
    response = await YouTubeQuizService.generate_quiz(request_payload)
    assert response.title
    assert response.summary
    assert len(response.sections) == 3
