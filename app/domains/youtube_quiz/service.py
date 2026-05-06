"""
Service layer for generating quizzes from YouTube lessons.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

import requests
from pydantic import ValidationError

from app.core.logging import get_logger
from app.domains.content_factory.constants.lesson_strategies import (
    build_strategy_intent_lines,
    get_strategy_by_id,
    map_strategy_mix_to_schema_styles,
    scale_question_mix,
)
from app.domains.youtube_quiz.schemas import QUESTION_STYLE_TO_KEY, QUESTION_STYLES
from app.llm.router import ModelRouter
from app.llm.schemas import LLMResponse
from app.domains.youtube_quiz.schemas import YouTubeQuizGenerateRequest, YouTubeQuizGenerateResponse

logger = get_logger(__name__)


class TranscriptUnavailableError(RuntimeError):
    """Raised when transcript cannot be fetched."""


@dataclass
class TranscriptContext:
    video_id: str
    title: str
    transcript_text: str
    used_transcript: bool


class YouTubeQuizService:
    """Build quiz output using transcript context and model router."""

    _model_router: Optional[ModelRouter] = None
    _required_section_headings = ["Key idea check", "Application & transfer", "Discussion launcher"]

    @classmethod
    def _get_model_router(cls) -> ModelRouter:
        if cls._model_router is None:
            cls._model_router = ModelRouter()
        return cls._model_router

    @staticmethod
    def extract_video_id(url: str) -> Optional[str]:
        """Extract YouTube video ID from common URL formats."""
        if not url:
            return None
        parsed = urlparse(url.strip())
        host = (parsed.netloc or "").lower()
        path = (parsed.path or "").strip("/")

        if host in {"youtu.be", "www.youtu.be"} and path:
            return path.split("/")[0]

        if "youtube.com" not in host:
            return None

        if path == "watch":
            video_id = parse_qs(parsed.query).get("v", [None])[0]
            return video_id

        if path.startswith("shorts/"):
            parts = path.split("/")
            if len(parts) > 1:
                return parts[1]

        if path.startswith("embed/"):
            parts = path.split("/")
            if len(parts) > 1:
                return parts[1]

        return None

    @staticmethod
    def _extract_json_payload(content: str) -> Dict[str, Any]:
        """Extract JSON object from model content."""
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
            cleaned = re.sub(r"```$", "", cleaned).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise
            return json.loads(cleaned[start : end + 1])

    @staticmethod
    def _build_style_distribution(selected_styles: List[str], question_count: int) -> Dict[str, int]:
        style_keys = [QUESTION_STYLE_TO_KEY[style] for style in selected_styles]
        if not style_keys:
            return {}

        distribution: Dict[str, int] = {style_key: 0 for style_key in style_keys}
        if len(style_keys) == 1:
            distribution[style_keys[0]] = question_count
            return distribution

        if question_count >= len(style_keys):
            for style_key in style_keys:
                distribution[style_key] = 1
            remaining = question_count - len(style_keys)
        else:
            remaining = question_count

        idx = 0
        while remaining > 0:
            style_key = style_keys[idx % len(style_keys)]
            distribution[style_key] += 1
            remaining -= 1
            idx += 1

        return distribution

    @staticmethod
    def _format_bulleted_lines(items: List[str]) -> str:
        return "\n".join(f"- {item}" for item in items)

    @classmethod
    def _resolve_effective_distribution(
        cls,
        payload: YouTubeQuizGenerateRequest,
        strategy: Optional[Dict[str, Any]],
    ) -> Dict[str, int]:
        if strategy:
            mapped_mix = map_strategy_mix_to_schema_styles(strategy["base_question_mix"])
            return scale_question_mix(mapped_mix, payload.question_count)
        selected_styles = payload.question_styles or sorted(QUESTION_STYLES)
        return cls._build_style_distribution(selected_styles, payload.question_count)

    @classmethod
    def _build_strategy_block(
        cls,
        strategy: Dict[str, Any],
        question_count: int,
        enforced_distribution: Dict[str, int],
    ) -> str:
        scaled_original_mix = scale_question_mix(strategy["base_question_mix"], question_count)
        original_composition_lines = cls._format_bulleted_lines(
            [f"{question_type}: {count}" for question_type, count in scaled_original_mix.items()]
        )
        enforced_composition_lines = cls._format_bulleted_lines(
            [f"{schema_style}: {count}" for schema_style, count in enforced_distribution.items()]
        )
        objectives_lines = cls._format_bulleted_lines(strategy["learning_objectives"])
        generation_rules_lines = cls._format_bulleted_lines(strategy["generation_rules"])
        intent_lines = "\n".join(build_strategy_intent_lines(strategy["base_question_mix"]))

        return f"""
Teaching Strategy: {strategy['title']}
Teaching Mode: {strategy['teaching_mode']}

Learning Objectives:
{objectives_lines}

Generation Rules:
{generation_rules_lines}

Original Strategy Question Mix:
{original_composition_lines}

Enforced Schema Style Distribution:
{enforced_composition_lines}

Strategy Type Mapping Instructions:
{intent_lines}

Instructions:
{strategy['instruction']}
""".strip()

    @classmethod
    def _build_capability_block(cls, payload: YouTubeQuizGenerateRequest) -> str:
        capability_lines: List[str] = []

        if payload.difficultyLevel == "easy":
            capability_lines.extend(
                [
                    "Adaptive Difficulty (easy):",
                    "- Generate accessible, direct questions.",
                    "- Prefer recall, simple comprehension, and clear short-answer style.",
                    "- Avoid multi-step reasoning unless required by selected strategy.",
                    "- Keep vocabulary age-appropriate for the selected grade band.",
                ]
            )
        elif payload.difficultyLevel == "medium":
            capability_lines.extend(
                [
                    "Adaptive Difficulty (medium):",
                    "- Generate balanced questions.",
                    "- Include some reasoning and application-based questions.",
                    "- Avoid overly trivial or overly advanced wording.",
                    "- Match Grade 6-8 style when grade band is Grades 6-8.",
                ]
            )
        elif payload.difficultyLevel == "challenging":
            capability_lines.extend(
                [
                    "Adaptive Difficulty (challenging):",
                    "- Generate more demanding questions.",
                    "- Include reasoning, application, explanation, and transfer where compatible with allowed styles.",
                    "- Do not exceed the selected grade band.",
                    "- Do not violate schema or style distribution requirements.",
                ]
            )

        if payload.accessibilityMode:
            capability_lines.extend(
                [
                    "Accessibility Assistant (enabled):",
                    "- Use simple, clear language.",
                    "- Avoid unnecessarily complex sentence structures.",
                    "- Avoid dense academic phrasing.",
                    "- Prefer short questions.",
                    "- Make questions easy to read for students.",
                    "- Preserve correct educational meaning.",
                ]
            )

        if not capability_lines:
            return ""
        return "\n".join(capability_lines)

    @classmethod
    def _normalize_payload(cls, parsed_payload: Dict[str, Any]) -> Dict[str, Any]:
        sections = parsed_payload.get("sections", [])
        question_counter = 1
        for section_idx, section in enumerate(sections):
            questions = section.get("questions", [])
            for q_idx, question in enumerate(questions):
                if not isinstance(question, dict):
                    continue

                if not question.get("id"):
                    question["id"] = f"q-{section_idx + 1}-{q_idx + 1}-{question_counter}"
                question_counter += 1

                for key in ("prompt", "sample_answer"):
                    value = question.get(key)
                    if isinstance(value, str):
                        question[key] = value.strip()

                options = question.get("options")
                if isinstance(options, list):
                    question["options"] = [str(opt).strip() for opt in options if str(opt).strip()]

                rubric_points = question.get("rubric_points")
                if isinstance(rubric_points, list):
                    question["rubric_points"] = [str(point).strip() for point in rubric_points if str(point).strip()]

        return parsed_payload

    @classmethod
    def _coerce_legacy_payload(
        cls,
        parsed_payload: Dict[str, Any],
        *,
        title: str,
        summary: str,
        question_count: int,
    ) -> Dict[str, Any]:
        """
        Some upstream/stubbed model responses return a legacy shape like:
          {"questions": [...], "marking_scheme": [...]}

        Coerce these into the required schema {title, summary, sections[]} so the
        endpoint doesn't 502 due to schema mismatch.
        """
        if "sections" in parsed_payload:
            return parsed_payload

        questions = parsed_payload.get("questions")
        if not isinstance(questions, list) or len(questions) == 0:
            return parsed_payload

        # Trim/exact question count to match requested count.
        questions = [q for q in questions if isinstance(q, dict)]
        if len(questions) > question_count:
            questions = questions[:question_count]

        # Distribute questions across the 3 required headings in order.
        headings = cls._required_section_headings
        buckets: List[List[Dict[str, Any]]] = [[], [], []]
        for idx, q in enumerate(questions):
            buckets[idx % 3].append(q)

        sections: List[Dict[str, Any]] = []
        for heading, bucket in zip(headings, buckets):
            sections.append(
                {
                    "heading": heading,
                    "details": "Auto-repaired from legacy quiz output.",
                    "questions": bucket,
                }
            )

        return {
            "title": parsed_payload.get("title") or title,
            "summary": parsed_payload.get("summary") or summary,
            "sections": sections,
        }

    @classmethod
    def _build_fallback_quiz(
        cls,
        payload: YouTubeQuizGenerateRequest,
        context: TranscriptContext,
        expected_style_distribution: Dict[str, int],
    ) -> Dict[str, Any]:
        """
        Deterministic, schema-valid fallback used when the model output cannot be repaired.
        This prevents 502s in local/dev environments when provider/stub output is malformed.
        """
        # Build a flat list of styles to generate.
        styles: List[str] = []
        for style_key, count in expected_style_distribution.items():
            styles.extend([style_key] * int(count))
        # Safety: if distribution is empty, default to multiple_choice.
        if not styles:
            styles = ["multiple_choice"] * payload.question_count
        styles = styles[: payload.question_count]

        headings = cls._required_section_headings
        section_question_counts = [payload.question_count // 3] * 3
        for i in range(payload.question_count % 3):
            section_question_counts[i] += 1

        def mcq(qid: str, prompt: str) -> Dict[str, Any]:
            return {
                "id": qid,
                "style": "multiple_choice",
                "prompt": prompt,
                "options": ["A", "B", "C", "D"],
                "correct_option_index": 0,
            }

        def higher(qid: str, prompt: str) -> Dict[str, Any]:
            return {
                "id": qid,
                "style": "higher_order",
                "prompt": prompt,
                "sample_answer": "Explain your reasoning using evidence from the lesson.",
                "rubric_points": ["Uses evidence from the lesson", "Explains reasoning clearly"],
            }

        def discussion(qid: str, prompt: str) -> Dict[str, Any]:
            return {
                "id": qid,
                "style": "discussion_prompt",
                "prompt": prompt,
                "sample_answer": "Facilitate multiple viewpoints and connect to real-world examples.",
                "rubric_points": ["Offers a supported viewpoint", "Connects to real-world examples"],
            }

        def quick(qid: str, prompt: str) -> Dict[str, Any]:
            return {
                "id": qid,
                "style": "quick_check",
                "prompt": prompt,
                "expected_response_type": "short_phrase",
                "answer": "Sample answer",
            }

        question_builders = {
            "multiple_choice": mcq,
            "higher_order": higher,
            "discussion_prompt": discussion,
            "quick_check": quick,
        }

        sections: List[Dict[str, Any]] = []
        cursor = 0
        q_num = 1
        for section_idx, (heading, count) in enumerate(zip(headings, section_question_counts)):
            bucket_styles = styles[cursor : cursor + count]
            cursor += count
            questions: List[Dict[str, Any]] = []
            for style_key in bucket_styles:
                builder = question_builders.get(style_key, mcq)
                qid = f"fallback-{section_idx+1}-{q_num}"
                q_num += 1
                base_prompt = f"({heading}) Based on the lesson '{context.title}', answer this question."
                questions.append(builder(qid, base_prompt))
            sections.append(
                {
                    "heading": heading,
                    "details": "Fallback quiz generated when model response was invalid.",
                    "questions": questions,
                }
            )

        return {
            "title": f"Quiz: {context.title}",
            "summary": f"Fallback quiz (model response could not be validated) for {payload.grade_band} · {payload.subject_lens}.",
            "sections": sections,
        }

    @classmethod
    def _validate_business_rules(
        cls,
        response: YouTubeQuizGenerateResponse,
        expected_style_distribution: Dict[str, int],
        question_count: int,
    ) -> None:
        headings = [section.heading for section in response.sections]
        if headings != cls._required_section_headings:
            raise ValueError(
                f"Sections must be exactly {cls._required_section_headings}. Received headings: {headings}"
            )

        total_questions = sum(len(section.questions) for section in response.sections)
        if total_questions != question_count:
            raise ValueError(
                f"Expected exactly {question_count} questions but received {total_questions}."
            )

        actual_distribution: Dict[str, int] = {}
        for section in response.sections:
            for question in section.questions:
                actual_distribution[question.style] = actual_distribution.get(question.style, 0) + 1

        for style_key, expected_count in expected_style_distribution.items():
            actual_count = actual_distribution.get(style_key, 0)
            if actual_count != expected_count:
                raise ValueError(
                    f"Style distribution mismatch for '{style_key}': expected {expected_count}, got {actual_count}."
                )

    @staticmethod
    def _fetch_video_title(video_url: str) -> Optional[str]:
        """Fetch title via YouTube oEmbed."""
        oembed_url = "https://www.youtube.com/oembed"
        try:
            response = requests.get(
                oembed_url,
                params={"url": video_url, "format": "json"},
                timeout=8,
            )
            if response.status_code != 200:
                return None
            payload = response.json()
            return payload.get("title")
        except Exception:
            return None

    @staticmethod
    def _fetch_transcript(video_id: str, language: str) -> str:
        """Fetch transcript text using youtube-transcript-api if available."""
        try:
            from youtube_transcript_api import YouTubeTranscriptApi

            preferred_languages = [language.lower(), "en"]
            transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=preferred_languages)
            chunks = [item.get("text", "").strip() for item in transcript if item.get("text")]
            text = " ".join(chunks).strip()
            if not text:
                raise TranscriptUnavailableError("Transcript was empty")
            return text
        except Exception as exc:
            raise TranscriptUnavailableError(str(exc)) from exc

    @staticmethod
    def _truncate_transcript(text: str, max_chars: int = 10000) -> str:
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + " ..."

    @classmethod
    def _build_context(cls, payload: YouTubeQuizGenerateRequest) -> TranscriptContext:
        video_id = cls.extract_video_id(payload.video_url)
        if not video_id:
            raise ValueError("Invalid YouTube URL. Could not extract video id.")

        title = cls._fetch_video_title(payload.video_url) or "YouTube lesson"
        try:
            transcript = cls._fetch_transcript(video_id, payload.quiz_language)
            return TranscriptContext(
                video_id=video_id,
                title=title,
                transcript_text=cls._truncate_transcript(transcript),
                used_transcript=True,
            )
        except TranscriptUnavailableError as exc:
            logger.warning(f"Transcript unavailable for {video_id}: {exc}")
            return TranscriptContext(
                video_id=video_id,
                title=title,
                transcript_text="Transcript unavailable. Rely on video context and educator inputs.",
                used_transcript=False,
            )

    @staticmethod
    def _build_prompt(
        payload: YouTubeQuizGenerateRequest,
        context: TranscriptContext,
        expected_style_distribution: Dict[str, int],
        strategy_block: str = "",
        capability_block: str = "",
        generation_mode: str = "style_selection",
    ) -> tuple[str, str]:
        selected_styles = payload.question_styles or sorted(QUESTION_STYLES)
        selected_style_keys = [QUESTION_STYLE_TO_KEY[style] for style in selected_styles]
        if generation_mode == "strategy":
            style_authority_instruction = f"""
- A lesson strategy is applied. The strategy-derived distribution is the authority.
- Ignore frontend-selected question styles for distribution.
- Only output schema-supported styles from this enforced distribution: {list(expected_style_distribution.keys())}
- Use this exact strategy-derived style distribution: {expected_style_distribution}
- Preserve the original strategy intent described in the Strategy Type Mapping Instructions.
""".strip()
        else:
            style_authority_instruction = f"""
- No lesson strategy is applied. Use frontend-selected question styles as the authority.
- Only use these selected styles: {selected_styles} -> mapped keys {selected_style_keys}
- Use this exact style distribution: {expected_style_distribution}
""".strip()

        system_message = (
            "You are an education assessment assistant. "
            "Always return valid JSON only. "
            "Do not include markdown fences, explanations, or additional keys."
        )
        schema_string = """
{
  "title": "string",
  "summary": "string",
  "sections": [
    {
      "heading": "Key idea check | Application & transfer | Discussion launcher",
      "details": "string",
      "questions": [
        {
          "id": "string",
          "style": "multiple_choice | higher_order | quick_check | discussion_prompt",
          "prompt": "string",
          "options": ["string", "string", "string", "string"],
          "correct_option_index": 0,
          "sample_answer": "string",
          "rubric_points": ["string", "string"],
          "expected_response_type": "one_word | short_phrase | true_false",
          "answer": "string or boolean"
        }
      ]
    }
  ]
}
""".strip()

        user_prompt = f"""
Generate a classroom-ready quiz blueprint with this exact schema:
{schema_string}

Rules:
{strategy_block}
{capability_block}
- Keep exactly 3 sections with headings:
  1) Key idea check
  2) Application & transfer
  3) Discussion launcher
- Total questions across all sections must be exactly {payload.question_count}.
{style_authority_instruction}
- Output language: {payload.quiz_language}
- Grade band: {payload.grade_band}
- Subject lens: {payload.subject_lens}
- Learning focus: {payload.learning_focus}
- If transcript is unavailable, still generate useful pedagogically aligned questions.
- Question style requirements:
  - multiple_choice: include exactly 4 plausible options and one correct_option_index.
  - higher_order: include sample_answer and at least 2 rubric_points.
  - quick_check: include expected_response_type and exact answer.
  - discussion_prompt: include sample_answer and at least 2 rubric_points with facilitation angles.
- Omit style-specific optional fields for styles where they do not apply.
- Return JSON only. No markdown.

Video title: {context.title}
Video id: {context.video_id}
Transcript used: {context.used_transcript}
Transcript/context:
{context.transcript_text}
""".strip()
        return system_message, user_prompt

    @classmethod
    async def _call_model(cls, system_message: str, user_prompt: str) -> LLMResponse:
        router = cls._get_model_router()
        return await router.generate(
            system_message=system_message,
            prompt=user_prompt,
            model_config=None,
        )

    @classmethod
    def _validate_and_convert(
        cls,
        parsed_payload: Dict[str, Any],
        expected_style_distribution: Dict[str, int],
        question_count: int,
    ) -> YouTubeQuizGenerateResponse:
        normalized = cls._normalize_payload(parsed_payload)
        response = YouTubeQuizGenerateResponse.model_validate(normalized)
        cls._validate_business_rules(response, expected_style_distribution, question_count)
        return response

    @classmethod
    async def generate_quiz(cls, payload: YouTubeQuizGenerateRequest) -> YouTubeQuizGenerateResponse:
        context = cls._build_context(payload)
        strategy = get_strategy_by_id(payload.lesson_strategy_id) if payload.lesson_strategy_id else None
        if payload.lesson_strategy_id and not strategy:
            logger.warning(f"Unknown lesson strategy id received: {payload.lesson_strategy_id}")
        expected_style_distribution = cls._resolve_effective_distribution(payload, strategy)
        strategy_block = ""
        capability_block = cls._build_capability_block(payload)
        generation_mode = "style_selection"
        if strategy:
            strategy_block = cls._build_strategy_block(
                strategy,
                payload.question_count,
                expected_style_distribution,
            )
            logger.info(f"Lesson strategy applied: {strategy['id']}")
            generation_mode = "strategy"
        if payload.difficultyLevel:
            logger.info(f"Capability applied: difficultyLevel={payload.difficultyLevel}")
        if payload.accessibilityMode:
            logger.info("Capability applied: accessibilityMode=true")

        system_message, user_prompt = cls._build_prompt(
            payload,
            context,
            expected_style_distribution,
            strategy_block=strategy_block,
            capability_block=capability_block,
            generation_mode=generation_mode,
        )

        llm_response: Optional[LLMResponse] = None
        try:
            llm_response = await cls._call_model(system_message, user_prompt)
            parsed = cls._extract_json_payload(llm_response.content)
            parsed = cls._coerce_legacy_payload(
                parsed,
                title=f"Quiz: {context.title}",
                summary="Auto-coerced from legacy model output.",
                question_count=payload.question_count,
            )
            return cls._validate_and_convert(parsed, expected_style_distribution, payload.question_count)
        except Exception as first_error:
            logger.warning(f"Initial quiz generation parse failed: {first_error}")
            previous_response = llm_response.content if llm_response else ""
            validation_errors = (
                first_error.errors() if isinstance(first_error, ValidationError) else [str(first_error)]
            )
            strategy_repair_note = (
                "- A lesson strategy is applied. Keep the strategy-derived style distribution and preserve original mapped strategy intent."
                if strategy
                else "- No strategy is applied. Keep the selected-style distribution."
            )
            capability_repair_notes: List[str] = []
            if payload.difficultyLevel:
                capability_repair_notes.append(
                    f"- Keep adaptive difficulty intent aligned to '{payload.difficultyLevel}'."
                )
            if payload.accessibilityMode:
                capability_repair_notes.append(
                    "- Keep accessibility mode intent with simple, clear wording."
                )
            capability_repair_note = (
                "\n".join(capability_repair_notes)
                if capability_repair_notes
                else "- No capability modifiers are active."
            )
            repair_prompt = f"""
Repair the previous response so it is valid JSON for the required schema and business rules.
Return JSON only.

Validation errors:
{validation_errors}

Business rules:
- Required section headings: {cls._required_section_headings}
- Total question count must be exactly {payload.question_count}
- Required style distribution: {expected_style_distribution}
- Style field requirements:
  - multiple_choice: exactly 4 options and valid correct_option_index.
  - higher_order: sample_answer and rubric_points.
  - quick_check: expected_response_type and answer.
  - discussion_prompt: sample_answer and rubric_points.
{strategy_repair_note}
{capability_repair_note}

Original invalid response:
{previous_response}
""".strip()
            try:
                llm_response = await cls._call_model(system_message, f"{user_prompt}\n\n{repair_prompt}")
                parsed = cls._extract_json_payload(llm_response.content)
                parsed = cls._coerce_legacy_payload(
                    parsed,
                    title=f"Quiz: {context.title}",
                    summary="Auto-coerced from legacy model output.",
                    question_count=payload.question_count,
                )
                return cls._validate_and_convert(parsed, expected_style_distribution, payload.question_count)
            except Exception as repair_error:
                logger.error(f"Quiz generation failed after repair attempt: {repair_error}", exc_info=True)
                # Final fallback: return a schema-valid quiz instead of 502.
                fallback = cls._build_fallback_quiz(payload, context, expected_style_distribution)
                try:
                    return cls._validate_and_convert(
                        fallback,
                        expected_style_distribution,
                        payload.question_count,
                    )
                except Exception as fallback_error:
                    raise RuntimeError(
                        "Failed to generate a valid typed quiz response from LLM after repair attempt, "
                        "and fallback quiz validation also failed. "
                        f"Root error: {str(repair_error)}; Fallback error: {str(fallback_error)}"
                    ) from fallback_error
