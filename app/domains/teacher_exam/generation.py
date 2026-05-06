from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.core.logging import get_logger
from app.llm.config import llm_settings
from app.llm.router import ModelRouter

logger = get_logger(__name__)


@dataclass(frozen=True)
class GeneratedExamSection:
    title: str
    marks: float
    description: str


@dataclass(frozen=True)
class GeneratedMcq:
    stem: str
    options: List[str]
    marks_per: float


@dataclass(frozen=True)
class GeneratedShort:
    stem: str
    marks_per: float


@dataclass(frozen=True)
class GeneratedLong:
    stem: str
    subparts: List[str]
    marks_per: float


@dataclass(frozen=True)
class GeneratedExam:
    sections: List[GeneratedExamSection]
    mcqs: List[GeneratedMcq]
    shorts: List[GeneratedShort]
    longs: List[GeneratedLong]
    warnings: List[str]


def _strip_fences(s: str) -> str:
    s = (s or "").strip()
    if "```json" in s:
        return s.split("```json", 1)[1].split("```", 1)[0].strip()
    if "```" in s:
        return s.split("```", 1)[1].split("```", 1)[0].strip()
    return s


def _safe_json_load(s: str) -> Dict[str, Any]:
    raw = _strip_fences(s)
    try:
        out = json.loads(raw)
        return out if isinstance(out, dict) else {}
    except json.JSONDecodeError:
        idx = raw.rfind("}")
        if idx != -1:
            return json.loads(raw[: idx + 1])
        raise


def _difficulty_label(difficulty: Optional[str]) -> str:
    if difficulty == "foundation":
        return "Foundation"
    if difficulty == "challenge":
        return "Challenge"
    return "Standard"


def _paper_short_pool(paper: Dict[str, Any]) -> int:
    if (paper.get("shortRule") or "pickNM") == "pickNM":
        return int(paper.get("shortM") or 0)
    return int(paper.get("shortCount") or 0)


def _paper_long_pool(paper: Dict[str, Any]) -> int:
    if (paper.get("longRule") or "pickNM") == "pickNM":
        return int(paper.get("longM") or 0)
    return int(paper.get("longCount") or 0)


def _mcq_option_labels(n_opts: int) -> List[str]:
    letters = ["A", "B", "C", "D", "E"]
    return [f"{letters[i]}. Option {i+1}" for i in range(min(n_opts, 5))]


class ExamGenerationService:
    def __init__(self) -> None:
        self.llm_router = ModelRouter(config=llm_settings)

    @staticmethod
    def build_input_hash(payload: Dict[str, Any]) -> str:
        as_json = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(as_json.encode("utf-8")).hexdigest()

    def _stub_full_exam(
        self,
        *,
        paper: Dict[str, Any],
        section_target_count: int,
        topic_label: str,
        subject: str,
    ) -> GeneratedExam:
        warnings = ["Stub generation (USE_REAL_LLM=false)."]
        obj_n = max(1, int(paper.get("objCount") or 1))
        obj_opts = int(paper.get("objOptions") or 4)
        obj_marks = float(paper.get("objMarksPer") or 1.0)
        short_n = max(1, _paper_short_pool(paper))
        short_marks = float(paper.get("shortMarksPer") or 5.0)
        long_n = max(1, _paper_long_pool(paper))
        long_marks = float(paper.get("longMarksPer") or 10.0)
        long_sub = max(1, min(6, int(paper.get("longSubparts") or 3)))

        sections: List[GeneratedExamSection] = []
        for i in range(max(1, section_target_count)):
            sections.append(
                GeneratedExamSection(
                    title=f"Section {chr(65 + i)} — {topic_label or subject}",
                    marks=10.0,
                    description=f"Placeholder section description ({i+1}).",
                )
            )

        mcqs = [
            GeneratedMcq(
                stem=f"Sample MCQ [{i+1}] for {subject}: {topic_label}?",
                options=_mcq_option_labels(obj_opts),
                marks_per=obj_marks,
            )
            for i in range(obj_n)
        ]
        shorts = [
            GeneratedShort(
                stem=f"Explain aspect [{i+1}] of {topic_label} in the context of {subject}.",
                marks_per=short_marks,
            )
            for i in range(short_n)
        ]
        sub_template = ["(a) Define.", "(b) Describe.", "(c) Evaluate."]
        longs = [
            GeneratedLong(
                stem=f"Analyse [{i+1}] {topic_label} in {subject}.",
                subparts=sub_template[:long_sub],
                marks_per=long_marks,
            )
            for i in range(long_n)
        ]
        return GeneratedExam(sections=sections, mcqs=mcqs, shorts=shorts, longs=longs, warnings=warnings)

    async def generate_full_exam(
        self,
        *,
        subject: str,
        grade: str,
        topic_label: str,
        international_standard: str,
        paper_config: Dict[str, Any],
        section_target_count: int,
        difficulty: Optional[str],
        teacher_notes: Optional[str],
        retrieved_chunks: str,
        avoid_question_stems: Optional[List[str]] = None,
    ) -> GeneratedExam:
        if not getattr(llm_settings, "USE_REAL_LLM", False):
            return self._stub_full_exam(
                paper=paper_config,
                section_target_count=section_target_count,
                topic_label=topic_label,
                subject=subject,
            )

        paper = dict(paper_config or {})
        obj_count = int(paper.get("objCount") or 0)
        obj_options = int(paper.get("objOptions") or 4)
        short_pool = _paper_short_pool(paper)
        long_pool = _paper_long_pool(paper)
        long_subparts = int(paper.get("longSubparts") or 3)
        obj_marks = float(paper.get("objMarksPer") or 1.0)
        short_marks = float(paper.get("shortMarksPer") or 5.0)
        long_marks = float(paper.get("longMarksPer") or 10.0)

        short_rule = paper.get("shortRule") or "pickNM"
        long_rule = paper.get("longRule") or "pickNM"
        part_b1_marks = (int(paper.get("shortN") or 0) if short_rule == "pickNM" else int(paper.get("shortCount") or 0)) * short_marks
        part_b2_marks = (int(paper.get("longN") or 0) if long_rule == "pickNM" else int(paper.get("longCount") or 0)) * long_marks
        part_a_marks = obj_count * obj_marks
        grand_total = part_a_marks + part_b1_marks + part_b2_marks

        diff_label = _difficulty_label(difficulty)
        teacher_notes_section = ""
        if teacher_notes and teacher_notes.strip():
            teacher_notes_section = f"\nTeacher notes / focus: {teacher_notes.strip()}\n"

        stems = [s.strip() for s in (avoid_question_stems or []) if isinstance(s, str) and s.strip()]
        regeneration_hint = ""
        if stems:
            preview = [t[:180] + ("…" if len(t) > 180 else "") for t in stems[:24]]
            regeneration_hint = (
                "\nREGENERATION — fresh paper required:\n"
                "- Do NOT copy or lightly paraphrase any prior stems below.\n"
                "- Invent new scenarios, quantities, definitions, and command words.\n"
                + "\n".join([f"- Previous stem to avoid echoing: \"{p}\"" for p in preview])
                + "\n"
            )

        prompt = f"""
You are an exam paper generator for {subject}, {grade}, {international_standard} standard.
Difficulty: {diff_label}
Topic scope: {topic_label}
Source material: {retrieved_chunks}
{teacher_notes_section}
{regeneration_hint}

Generate a complete exam in this JSON format:
{{
  "sections": [
    {{"title": "Part A — Objective", "marks": 20, "description": "20 multiple-choice questions, 1 mark each."}}
  ],
  "mcqs": [
    {{"stem": "Question text?", "options": ["A. ...", "B. ...", "C. ...", "D. ..."]}}
  ],
  "shorts": [
    {{"stem": "Explain X with reference to the source material."}}
  ],
  "longs": [
    {{
      "stem": "Analyse Y in the context of {topic_label}.",
      "subparts": ["(a) Define Y.", "(b) Describe two effects of Y.", "(c) Evaluate the implications."]
    }}
  ]
}}

Requirements:
- Generate {section_target_count} sections that match the paper structure.
- MCQ count: {obj_count}, each with exactly {obj_options} options labeled "A." through "D/E."
- Short question count: {short_pool}
- Long question count: {long_pool}, each with exactly {long_subparts} sub-parts.
- All content must be grounded in the provided source material when present; if empty, stay on-topic for the scope.
- Marks allocation: Part A {part_a_marks}, Part B1 {part_b1_marks}, Part B2 {part_b2_marks}, Grand total {grand_total}.
- For {international_standard}: use appropriate command verbs (Cambridge: "state/explain/evaluate"; IB: "outline/analyse/discuss").
- Return ONLY the JSON object. No prose before or after.
""".strip()

        system_message = (
            "You are an expert assessment author. Return ONLY valid JSON matching the schema. "
            "Use international English appropriate to the grade."
        )
        warnings: List[str] = []
        llm_temp = 0.34 if stems else 0.25
        try:
            response = await self.llm_router.generate(
                system_message=system_message,
                prompt=prompt,
                model_config={
                    "provider": getattr(llm_settings, "DEFAULT_MODEL_PROVIDER", "openai"),
                    "model": getattr(llm_settings, "DEFAULT_MODEL", "gpt-4o-mini"),
                    "temperature": llm_temp,
                    "max_tokens": 12000,
                },
            )
        except Exception:
            logger.warning("exam_llm_generate_failed", exc_info=True)
            raise

        content = getattr(response, "content", "") or ""
        parsed = _safe_json_load(content)
        sections_raw = parsed.get("sections") or []
        mcqs_raw = parsed.get("mcqs") or []
        shorts_raw = parsed.get("shorts") or []
        longs_raw = parsed.get("longs") or []

        sections: List[GeneratedExamSection] = []
        if isinstance(sections_raw, list):
            for s in sections_raw[: max(12, section_target_count + 2)]:
                if not isinstance(s, dict):
                    continue
                sections.append(
                    GeneratedExamSection(
                        title=str(s.get("title") or "Section"),
                        marks=float(s.get("marks") or 0),
                        description=str(s.get("description") or ""),
                    )
                )

        mcqs: List[GeneratedMcq] = []
        if isinstance(mcqs_raw, list):
            for i, m in enumerate(mcqs_raw):
                if not isinstance(m, dict):
                    continue
                opts = m.get("options")
                if not isinstance(opts, list) or len(opts) < 2:
                    opts = _mcq_option_labels(obj_options)
                opts = [str(x).strip() for x in opts][:obj_options]
                mcqs.append(
                    GeneratedMcq(
                        stem=str(m.get("stem") or f"Question {i+1}?"),
                        options=opts,
                        marks_per=obj_marks,
                    )
                )

        shorts: List[GeneratedShort] = []
        if isinstance(shorts_raw, list):
            for i, s in enumerate(shorts_raw):
                if not isinstance(s, dict):
                    continue
                shorts.append(
                    GeneratedShort(stem=str(s.get("stem") or f"Short {i+1}"), marks_per=short_marks)
                )

        longs: List[GeneratedLong] = []
        if isinstance(longs_raw, list):
            for i, lg in enumerate(longs_raw):
                if not isinstance(lg, dict):
                    continue
                sp = lg.get("subparts")
                if not isinstance(sp, list) or len(sp) < 1:
                    sp = [f"({chr(97+j)}) Subpart {j+1}" for j in range(long_subparts)]
                sp = [str(x).strip() for x in sp][:long_subparts]
                longs.append(
                    GeneratedLong(
                        stem=str(lg.get("stem") or f"Long question {i+1}"),
                        subparts=sp,
                        marks_per=long_marks,
                    )
                )

        # Pad/truncate to paper counts (best-effort)
        while len(mcqs) < obj_count:
            mcqs.append(
                GeneratedMcq(
                    stem=f"Additional MCQ [{len(mcqs)+1}]?",
                    options=_mcq_option_labels(obj_options),
                    marks_per=obj_marks,
                )
            )
            warnings.append("Padded MCQs to match configured count.")
        mcqs = mcqs[:obj_count]

        while len(shorts) < short_pool:
            shorts.append(GeneratedShort(stem=f"Additional short [{len(shorts)+1}]", marks_per=short_marks))
            warnings.append("Padded short questions to match configured count.")
        shorts = shorts[:short_pool]

        while len(longs) < long_pool:
            longs.append(
                GeneratedLong(
                    stem=f"Additional long [{len(longs)+1}]",
                    subparts=[f"({chr(97+j)}) Part {j+1}" for j in range(long_subparts)],
                    marks_per=long_marks,
                )
            )
            warnings.append("Padded long questions to match configured count.")
        longs = longs[:long_pool]

        if len(sections) < section_target_count:
            while len(sections) < section_target_count:
                sections.append(
                    GeneratedExamSection(
                        title=f"Part {len(sections)+1}",
                        marks=float(grand_total / max(section_target_count, 1)),
                        description="Auto-generated section stub.",
                    )
                )
            warnings.append("Padded sections to section_target_count.")
        sections = sections[:section_target_count]

        return GeneratedExam(sections=sections, mcqs=mcqs, shorts=shorts, longs=longs, warnings=warnings)

    async def regenerate_mcq(
        self,
        *,
        subject: str,
        grade: str,
        topic_label: str,
        paper_config: Dict[str, Any],
        difficulty: Optional[str],
        retrieved_chunks: str,
        marks_per: float,
        seed: int = 0,
        previous_stem: Optional[str] = None,
        previous_options: Optional[List[str]] = None,
    ) -> GeneratedMcq:
        if not getattr(llm_settings, "USE_REAL_LLM", False):
            rnd = (seed or 0) + random.randint(1, 10_000)
            n_opts = int((paper_config or {}).get("objOptions") or 4)
            return GeneratedMcq(
                stem=f"Sample MCQ (refresh {rnd}) on {topic_label} for {subject} — new angle than before.",
                options=[f"{L} Option {i+1} (r{rnd % 1000})" for i, L in enumerate(["A", "B", "C", "D", "E"][:n_opts])],
                marks_per=marks_per,
            )

        diff_label = _difficulty_label(difficulty)
        n_opts = int((paper_config or {}).get("objOptions") or 4)
        prev_block = ""
        if previous_stem and str(previous_stem).strip():
            ps = str(previous_stem).strip()[:900]
            prev_block += f"\nDo NOT repeat or lightly paraphrase this prior stem: \"{ps}\"\n"
        if previous_options:
            po = " | ".join(str(x).strip()[:100] for x in previous_options[:6])
            if po:
                prev_block += f"\nPrevious options (write new distractors, new ordering of ideas): {po}\n"
        prompt = f"""
Generate ONE multiple-choice question for {subject} {grade}, {diff_label}.
Topic: {topic_label}. {marks_per} mark(s).
Source: {retrieved_chunks}
Variation seed: {seed} — use a different subtopic, skill, or scenario than any prior version.
{prev_block}
The new item must be clearly distinct (different scenario, numbers, or concept focus).

Return JSON: {{"stem": "...", "options": ["A. ...", "B. ...", "C. ...", "D. ..."]}}
ONLY return valid JSON.
""".strip()
        response = await self.llm_router.generate(
            system_message="Return ONLY valid JSON.",
            prompt=prompt,
            model_config={
                "provider": getattr(llm_settings, "DEFAULT_MODEL_PROVIDER", "openai"),
                "model": getattr(llm_settings, "DEFAULT_MODEL", "gpt-4o-mini"),
                "temperature": 0.52,
                "max_tokens": 900,
            },
        )
        content = getattr(response, "content", "") or ""
        parsed = _safe_json_load(content)
        opts = parsed.get("options")
        if not isinstance(opts, list):
            opts = _mcq_option_labels(n_opts)
        opts = [str(x).strip() for x in opts][:n_opts]
        return GeneratedMcq(
            stem=str(parsed.get("stem") or "Question?"),
            options=opts,
            marks_per=marks_per,
        )

    async def regenerate_short(
        self,
        *,
        subject: str,
        grade: str,
        topic_label: str,
        marks_per: float,
        difficulty: Optional[str],
        retrieved_chunks: str,
        seed: int = 0,
        previous_stem: Optional[str] = None,
    ) -> GeneratedShort:
        if not getattr(llm_settings, "USE_REAL_LLM", False):
            return GeneratedShort(
                stem=f"Explain (refresh {seed}) a different aspect of {topic_label} in {subject} than the prior question.",
                marks_per=marks_per,
            )
        diff_label = _difficulty_label(difficulty)
        prev_block = ""
        if previous_stem and str(previous_stem).strip():
            prev_block = f"\nReplace this prior stem — do NOT repeat it: \"{str(previous_stem).strip()[:800]}\"\n"
        prompt = f"""
Generate ONE short-answer question ({marks_per} marks) for {subject} {grade}.
Topic: {topic_label}. Standard-level difficulty: {diff_label}.
Source: {retrieved_chunks}
Variation seed: {seed}. Use a different angle or skill than before.
{prev_block}

Return JSON: {{"stem": "..."}}
ONLY return valid JSON.
""".strip()
        response = await self.llm_router.generate(
            system_message="Return ONLY valid JSON.",
            prompt=prompt,
            model_config={
                "provider": getattr(llm_settings, "DEFAULT_MODEL_PROVIDER", "openai"),
                "model": getattr(llm_settings, "DEFAULT_MODEL", "gpt-4o-mini"),
                "temperature": 0.52,
                "max_tokens": 600,
            },
        )
        content = getattr(response, "content", "") or ""
        parsed = _safe_json_load(content)
        return GeneratedShort(stem=str(parsed.get("stem") or "Short question"), marks_per=marks_per)

    async def regenerate_long(
        self,
        *,
        subject: str,
        grade: str,
        topic_label: str,
        paper_config: Dict[str, Any],
        difficulty: Optional[str],
        retrieved_chunks: str,
        marks_per: float,
        seed: int = 0,
        previous_stem: Optional[str] = None,
        previous_subparts: Optional[List[str]] = None,
    ) -> GeneratedLong:
        long_subparts = max(1, min(6, int((paper_config or {}).get("longSubparts") or 3)))
        if not getattr(llm_settings, "USE_REAL_LLM", False):
            parts = [f"({chr(97+i)}) Part {i+1} (r{seed % 1000})" for i in range(long_subparts)]
            return GeneratedLong(
                stem=f"Analyse (refresh {seed}) a new scenario for {topic_label} — not the same brief as before.",
                subparts=parts,
                marks_per=marks_per,
            )
        diff_label = _difficulty_label(difficulty)
        prev_block = ""
        if previous_stem and str(previous_stem).strip():
            prev_block += f"\nPrior stem to replace (do not repeat): \"{str(previous_stem).strip()[:800]}\"\n"
        if previous_subparts:
            sp = " | ".join(str(x).strip()[:120] for x in previous_subparts[:8])
            if sp:
                prev_block += f"\nPrior sub-parts (invent new tasks): {sp}\n"
        prompt = f"""
Generate ONE structured/extended question ({marks_per} marks) for {subject} {grade}.
Topic: {topic_label}. Difficulty: {diff_label}.
Exactly {long_subparts} sub-parts required.
Source: {retrieved_chunks}
Variation seed: {seed}. Use a different scenario and command-word pattern than before.
{prev_block}

Return JSON: {{"stem": "...", "subparts": ["(a) ...", "(b) ...", "(c) ..."]}}
ONLY return valid JSON.
""".strip()
        response = await self.llm_router.generate(
            system_message="Return ONLY valid JSON.",
            prompt=prompt,
            model_config={
                "provider": getattr(llm_settings, "DEFAULT_MODEL_PROVIDER", "openai"),
                "model": getattr(llm_settings, "DEFAULT_MODEL", "gpt-4o-mini"),
                "temperature": 0.52,
                "max_tokens": 1200,
            },
        )
        content = getattr(response, "content", "") or ""
        parsed = _safe_json_load(content)
        sp = parsed.get("subparts")
        if not isinstance(sp, list) or len(sp) < 1:
            sp = [f"({chr(97+i)}) Subpart {i+1}" for i in range(long_subparts)]
        sp = [str(x).strip() for x in sp][:long_subparts]
        return GeneratedLong(
            stem=str(parsed.get("stem") or "Long question"),
            subparts=sp,
            marks_per=marks_per,
        )
