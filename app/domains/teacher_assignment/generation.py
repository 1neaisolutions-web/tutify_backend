from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.core.logging import get_logger
from app.llm.config import llm_settings
from app.llm.router import ModelRouter

logger = get_logger(__name__)


@dataclass(frozen=True)
class GeneratedBriefTopic:
    topic_id: str
    title: str
    lines: List[str]


@dataclass(frozen=True)
class GeneratedBriefLine:
    topic_id: str
    title: str
    line_text: str
    line_id: str


def _strip_fences(s: str) -> str:
    s = (s or "").strip()
    if "```json" in s:
        return s.split("```json", 1)[1].split("```", 1)[0].strip()
    if "```" in s:
        return s.split("```", 1)[1].split("```", 1)[0].strip()
    return s


def _safe_json_load(s: str) -> Any:
    raw = _strip_fences(s)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        idx = raw.rfind("}")
        if idx != -1:
            return json.loads(raw[: idx + 1])
        raise


def _difficulty_tone(difficulty: Optional[str]) -> str:
    if difficulty == "foundation":
        return "Scaffold with short prompts, guided checkpoints, and recall-level checks."
    if difficulty == "challenge":
        return (
            "Push synthesis, cross-strand links, and evaluative reasoning suited to extension."
        )
    return "Balance grade-level rigor with clear checkpoints and structured tasks."


def _format_avoid_block(items: List[str], *, label: str, limit: int = 12) -> str:
    cleaned = [x.strip() for x in (items or []) if x and x.strip()]
    if not cleaned:
        return ""
    cleaned = cleaned[:limit]
    lines = "\n".join(f"- {x}" for x in cleaned)
    return f"\nAVOID REPEATING ({label}):\n{lines}\n"


class AssignmentGenerationService:
    def __init__(self) -> None:
        self.llm_router = ModelRouter(config=llm_settings)

    @staticmethod
    def build_input_hash(payload: Dict[str, Any]) -> str:
        as_json = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(as_json.encode("utf-8")).hexdigest()

    async def generate_brief(
        self,
        *,
        subject: str,
        grade: str,
        assignment_type: str,
        rigor_profile: str,
        topic_label: str,
        scope_topics: List[str],
        difficulty: Optional[str],
        topic_count: int,
        teacher_notes: Optional[str],
        context_text: str,
    ) -> Tuple[List[GeneratedBriefTopic], List[str], Dict[str, Any]]:
        warnings: List[str] = []
        topic_count = max(1, min(10, topic_count))

        context = (context_text or "").strip()
        if len(context) > 12_000:
            context = context[:10_000] + "\n[...truncated...]\n" + context[-1500:]
            warnings.append("Context was long and was truncated.")

        diff_tone = _difficulty_tone(difficulty)
        teacher_line = (
            f"\nTeacher focus: {teacher_notes.strip()}"
            if teacher_notes and teacher_notes.strip()
            else ""
        )

        topic_hints = ""
        if scope_topics:
            hints = ", ".join(f'"{t}"' for t in scope_topics[:10])
            topic_hints = f"\nPreferred topic strands (distribute across sections): {hints}."

        schema_example = {
            "topics": [
                {
                    "title": "Topic title here",
                    "lines": [
                        "Objective — [title]: produce [assignment_type] work at [rigor_profile] expectations in [subject] ([grade]).",
                        "Tasks — [difficulty tone]. Include N concrete deliverables tied to the topic with a short self-check.",
                        "Evidence — Prioritise catalog-aligned evidence. Cite materials explicitly when excerpts are available.",
                    ],
                }
            ]
        }

        system_message = (
            "You are an expert curriculum designer. "
            "Return ONLY valid JSON matching the schema. "
            "Keep language international English, grade-appropriate, and actionable."
        )

        prompt = f"""
TASK: Create a multi-topic assignment brief.

ASSIGNMENT TYPE: {assignment_type}
SUBJECT: {subject}
GRADE: {grade}
RIGOR PROFILE: {rigor_profile}
DIFFICULTY PROFILE: {diff_tone}
TOPIC SCOPE: {topic_label}
{teacher_line}
{topic_hints}

REQUIREMENTS:
- Return a JSON object with key "topics" (array of exactly {topic_count} objects).
- Each topic object has "title" (string) and "lines" (array of exactly 3 strings).
- Line 1 (Objective): Start with "Objective — [title]: produce [assignment_type]..."
- Line 2 (Tasks): Start with "Tasks — " followed by difficulty-appropriate deliverables.
- Line 3 (Evidence): Start with "Evidence — " citing catalog grounding if context provided.
- Titles must be distinct and directly drawn from the scope topics or topic label.
- All lines must be actionable, grade-appropriate, and specific to the subject.
- Use the CONTEXT when present; generate from general knowledge otherwise.

SCHEMA EXAMPLE (do not copy values):
{json.dumps(schema_example, ensure_ascii=False)}

CONTEXT:
{context}

Return only JSON.
""".strip()

        try:
            response = await self.llm_router.generate(
                system_message=system_message,
                prompt=prompt,
                model_config={
                    "provider": getattr(llm_settings, "DEFAULT_MODEL_PROVIDER", "openai"),
                    "model": getattr(llm_settings, "DEFAULT_MODEL", "gpt-4o-mini"),
                    "temperature": 0.3,
                    "max_tokens": 3000,
                },
            )
        except Exception:
            logger.warning("assignment_llm_generate_failed", exc_info=True)
            raise

        content = getattr(response, "content", "") or ""
        parsed = _safe_json_load(content)
        raw_topics = parsed.get("topics") if isinstance(parsed, dict) else None
        if not isinstance(raw_topics, list):
            raise ValueError("LLM returned invalid assignment JSON: missing topics list.")

        out: List[GeneratedBriefTopic] = []
        for row in raw_topics[:topic_count]:
            if not isinstance(row, dict):
                continue
            title = str(row.get("title") or "").strip()
            if not title:
                continue
            raw_lines = row.get("lines") or []
            lines = [str(ln).strip() for ln in raw_lines if str(ln).strip()]
            if not lines:
                continue
            while len(lines) < 3:
                lines.append(f"Evidence — Use grade-appropriate sources for {title}.")
            lines = lines[:3]
            out.append(
                GeneratedBriefTopic(
                    topic_id=str(uuid.uuid4()),
                    title=title,
                    lines=lines,
                )
            )

        if len(out) < topic_count:
            warnings.append(
                f"Generator returned {len(out)} topics; expected {topic_count}."
            )

        meta = {
            "provider": getattr(response, "provider", None),
            "model_used": getattr(response, "model_used", None),
            "finish_reason": getattr(response, "finish_reason", None),
            "content_length": len(content),
        }
        return out, warnings, meta

    async def regenerate_topic(
        self,
        *,
        subject: str,
        grade: str,
        assignment_type: str,
        rigor_profile: str,
        topic_title: str,
        difficulty: Optional[str],
        teacher_notes: Optional[str],
        context_text: str,
        existing_lines: Optional[List[str]] = None,
        other_titles: Optional[List[str]] = None,
    ) -> Tuple[GeneratedBriefTopic, List[str], Dict[str, Any]]:
        warnings: List[str] = []
        context = (context_text or "").strip()
        if len(context) > 12_000:
            context = context[:10_000] + "\n[...truncated...]\n" + context[-1500:]
            warnings.append("Context was long and was truncated.")

        diff_tone = _difficulty_tone(difficulty)
        teacher_line = (
            f"\nTeacher focus: {teacher_notes.strip()}"
            if teacher_notes and teacher_notes.strip()
            else ""
        )
        avoid_block = _format_avoid_block(existing_lines or [], label="previous lines")
        avoid_titles = _format_avoid_block(other_titles or [], label="other topic titles")

        schema_example = {
            "title": "Topic title here",
            "lines": [
                "Objective — [title]: produce [assignment_type]...",
                "Tasks — ...",
                "Evidence — ...",
            ],
        }

        system_message = (
            "You are an expert curriculum designer. "
            "Return ONLY valid JSON matching the schema. "
            "Be specific, actionable, and avoid repetition."
        )

        prompt = f"""
TASK: Regenerate ONE topic section for an assignment brief.

ASSIGNMENT TYPE: {assignment_type}
SUBJECT: {subject}
GRADE: {grade}
RIGOR PROFILE: {rigor_profile}
DIFFICULTY PROFILE: {diff_tone}
TOPIC TITLE (keep the same topic, but vary the phrasing/tasks): {topic_title}
{teacher_line}

REQUIREMENTS:
- Return a JSON object with keys: "title" (string) and "lines" (array of exactly 3 strings).
- Keep the topic aligned to "{topic_title}" but make it feel meaningfully refreshed.
- Do NOT repeat the AVOID REPEATING items verbatim; produce new wording and different concrete deliverables.
- Line 1 starts with "Objective —".
- Line 2 starts with "Tasks —".
- Line 3 starts with "Evidence —".
- Use the CONTEXT when present.
{avoid_titles}{avoid_block}

SCHEMA EXAMPLE (do not copy values):
{json.dumps(schema_example, ensure_ascii=False)}

CONTEXT:
{context}

Return only JSON.
""".strip()

        response = await self.llm_router.generate(
            system_message=system_message,
            prompt=prompt,
            model_config={
                "provider": getattr(llm_settings, "DEFAULT_MODEL_PROVIDER", "openai"),
                "model": getattr(llm_settings, "DEFAULT_MODEL", "gpt-4o-mini"),
                # Increase variance on regen so it doesn't mirror the prior text.
                "temperature": 0.7,
                "max_tokens": 1400,
            },
        )

        content = getattr(response, "content", "") or ""
        parsed = _safe_json_load(content)
        if not isinstance(parsed, dict):
            raise ValueError("LLM returned invalid topic JSON.")

        title = str(parsed.get("title") or "").strip() or topic_title
        raw_lines = parsed.get("lines") or []
        lines = [str(ln).strip() for ln in raw_lines if str(ln).strip()]
        while len(lines) < 3:
            lines.append(f"Evidence — Use grade-appropriate sources for {title}.")
        lines = lines[:3]

        meta = {
            "provider": getattr(response, "provider", None),
            "model_used": getattr(response, "model_used", None),
            "finish_reason": getattr(response, "finish_reason", None),
            "content_length": len(content),
        }
        return GeneratedBriefTopic(topic_id=str(uuid.uuid4()), title=title, lines=lines), warnings, meta

    async def regenerate_line(
        self,
        *,
        subject: str,
        grade: str,
        assignment_type: str,
        rigor_profile: str,
        topic_title: str,
        line_index: int,
        difficulty: Optional[str],
        teacher_notes: Optional[str],
        context_text: str,
        existing_lines: Optional[List[str]] = None,
        objective_text: Optional[str] = None,
        tasks_text: Optional[str] = None,
        evidence_text: Optional[str] = None,
    ) -> Tuple[GeneratedBriefLine, List[str], Dict[str, Any]]:
        warnings: List[str] = []
        context = (context_text or "").strip()
        if len(context) > 12_000:
            context = context[:10_000] + "\n[...truncated...]\n" + context[-1500:]
            warnings.append("Context was long and was truncated.")

        diff_tone = _difficulty_tone(difficulty)
        teacher_line = (
            f"\nTeacher focus: {teacher_notes.strip()}"
            if teacher_notes and teacher_notes.strip()
            else ""
        )
        avoid_block = _format_avoid_block(existing_lines or [], label="existing lines in this topic")
        schema_example = {"text": "Tasks — Provide two new deliverables that differ from the original."}

        system_message = (
            "You are an expert curriculum designer. "
            "Return ONLY valid JSON matching the schema. "
            "Be specific and avoid repetition."
        )

        which = "Objective" if line_index == 0 else "Tasks" if line_index == 1 else "Evidence"
        current_lines_block = ""
        if objective_text or tasks_text or evidence_text:
            current_lines_block = (
                "\nCURRENT TOPIC LINES (do not contradict; keep coherent):\n"
                f"- Objective: {(objective_text or '').strip()}\n"
                f"- Tasks: {(tasks_text or '').strip()}\n"
                f"- Evidence: {(evidence_text or '').strip()}\n"
            )
        prompt = f"""
TASK: Regenerate ONE line in an assignment brief topic, with meaningful variation.

ASSIGNMENT TYPE: {assignment_type}
SUBJECT: {subject}
GRADE: {grade}
RIGOR PROFILE: {rigor_profile}
DIFFICULTY PROFILE: {diff_tone}
TOPIC: {topic_title}
LINE TO REGENERATE: index={line_index} ({which})
{teacher_line}

REQUIREMENTS:
- Return a JSON object with key "text" (string) only.
- Start the text with "{which} —".
- Keep alignment with the topic, but change the concrete deliverables / wording.
- Maintain coherence with the other two lines:
  - If regenerating Tasks: ensure tasks directly operationalize the Objective.
  - If regenerating Evidence: ensure evidence supports completion of the Tasks and Objective.
  - If regenerating Objective: do not change the topic; keep it compatible with the existing Tasks/Evidence intent.
- Do NOT repeat the AVOID REPEATING items verbatim.
{current_lines_block}
{avoid_block}

SCHEMA EXAMPLE (do not copy values):
{json.dumps(schema_example, ensure_ascii=False)}

CONTEXT:
{context}

Return only JSON.
""".strip()

        response = await self.llm_router.generate(
            system_message=system_message,
            prompt=prompt,
            model_config={
                "provider": getattr(llm_settings, "DEFAULT_MODEL_PROVIDER", "openai"),
                "model": getattr(llm_settings, "DEFAULT_MODEL", "gpt-4o-mini"),
                "temperature": 0.8,
                "max_tokens": 700,
            },
        )

        content = getattr(response, "content", "") or ""
        parsed = _safe_json_load(content)
        if not isinstance(parsed, dict):
            raise ValueError("LLM returned invalid line JSON.")
        text = str(parsed.get("text") or "").strip()
        if not text:
            text = f"{which} — Provide a revised line for {topic_title}."

        meta = {
            "provider": getattr(response, "provider", None),
            "model_used": getattr(response, "model_used", None),
            "finish_reason": getattr(response, "finish_reason", None),
            "content_length": len(content),
        }
        return (
            GeneratedBriefLine(
                topic_id=str(uuid.uuid4()),
                title=topic_title,
                line_text=text,
                line_id=str(uuid.uuid4()),
            ),
            warnings,
            meta,
        )
