from __future__ import annotations

import hashlib
import json
import re
import secrets
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.core.logging import get_logger
from app.llm.config import llm_settings
from app.llm.router import ModelRouter

logger = get_logger(__name__)


@dataclass(frozen=True)
class GeneratedBlock:
    bid: str
    btype: str
    prompt: Optional[str]
    points: float
    options: Optional[List[str]] = None
    answer: Optional[str] = None
    sample_answer: Optional[str] = None
    response_lines: Optional[int] = None
    left: Optional[List[str]] = None
    right: Optional[List[str]] = None


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
        return json.loads(raw)
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


def _norm_prompt(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "which",
        "of",
        "following",
        "what",
        "how",
        "why",
        "when",
        "where",
        "this",
        "that",
        "these",
        "those",
        "to",
        "in",
        "for",
        "on",
        "with",
        "at",
        "by",
        "or",
        "and",
        "be",
        "as",
        "if",
        "your",
        "you",
        "we",
        "their",
        "there",
        "from",
        "into",
        "about",
        "than",
        "then",
        "each",
        "all",
        "any",
        "some",
        "one",
        "two",
        "most",
        "least",
        "not",
        "no",
        "yes",
    }
)


def _word_tokens(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", _norm_prompt(s)))


def _content_tokens(s: str) -> set[str]:
    """Meaningful tokens only — avoids flagging different MCQs that share 'which of the following'."""
    return {t for t in _word_tokens(s) if t not in _STOPWORDS and len(t) > 2}


def _content_overlap_ratio(a: str, b: str) -> float:
    wa, wb = _content_tokens(a), _content_tokens(b)
    if len(wa) < 3 or len(wb) < 3:
        return 0.0
    inter = len(wa & wb)
    return inter / max(len(wa), len(wb))


def _too_close_to_any(candidate: str, avoid: List[str], *, overlap_min: float = 0.78) -> bool:
    """True if candidate is identical, nearly identical, or reuses most distinctive words vs any avoided string."""
    cn = _norm_prompt(candidate)
    if len(cn) < 8:
        return False
    for prev in avoid:
        pn = _norm_prompt(prev)
        if not pn or len(pn) < 8:
            continue
        if cn == pn:
            return True
        if len(cn) > 40 and len(pn) > 40 and (cn in pn or pn in cn):
            return True
        if _content_overlap_ratio(candidate, prev) >= overlap_min:
            return True
    return False


def _generated_block_primary_text(b: GeneratedBlock) -> str:
    if b.btype == "match":
        parts = [f"{l}::{r}" for l, r in zip(b.left or [], b.right or [])]
        return " ".join(parts)
    return (b.prompt or "").strip()


def _balanced_type_sequence(
    question_count: int,
    *,
    include_mcq: bool,
    include_fill_blank: bool,
    include_short: bool,
    include_match: bool,
) -> List[str]:
    types: List[str] = []
    if include_mcq:
        types.append("mcq")
    if include_fill_blank:
        types.append("fill_blank")
    if include_short:
        types.append("short")
    if include_match:
        types.append("match")
    if not types:
        types = ["mcq", "fill_blank", "short", "match"]
    return [types[i % len(types)] for i in range(question_count)]


def _resolve_counts(
    question_count: int,
    *,
    mix_mode: str,
    include_mcq: bool,
    include_fill_blank: bool,
    include_short: bool,
    include_match: bool,
    counts_by_type: Optional[Dict[str, int]],
) -> Tuple[List[str], List[str]]:
    """Returns (warnings, ordered type sequence for each slot)."""
    warnings: List[str] = []
    if mix_mode == "custom" and counts_by_type:
        mcq_n = int(counts_by_type.get("mcq", 0) or 0)
        fb_n = int(counts_by_type.get("fill_blank", 0) or 0)
        sh_n = int(counts_by_type.get("short", 0) or 0)
        mt_n = int(counts_by_type.get("match", 0) or 0)
        if not include_mcq:
            mcq_n = 0
        if not include_fill_blank:
            fb_n = 0
        if not include_short:
            sh_n = 0
        if not include_match:
            mt_n = 0
        seq: List[str] = []
        seq.extend(["mcq"] * mcq_n)
        seq.extend(["fill_blank"] * fb_n)
        seq.extend(["short"] * sh_n)
        seq.extend(["match"] * mt_n)
        if len(seq) == 0:
            warnings.append("Custom mix counts were empty; using balanced mix.")
            return warnings, _balanced_type_sequence(
                question_count,
                include_mcq=include_mcq,
                include_fill_blank=include_fill_blank,
                include_short=include_short,
                include_match=include_match,
            )
        if len(seq) != question_count:
            warnings.append(f"Custom counts length {len(seq)} adjusted to questionCount {question_count}.")
            if len(seq) > question_count:
                seq = seq[:question_count]
            else:
                fill = _balanced_type_sequence(
                    question_count - len(seq),
                    include_mcq=include_mcq,
                    include_fill_blank=include_fill_blank,
                    include_short=include_short,
                    include_match=include_match,
                )
                seq = seq + fill
        return warnings, seq[:question_count]

    return warnings, _balanced_type_sequence(
        question_count,
        include_mcq=include_mcq,
        include_fill_blank=include_fill_blank,
        include_short=include_short,
        include_match=include_match,
    )


def _stub_block(btype: str, idx: int) -> GeneratedBlock:
    if btype == "mcq":
        opts = ["Option A", "Option B", "Option C", "Option D"]
        return GeneratedBlock(
            bid=f"stub-{idx}",
            btype="mcq",
            prompt=f"(Stub) Sample MCQ #{idx + 1} for this topic.",
            points=1.0,
            options=opts,
            answer="Option B",
        )
    if btype == "fill_blank":
        pairs = [
            ("The SI unit of force is the ______.", "newton"),
            ("The SI base unit for electric current is the ______.", "ampere"),
            ("Energy transferred per second is measured in ______.", "watts"),
            ("The SI unit of frequency is the ______.", "hertz"),
            ("Distance divided by time gives ______ in SI.", "speed"),
        ]
        prompt, answer = pairs[idx % len(pairs)]
        if "______" not in prompt:
            prompt = f"{prompt.rstrip('.')} ______."
        return GeneratedBlock(
            bid=f"stub-{idx}",
            btype="fill_blank",
            prompt=prompt,
            points=1.0,
            answer=answer,
        )
    if btype == "short":
        return GeneratedBlock(
            bid=f"stub-{idx}",
            btype="short",
            prompt=f"(Stub) Short response #{idx + 1}: explain one key idea in 2–4 sentences.",
            points=2.0,
            sample_answer="Model answer: cite evidence from the source material.",
            response_lines=4,
        )
    return GeneratedBlock(
        bid=f"stub-{idx}",
        btype="match",
        prompt=None,
        points=1.0,
        left=["Term A", "Term B"],
        right=["Definition A", "Definition B"],
    )


def _normalize_block(row: Dict[str, Any], expected_type: Optional[str], idx: int) -> Optional[GeneratedBlock]:
    btype = (row.get("type") or "").strip().lower()
    if expected_type:
        btype = expected_type
    if btype not in ("mcq", "fill_blank", "short", "match"):
        return None

    points = float(row.get("points") or 1.0)
    points = max(0.0, min(100.0, points))

    if btype == "mcq":
        prompt = str(row.get("prompt") or "").strip()
        options = row.get("options")
        if not isinstance(options, list):
            options = ["A", "B", "C", "D"]
        options = [str(x).strip() for x in options if str(x).strip()][:6]
        if len(options) < 2:
            options = ["Option A", "Option B", "Option C", "Option D"]
        answer = str(row.get("answer") or "").strip()
        if answer not in options:
            answer = options[0] if options else "A"
        if not prompt:
            return None
        return GeneratedBlock(bid=str(row.get("id") or f"b{idx}"), btype="mcq", prompt=prompt, points=points, options=options, answer=answer)

    if btype == "fill_blank":
        prompt = str(row.get("prompt") or "").strip()
        answer = str(row.get("answer") or "").strip()
        if not prompt or not answer:
            return None
        if "______" not in prompt:
            prompt = prompt + " ______"
        return GeneratedBlock(bid=str(row.get("id") or f"b{idx}"), btype="fill_blank", prompt=prompt, points=points, answer=answer)

    if btype == "short":
        prompt = str(row.get("prompt") or "").strip()
        sample = str(row.get("sample_answer") or row.get("sampleAnswer") or "").strip()
        try:
            rl = int(row.get("response_lines") or row.get("responseLines") or 4)
        except (TypeError, ValueError):
            rl = 4
        rl = max(2, min(8, rl))
        if not prompt:
            return None
        return GeneratedBlock(
            bid=str(row.get("id") or f"b{idx}"),
            btype="short",
            prompt=prompt,
            points=points,
            sample_answer=sample or "See source material.",
            response_lines=rl,
        )

    left = row.get("left")
    right = row.get("right")
    if not isinstance(left, list) or not isinstance(right, list):
        return None
    left_l = [str(x).strip() for x in left if str(x).strip()][:6]
    right_l = [str(x).strip() for x in right if str(x).strip()][:6]
    if len(left_l) < 2 or len(left_l) != len(right_l):
        return None
    return GeneratedBlock(bid=str(row.get("id") or f"b{idx}"), btype="match", prompt=None, points=points, left=left_l, right=right_l)


class WorksheetGenerationService:
    def __init__(self) -> None:
        self.llm_router = ModelRouter(config=llm_settings)

    @staticmethod
    def build_input_hash(payload: Dict[str, Any]) -> str:
        as_json = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(as_json.encode("utf-8")).hexdigest()

    async def generate_blocks(
        self,
        *,
        subject: str,
        grade: str,
        topic_label: str,
        difficulty: Optional[str],
        question_count: int,
        mix_mode: str,
        include_mcq: bool,
        include_fill_blank: bool,
        include_short: bool,
        include_match: bool,
        counts_by_type: Optional[Dict[str, int]],
        teacher_notes: Optional[str],
        retrieved_chunks: str,
        avoid_prompts: Optional[List[str]] = None,
        llm_temperature: Optional[float] = None,
        extra_instruction: str = "",
        allow_internal_salvage: bool = True,
    ) -> Tuple[List[GeneratedBlock], List[str], Dict[str, Any]]:
        warn, seq = _resolve_counts(
            question_count,
            mix_mode=mix_mode,
            include_mcq=include_mcq,
            include_fill_blank=include_fill_blank,
            include_short=include_short,
            include_match=include_match,
            counts_by_type=counts_by_type,
        )
        warnings = list(warn)

        context = (retrieved_chunks or "").strip()
        if len(context) > 12_000:
            context = context[:10_000] + "\n[...context truncated...]\n" + context[-1500:]
            warnings.append("Context was long and was truncated for generation.")

        diff_label = _difficulty_label(difficulty)
        teacher_line = f"\nTeacher focus: {teacher_notes.strip()}" if teacher_notes and teacher_notes.strip() else ""
        avoid = [x for x in (avoid_prompts or []) if isinstance(x, str) and x.strip()]
        avoid_norm = {_norm_prompt(x) for x in avoid}
        avoid_hint = ""
        if avoid:
            trimmed = [re.sub(r"\s+", " ", x.strip())[:240] for x in avoid[:25]]
            avoid_hint = (
                "\nAVOID DUPLICATES:\n"
                "- Do NOT repeat or paraphrase these existing prompts (same concept, reordered wording, or trivial edits).\n"
                "- Each new item must test a different fact, scenario, or skill angle.\n"
                + "\n".join([f"- {t}" for t in trimmed])
                + "\n"
            )
        nonce = secrets.token_hex(3)
        novelty_line = (
            f"\nInternal variation id: {nonce} (ignore in output; use it only as a randomness hint for diversity.)\n"
            if avoid
            else ""
        )

        system_message = (
            "You are an expert worksheet designer. Return ONLY valid JSON matching the schema. "
            "Keep language international English, grade-appropriate."
        )
        schema_hint = {
            "blocks": [
                {"type": "mcq", "prompt": "?", "options": ["A", "B", "C", "D"], "answer": "B"},
                {"type": "fill_blank", "prompt": "The ______ ...", "answer": "word"},
                {"type": "short", "prompt": "?", "sample_answer": "...", "response_lines": 4},
                {"type": "match", "left": ["t1"], "right": ["d1"]},
            ]
        }
        prompt = f"""
You are a worksheet generator for {subject} {grade} students.
Difficulty: {diff_label}
Topic: {topic_label}
Source content:
{context}
{teacher_line}
{avoid_hint}
{novelty_line}
{extra_instruction.strip()}

Generate exactly {question_count} worksheet blocks in order. Per-slot types (use this exact sequence):
{json.dumps(seq)}

Return JSON object: {{"blocks": [ ... ]}}
Each block must match its assigned type from the sequence (same index).
Rules:
- fill_blank prompts MUST contain exactly one "______" (6 underscores)
- match: left and right same length, 2-6 items each; omit "prompt" or use null
- mcq: 2-6 options; "answer" must exactly equal one option string
- short: response_lines between 2 and 8
- Points default 1.0 (vary slightly if needed)
- Every block in this batch must be unique: no repeated stems, duplicate fill-in sentences, or copy-pasted MCQ prompts; vary scenarios and facts across slots.

Schema example (structure only):
{json.dumps(schema_hint, ensure_ascii=False)}

Return ONLY the JSON object, no prose.
""".strip()

        if not getattr(llm_settings, "USE_REAL_LLM", False):
            out = [_stub_block(seq[i], i) for i in range(len(seq))]
            return out, warnings + ["Stub generation (USE_REAL_LLM=false)."], {"model_used": "stub"}

        base_temp = 0.42 if avoid else 0.2
        temp = float(llm_temperature) if llm_temperature is not None else base_temp
        temp = max(0.0, min(1.0, temp))

        try:
            response = await self.llm_router.generate(
                system_message=system_message,
                prompt=prompt,
                model_config={
                    "provider": getattr(llm_settings, "DEFAULT_MODEL_PROVIDER", "openai"),
                    "model": getattr(llm_settings, "DEFAULT_MODEL", "gpt-4o-mini"),
                    "temperature": temp,
                    "max_tokens": 4000,
                },
            )
        except Exception:
            logger.warning("worksheet_llm_generate_failed", exc_info=True)
            out = [_stub_block(seq[i], i) for i in range(len(seq))]
            return out, warnings + ["LLM call failed; returned stub blocks."], {"model_used": "stub-error"}

        content = getattr(response, "content", "") or ""
        try:
            parsed = _safe_json_load(content)
        except Exception:
            out = [_stub_block(seq[i], i) for i in range(len(seq))]
            return out, warnings + ["Invalid LLM JSON; returned stub blocks."], {"model_used": "stub-parse"}

        rows = parsed.get("blocks") if isinstance(parsed, dict) else None
        if not isinstance(rows, list):
            out = [_stub_block(seq[i], i) for i in range(len(seq))]
            return out, warnings + ["Missing blocks array; returned stub blocks."], {"model_used": "stub-shape"}

        out: List[GeneratedBlock] = []
        seen: set[str] = set()
        for i, expected in enumerate(seq):
            row = rows[i] if i < len(rows) and isinstance(rows[i], dict) else {}
            blk = _normalize_block(row, expected, i)
            if blk is None:
                blk = _stub_block(expected, i)
                warnings.append(f"Slot {i} failed validation; stub inserted.")
            primary = _generated_block_primary_text(blk)
            pn = _norm_prompt(primary)
            dup_vs_prior = bool(avoid) and (pn in avoid_norm or _too_close_to_any(primary, avoid))
            dup_internal = pn in seen

            if dup_internal or dup_vs_prior:
                salvaged_ok = False
                if allow_internal_salvage and getattr(llm_settings, "USE_REAL_LLM", False):
                    so_far = [_generated_block_primary_text(x) for x in out]
                    combined_avoid = [x for x in so_far + avoid if x.strip()]
                    try:
                        alt = await self.regenerate_block(
                            block_type=expected,
                            subject=subject,
                            grade=grade,
                            topic_label=topic_label,
                            difficulty=difficulty,
                            teacher_notes=teacher_notes,
                            retrieved_chunks=retrieved_chunks,
                            avoid_prompts=combined_avoid,
                        )
                        ap = _generated_block_primary_text(alt)
                        stub_like = ap.startswith("(Stub)") or "Sample MCQ" in ap
                        pn_alt = _norm_prompt(ap)
                        if (
                            alt.btype == expected
                            and not stub_like
                            and pn_alt not in seen
                            and not (avoid and _too_close_to_any(ap, avoid))
                        ):
                            blk, primary, pn = alt, ap, pn_alt
                            salvaged_ok = True
                    except Exception:
                        logger.warning("worksheet_slot_salvage_failed", exc_info=True)
                if not salvaged_ok:
                    blk = _stub_block(expected, i)
                    warnings.append(
                        f"Slot {i} duplicated another item or matched restricted text; "
                        "could not auto-fix — try Regenerate on that question."
                    )
            seen.add(pn)
            out.append(blk)

        meta = {
            "provider": getattr(response, "provider", None),
            "model_used": getattr(response, "model_used", None),
            "finish_reason": getattr(response, "finish_reason", None),
            "content_length": len(content),
        }
        return out, warnings, meta

    async def regenerate_block(
        self,
        *,
        block_type: str,
        subject: str,
        grade: str,
        topic_label: str,
        difficulty: Optional[str],
        teacher_notes: Optional[str],
        retrieved_chunks: str,
        avoid_prompts: Optional[List[str]] = None,
    ) -> GeneratedBlock:
        avoid_base = [x for x in (avoid_prompts or []) if isinstance(x, str) and x.strip()]
        candidate_avoid = list(avoid_base)
        best: Optional[GeneratedBlock] = None
        all_warnings: List[str] = []
        temps = (0.38, 0.56, 0.74, 0.9)
        for attempt, temp in enumerate(temps):
            extra = ""
            if attempt > 0:
                extra = (
                    "\n=== SINGLE-QUESTION REGENERATION ===\n"
                    "Prior outputs were too close to existing worksheet content.\n"
                    "Write ONE replacement question that:\n"
                    "- targets a different sub-skill or fact than anything under AVOID DUPLICATES,\n"
                    "- uses different numbers, scenarios, or vocabulary where applicable,\n"
                    "- is still correct for the topic and grade.\n"
                )
            blocks, warnings, _meta = await self.generate_blocks(
                subject=subject,
                grade=grade,
                topic_label=topic_label,
                difficulty=difficulty,
                question_count=1,
                mix_mode="custom",
                include_mcq=block_type == "mcq",
                include_fill_blank=block_type == "fill_blank",
                include_short=block_type == "short",
                include_match=block_type == "match",
                counts_by_type={block_type: 1},
                teacher_notes=teacher_notes,
                retrieved_chunks=retrieved_chunks,
                avoid_prompts=candidate_avoid,
                llm_temperature=temp,
                extra_instruction=extra,
                allow_internal_salvage=False,
            )
            all_warnings.extend(warnings)
            if not blocks:
                continue
            b = blocks[0]
            if b.btype != block_type:
                continue
            primary = _generated_block_primary_text(b)
            stub_like = primary.startswith("(Stub)") or "Sample MCQ" in primary
            if stub_like:
                candidate_avoid = avoid_base + [f"stub-reject-{attempt}"]
                continue
            if not _too_close_to_any(primary, avoid_base):
                if all_warnings:
                    logger.info("worksheet_regenerate_warnings", extra={"warnings": all_warnings[:8]})
                return b
            best = b
            candidate_avoid = avoid_base + [primary[:320]]

        if all_warnings:
            logger.info("worksheet_regenerate_warnings", extra={"warnings": all_warnings[:8]})
        if best and best.btype == block_type:
            logger.warning("worksheet_regenerate_fell_back_similar", extra={"block_type": block_type})
            return best
        return _stub_block(block_type, 0)
