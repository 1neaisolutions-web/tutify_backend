from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings
from app.core.logging import get_logger
from app.llm.config import llm_settings
from app.llm.router import ModelRouter

logger = get_logger(__name__)


@dataclass(frozen=True)
class GeneratedQuestion:
    qid: str
    qtype: str  # mcq|tf|short
    prompt: str
    points: float
    options: Optional[List[str]] = None
    response_lines: Optional[int] = None
    extra: Optional[Dict[str, Any]] = None


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
        # best-effort repair: truncate to last closing brace
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
    "a an the and or but in on at to for of is are was were be been being with from by as it this that".split()
)


def _significant_terms(text: str) -> List[str]:
    words = re.findall(r"[A-Za-z]{4,}", text or "")
    return [w.lower() for w in words if w.lower() not in _STOPWORDS]


def _validate_question_grounding(prompt_text: str, context_text: str) -> Optional[str]:
    """Return warning message if prompt terms are absent from context."""
    if not context_text or not prompt_text:
        return None
    ctx_lower = context_text.lower()
    terms = _significant_terms(prompt_text)
    if not terms:
        return None
    if any(t in ctx_lower for t in terms):
        return None
    return "Question terms not found in retrieved context"


def _citation_for_chunk_ids(
    chunk_ids: List[str],
    citation_map: Dict[str, Dict[str, str]],
    topic_label: str,
) -> tuple[str, bool]:
    """Resolve source line from chunk IDs; returns (source_line, verified)."""
    for cid in chunk_ids:
        cit = citation_map.get(str(cid))
        if cit:
            src_label = cit.get("topic_title") or topic_label
            page_rng = cit.get("page_range") or ""
            line = f"{src_label} · pp. {page_rng}" if page_rng else src_label
            return line, True
    return "Unverified source", False


def _best_citation_by_overlap(
    prompt_text: str,
    source_citations: List[Dict[str, str]],
    chunk_texts: Optional[Dict[str, str]],
    topic_label: str,
) -> tuple[str, bool]:
    """Pick citation whose chunk text best overlaps question terms."""
    if not source_citations:
        return "Unverified source", False
    terms = set(_significant_terms(prompt_text))
    if not terms or not chunk_texts:
        cit = source_citations[0]
        src_label = cit.get("topic_title") or topic_label
        page_rng = cit.get("page_range") or ""
        line = f"{src_label} · pp. {page_rng}" if page_rng else src_label
        return line, False
    best_score = -1
    best_cit = source_citations[0]
    for cit in source_citations:
        cid = str(cit.get("chunk_id") or "")
        text = (chunk_texts.get(cid) or "").lower()
        score = sum(1 for t in terms if t in text)
        if score > best_score:
            best_score = score
            best_cit = cit
    src_label = best_cit.get("topic_title") or topic_label
    page_rng = best_cit.get("page_range") or ""
    line = f"{src_label} · pp. {page_rng}" if page_rng else src_label
    return line, best_score > 0


class QuizGenerationService:
    def __init__(self) -> None:
        self.llm_router = ModelRouter(config=llm_settings)

    @staticmethod
    def build_input_hash(payload: Dict[str, Any]) -> str:
        as_json = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(as_json.encode("utf-8")).hexdigest()

    async def generate_questions(
        self,
        *,
        subject: str,
        grade: str,
        topic_label: str,
        difficulty: Optional[str],
        question_count: int,
        include_mcq: bool,
        include_tf: bool,
        include_short: bool,
        counts_by_type: Optional[Dict[str, int]],
        teacher_notes: Optional[str],
        context_text: str,
        avoid_prompts: Optional[List[str]] = None,
        must_differ_from: Optional[str] = None,
        allowed_topic_titles: Optional[List[str]] = None,
        sources_grounded: bool = False,
        source_citations: Optional[List[Dict[str, str]]] = None,
        chunk_texts: Optional[Dict[str, str]] = None,
    ) -> Tuple[List[GeneratedQuestion], List[str], Dict[str, Any]]:
        """
        Generate a list of questions. Output is normalized for DB persistence and
        can be mapped to the frontend `questionStubs` shape.
        """

        warnings: List[str] = []
        # Resolve counts
        types: List[str] = []
        if include_mcq:
            types.append("mcq")
        if include_tf:
            types.append("tf")
        if include_short:
            types.append("short")
        if not types:
            types = ["mcq", "tf", "short"]

        if counts_by_type and any(k in counts_by_type for k in ("mcq", "tf", "short")):
            mcq_n = int(counts_by_type.get("mcq", 0))
            tf_n = int(counts_by_type.get("tf", 0))
            short_n = int(counts_by_type.get("short", 0))
            if mcq_n + tf_n + short_n <= 0:
                mcq_n, tf_n, short_n = question_count, 0, 0
                warnings.append("Custom mix counts were empty; defaulted to MCQ only.")
        else:
            # balanced distribution
            mcq_n = question_count // len(types) + (1 if types[0] == "mcq" and question_count % len(types) else 0)
            # simple: fill round-robin
            seq = [types[i % len(types)] for i in range(question_count)]
            mcq_n = sum(1 for t in seq if t == "mcq")
            tf_n = sum(1 for t in seq if t == "tf")
            short_n = sum(1 for t in seq if t == "short")

        # Token hygiene: keep context bounded to reduce truncation.
        context = (context_text or "").strip()
        if sources_grounded:
            per_q = int(getattr(settings, "QUIZ_MIN_CONTEXT_CHARS_PER_QUESTION", 200))
            min_chars = min(per_q * question_count, 800)
            if len(context) < min_chars:
                raise ValueError(
                    f"Insufficient indexed content for this scope ({len(context)} chars; need ~{min_chars})."
                )

        if len(context) > 12_000:
            context = context[:10_000] + "\n[...context truncated...]\n" + context[-1500:]
            warnings.append("Context was long and was truncated for generation.")

        system_message = (
            "You are an expert assessment designer. Return ONLY valid JSON matching the schema. "
            "Keep language international English, grade-appropriate."
        )

        diff_label = _difficulty_label(difficulty)
        teacher_line = f"\nTeacher focus: {teacher_notes.strip()}" if teacher_notes and teacher_notes.strip() else ""
        avoid = [x for x in (avoid_prompts or []) if isinstance(x, str) and x.strip()]
        avoid_norm = {_norm_prompt(x) for x in avoid}
        avoid_hint = ""
        if avoid:
            trimmed = [re.sub(r"\s+", " ", x.strip())[:240] for x in avoid[:25]]
            avoid_hint = (
                "\nAVOID DUPLICATES:\n"
                "- Do NOT repeat or paraphrase any of these existing questions.\n"
                "- Each new question must be meaningfully different (new concept, scenario, numbers, or framing).\n"
                + "\n".join([f"- {t}" for t in trimmed])
                + "\n"
            )

        replace_hint = ""
        if must_differ_from and str(must_differ_from).strip():
            out_old = re.sub(r"\s+", " ", str(must_differ_from).strip())[:420]
            replace_hint = (
                "\nREGENERATION (single slot):\n"
                f"- The teacher is replacing an existing item. Outgoing question was: \"{out_old}\"\n"
                "- Your new question MUST be clearly different: new scenario, different concept focus, or different numbers — not a light rewording.\n"
            )

        schema = {
            "questions": [
                {
                    "id": "q1",
                    "type": "mcq|tf|short",
                    "prompt": "<string>",
                    "points": 2,
                    "options": ["<string>"],
                    "correct_option_index": 0,
                    "response_lines": 3,
                    "source_chunk_ids": ["<chunk_uuid>"],
                }
            ]
        }

        allowed_line = ""
        if allowed_topic_titles:
            titles = [t for t in allowed_topic_titles if t and t.strip()]
            if titles:
                allowed_line = (
                    "\nALLOWED TOPICS (questions MUST be answerable only from these sections):\n"
                    + "\n".join(f"- {t}" for t in titles)
                    + "\n"
                )

        grounding_rule = (
            "- Every question MUST be answerable solely from the CONTEXT below. "
            "Do NOT use facts from other chapters or general knowledge outside CONTEXT.\n"
            "- If CONTEXT does not mention a concept, do not ask about it.\n"
            "- Each question MUST include source_chunk_ids: array of chunk_id UUIDs from CONTEXT headers.\n"
            if sources_grounded and context
            else "- Use the CONTEXT when present; if context is empty, generate from general knowledge and clearly keep it on-topic.\n"
        )

        prompt = f"""
TASK: Create a formative quiz.\n
SUBJECT: {subject}\n
GRADE: {grade}\n
DIFFICULTY PROFILE: {diff_label}\n
TOPIC SCOPE LABEL: {topic_label}\n
{allowed_line}REQUIREMENTS:\n
- Return a JSON object with key 'questions' (array).\n
- Exactly {question_count} questions total.\n
- Exactly mcq={mcq_n}, tf={tf_n}, short={short_n}.\n
- MCQ: include 4 options; set correct_option_index.\n
- TF: options must be [\"True\",\"False\"] and set correct_option_index (0=True, 1=False).\n
- Short: include response_lines (1-12). Do NOT include options.\n
- Points: MCQ 2, TF 1, Short 3 (you may vary +/-0.5 if needed).\n
{grounding_rule}{avoid_hint}\n
{replace_hint}\n
{teacher_line}\n
SCHEMA EXAMPLE (do not copy values):\n{json.dumps(schema, ensure_ascii=False)}\n
CONTEXT:\n{context}\n
Return only JSON.\n
""".strip()

        llm_temp = 0.45 if (must_differ_from and str(must_differ_from).strip()) else 0.2

        llm_start = None
        try:
            llm_start = True
            response = await self.llm_router.generate(
                system_message=system_message,
                prompt=prompt,
                model_config={
                    "provider": getattr(llm_settings, "DEFAULT_MODEL_PROVIDER", "openai"),
                    "model": getattr(llm_settings, "DEFAULT_MODEL", "gpt-4o-mini"),
                    "temperature": llm_temp,
                    "max_tokens": 2400,
                },
            )
        except Exception as e:
            logger.warning("quiz_llm_generate_failed", exc_info=True)
            raise

        content = getattr(response, "content", "") or ""
        parsed = _safe_json_load(content)
        rows = parsed.get("questions") if isinstance(parsed, dict) else None
        if not isinstance(rows, list):
            raise ValueError("LLM returned invalid quiz JSON: missing questions list.")

        citation_map: Dict[str, Dict[str, str]] = {}
        if source_citations:
            for cit in source_citations:
                cid = str(cit.get("chunk_id") or "")
                if cid:
                    citation_map[cid] = cit

        out: List[GeneratedQuestion] = []
        seen_norm: set[str] = set()
        for i, row in enumerate(rows[:question_count]):
            if not isinstance(row, dict):
                continue
            qtype = (row.get("type") or "").strip().lower()
            if qtype not in ("mcq", "tf", "short"):
                # map common synonyms
                if qtype in ("multiple_choice", "multiple choice"):
                    qtype = "mcq"
                elif qtype in ("true_false", "true/false"):
                    qtype = "tf"
            prompt_text = str(row.get("prompt") or "").strip()
            if not prompt_text:
                continue
            pn = _norm_prompt(prompt_text)
            if pn in avoid_norm:
                warnings.append("Skipped a generated question that duplicated an existing prompt.")
                continue
            if pn in seen_norm:
                warnings.append("Skipped a generated question that duplicated another generated prompt.")
                continue
            seen_norm.add(pn)
            points = float(row.get("points") or (2 if qtype == "mcq" else 1 if qtype == "tf" else 3))
            options = row.get("options")
            resp_lines = row.get("response_lines")

            if qtype == "tf":
                options = ["True", "False"]
            if qtype == "mcq":
                if not isinstance(options, list) or len(options) < 2:
                    options = ["Option A", "Option B", "Option C", "Option D"]
                options = [str(x).strip() for x in options if str(x).strip()][:6]
                if len(options) < 2:
                    options = ["Option A", "Option B", "Option C", "Option D"]
            else:
                options = None

            if qtype == "short":
                try:
                    resp_lines = int(resp_lines) if resp_lines is not None else 3
                except Exception:
                    resp_lines = 3
                resp_lines = max(1, min(12, resp_lines))
            else:
                resp_lines = None

            correct_idx = row.get("correct_option_index")
            extra_data: Dict[str, Any] = {"reviewBadges": {"difficulty": diff_label}}
            if source_citations:
                raw_ids = row.get("source_chunk_ids") or row.get("citations")
                chunk_ids: List[str] = []
                if isinstance(raw_ids, list):
                    for item in raw_ids:
                        if isinstance(item, str):
                            chunk_ids.append(item)
                        elif isinstance(item, dict) and item.get("chunk_id"):
                            chunk_ids.append(str(item["chunk_id"]))
                if chunk_ids:
                    source_line, verified = _citation_for_chunk_ids(
                        chunk_ids, citation_map, topic_label
                    )
                else:
                    source_line, verified = _best_citation_by_overlap(
                        prompt_text, source_citations, chunk_texts, topic_label
                    )
                extra_data["sourceCitation"] = source_line
                extra_data["reviewBadges"]["source"] = source_line
                if not verified:
                    extra_data["reviewBadges"]["scopeWarning"] = "true"
            scope_warn = _validate_question_grounding(prompt_text, context_text or context)
            if scope_warn:
                extra_data.setdefault("reviewBadges", {})["scopeWarning"] = "true"
                warnings.append(scope_warn)
            if correct_idx is not None:
                try:
                    extra_data["correct_option_index"] = int(correct_idx)
                except (TypeError, ValueError):
                    pass

            out.append(
                GeneratedQuestion(
                    qid=str(row.get("id") or f"q{i+1}"),
                    qtype=qtype,
                    prompt=prompt_text,
                    points=points,
                    options=options,
                    response_lines=resp_lines,
                    extra=extra_data,
                )
            )

        if len(out) < question_count:
            warnings.append(f"Generator returned {len(out)} questions; expected {question_count}.")

        meta = {
            "provider": getattr(response, "provider", None),
            "model_used": getattr(response, "model_used", None),
            "finish_reason": getattr(response, "finish_reason", None),
            "content_length": len(content),
        }
        return out, warnings, meta

