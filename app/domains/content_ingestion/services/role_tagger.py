"""
Role tagging for chunks: board-agnostic structure/role taxonomy.
Auto-tag from regex + text patterns; override from document structure_map.
Deterministic, heuristic-only, no ML. OCR-noise robust.
"""
import re
from typing import List, Dict, Any, Optional, Tuple

from app.domains.content_ingestion.providers.base import Chunk

# Role taxonomy (fixed enum, international, board-agnostic)
CHUNK_ROLES = (
    "concept",
    "worked_example",
    "exercise_prompt",
    "exam_question",
    "solution",
    "marking_scheme",
    "unknown",
)
DEFAULT_ROLE = "unknown"

# OCR noise: compiled patterns for pre-normalization (run once)
_RE_MULTI_SPACE = re.compile(r"[ \t]+")
_RE_BROKEN_HYPHEN = re.compile(r"[\u2010\u2011\u2012\u2013\u2014\u2212\uff0d]")
_RE_WEIRD_BULLET = re.compile(r"^[\*\u2022\u2023\u25aa\u25cf\u25e6\u2043]\s*", re.M)
_RE_ROMAN_I_PAREN = re.compile(r"\bi\)\b", re.I)  # i) -> 1) for OCR confusion
_RE_LINE_START_NUMBER = re.compile(r"^(\d+)[\.\)]\s+", re.M)
_RE_LINE_START_ROMAN = re.compile(r"^[ivxlcdm]+[\.\)]\s+", re.M | re.I)
_RE_LINE_START_LETTER = re.compile(r"^\(\s*[a-zA-Z]\s*\)\s+", re.M)


def _normalize_for_role_tagger(text: str) -> str:
    """
    Normalize common OCR artifacts before regex matching.
    Deterministic, no side effects.
    """
    if not text or not isinstance(text, str):
        return ""
    t = text.strip()
    t = _RE_BROKEN_HYPHEN.sub("-", t)
    t = _RE_MULTI_SPACE.sub(" ", t)
    t = _RE_WEIRD_BULLET.sub("", t)
    t = re.sub(r"\n\s*\n\s*\n+", "\n\n", t)
    return t


# Instructional verbs that indicate exercise/question content
_INSTRUCTIONAL_VERBS = (
    "solve", "find", "prove", "show", "calculate", "determine",
    "evaluate", "explain", "write", "simplify",
)
_RE_INSTRUCTIONAL_VERB = re.compile(
    r"\b(" + "|".join(_INSTRUCTIONAL_VERBS) + r")\b", re.I
)

# Summary indicators -> concept
_SUMMARY_INDICATORS = ("key points", "summary", "review notes")
_RE_SUMMARY_INDICATOR = re.compile(
    r"\b(" + "|".join(_SUMMARY_INDICATORS) + r")\b", re.I
)


def _count_question_like_lines(text: str) -> int:
    """Count lines that look like numbered questions (1., 2., (a), (b), i., ii., etc.)."""
    count = 0
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if _RE_LINE_START_NUMBER.match(line):
            count += 1
        elif _RE_LINE_START_ROMAN.match(line):
            count += 1
        elif _RE_LINE_START_LETTER.match(line):
            count += 1
    return count


def _has_instructional_verb(text: str) -> bool:
    """True if text contains at least one instructional verb."""
    return bool(_RE_INSTRUCTIONAL_VERB.search(text))


def _has_question_mark(text: str) -> bool:
    """True if text contains at least one question mark."""
    return "?" in text


def _has_exercise_content_cues(text: str) -> bool:
    """True if text has instructional verb OR question mark (reduces false-positive exercise)."""
    return _has_instructional_verb(text) or _has_question_mark(text)


def _has_summary_indicator(text: str) -> bool:
    """True if text has Key Points, Summary, Review Notes -> concept."""
    return bool(_RE_SUMMARY_INDICATOR.search(text))


def _has_solution_structural_cues(text: str) -> bool:
    """Require keywords PLUS structural cues for solution/marking_scheme."""
    t = text.lower()
    cues = [
        "answer key",
        "answer key:",
        "marking scheme",
        "marking scheme:",
        "solution:",
        "solutions:",
        "answers:",
        "answer:",
    ]
    return any(c in t for c in cues)


def _has_worked_example_structure(text: str) -> bool:
    """worked_example: require 'Example' AND (Step patterns OR multiple math/operation tokens)."""
    t = text
    if not re.search(r"\bexample\b", t, re.I):
        return False
    step_patterns = [
        r"\bstep\s+\d",
        r"^\d+[\.\)]\s+.*\n\s*\d+[\.\)]\s+",
        r"first\s*,?\s*second\s*,?\s*third",
    ]
    if any(re.search(p, t, re.M | re.I | re.S) for p in step_patterns):
        return True
    math_tokens = ["[[MATH]]", "=", "+", "-", "*", "/", "×", "÷", "equation", "solve"]
    hits = sum(1 for m in math_tokens if m.lower() in t.lower())
    return hits >= 2


def _has_concept_definition_no_numbering(text: str) -> bool:
    """concept: definition-like phrasing AND no multi-line numbering."""
    def_phrases = [
        r"\bis\s+defined\s+as\b",
        r"\brefers\s+to\b",
        r"\bmeans\s+that\b",
        r"\bdefinition\s*[:\.]",
    ]
    has_def = any(re.search(p, text, re.I) for p in def_phrases)
    q_lines = _count_question_like_lines(text)
    return has_def and q_lines < 2


def get_role_from_structure_map(
    page_start: Optional[int],
    page_end: Optional[int],
    structure_map: Optional[List[Dict[str, Any]]],
) -> Optional[str]:
    """Public: get role from structure_map if chunk page range overlaps."""
    return _structure_map_override(page_start, page_end, structure_map)


def _structure_map_override(
    page_start: Optional[int],
    page_end: Optional[int],
    structure_map: Optional[List[Dict[str, Any]]],
) -> Optional[str]:
    """If structure_map has a range overlapping this chunk, return that role. Manual wins over auto."""
    if not structure_map or not isinstance(structure_map, list):
        return None
    for entry in structure_map:
        if not isinstance(entry, dict):
            continue
        start = entry.get("page_start", entry.get("start_page"))
        end = entry.get("page_end", entry.get("end_page"))
        role = entry.get("role")
        if role not in CHUNK_ROLES:
            continue
        if start is None or end is None:
            continue
        ps = page_start if page_start is not None else page_end
        pe = page_end if page_end is not None else page_start
        if ps is None:
            continue
        if pe is None:
            pe = ps
        if ps <= end and pe >= start:
            return role
    return None


def infer_role_from_text(
    text: str,
    min_chars_for_question_block: int = 200,
) -> Tuple[str, float]:
    """
    Auto-tag role from chunk text. Uses pre-normalization, anti-false-positive safeguards.
    Returns (role, confidence).
    """
    if not (text or "").strip():
        return DEFAULT_ROLE, 0.0
    norm = _normalize_for_role_tagger(text)
    if not norm:
        return DEFAULT_ROLE, 0.0
    total_chars = len(norm)

    # 0) Summary indicators -> concept (before exercise to avoid false-positive)
    if _has_summary_indicator(norm):
        return "concept", 0.85

    # 1) solution / marking_scheme: require structural cues
    if re.search(r"\b(marking\s+scheme|marking\s+criteria)\b", norm, re.I):
        if _has_solution_structural_cues(norm):
            return "marking_scheme", 0.9
        return DEFAULT_ROLE, 0.0
    if re.search(r"\b(solution|answer(s)?)\s*[:\.]?\s*$", norm, re.M | re.I) or re.search(
        r"\b(solution|answer(s)?)\b", norm, re.I
    ):
        if _has_solution_structural_cues(norm) or total_chars >= 150:
            return "solution", 0.85
        return DEFAULT_ROLE, 0.0

    # 2) exam_question: require min chars + >= 2 numbered lines + (verb OR ?)
    if re.search(r"\b(exam(ination)?\s+[Qq]uestion|past\s+paper)\b", norm, re.I):
        if total_chars < min_chars_for_question_block:
            return DEFAULT_ROLE, 0.0
        q_lines = _count_question_like_lines(norm)
        if q_lines >= 2 and _has_exercise_content_cues(norm):
            return "exam_question", 0.9
        if total_chars >= min_chars_for_question_block and _has_exercise_content_cues(norm):
            return "exam_question", 0.7
        return DEFAULT_ROLE, 0.0

    # 3) exercise_prompt: require min chars + >= 2 numbered lines + (verb OR ?)
    exercise_strong = [
        (r"exercise\s+\d+", 0.9),
        (r"review\s+exercise", 0.85),
        (r"questions?\s+for\s+practice", 0.85),
    ]
    for pat, conf in exercise_strong:
        if re.search(pat, norm, re.I):
            if total_chars < min_chars_for_question_block:
                return "exercise_prompt", conf * 0.7
            if _has_exercise_content_cues(norm):
                return "exercise_prompt", conf
            q_lines = _count_question_like_lines(norm)
            if q_lines >= 2:
                return "exercise_prompt", conf * 0.8
            return "exercise_prompt", conf * 0.7

    exercise_weak = [
        (r"^\d+[\.\)]\s+", re.M),
        (r"^\(\s*[a-zA-Z]\s*\)\s+", re.M),
        (r"^[ivxlcdm]+[\.\)]\s+", re.M | re.I),
        (r"\b(Solve|Find|Prove|Show|Calculate|Evaluate|Simplify|Determine|Explain|Write)\b", re.I),
    ]
    for pat, flags in exercise_weak:
        if re.search(pat, norm, flags):
            if total_chars < min_chars_for_question_block:
                return DEFAULT_ROLE, 0.0
            q_lines = _count_question_like_lines(norm)
            if q_lines >= 2 and _has_exercise_content_cues(norm):
                return "exercise_prompt", 0.7
            if q_lines >= 2 and not _has_exercise_content_cues(norm):
                return DEFAULT_ROLE, 0.0
            if _has_exercise_content_cues(norm):
                return "exercise_prompt", 0.5
            return DEFAULT_ROLE, 0.0

    # 4) worked_example: require "Example" AND structure
    if re.search(r"\bexample\s+\d+", norm, re.I) or re.search(r"^Example\s*[:\.]", norm, re.M | re.I):
        if _has_worked_example_structure(norm):
            return "worked_example", 0.9
        return "worked_example", 0.6

    step_like = re.search(r"^\d+[\.\)]\s+.*\n\s*\d+[\.\)]\s+", norm, re.M | re.S)
    if step_like and _has_worked_example_structure(norm):
        return "worked_example", 0.6

    # 5) concept: definition-like
    if _has_concept_definition_no_numbering(norm):
        return "concept", 0.85
    if re.search(r"\b(is\s+defined\s+as|refers\s+to|means\s+that)\b", norm, re.I):
        return "concept", 0.75
    if re.search(r"\bdefinition\s*[:\.]", norm, re.I):
        return "concept", 0.85
    if re.search(r"\[\[MATH\]\]", norm, re.I) and total_chars >= 100:
        return "concept", 0.5

    return DEFAULT_ROLE, 0.0


def assign_chunk_roles(
    chunks: List[Chunk],
    structure_map: Optional[List[Dict[str, Any]]] = None,
    min_chars_for_question_block: int = 200,
) -> None:
    """
    Set chunk.metadata for each chunk: auto_role, auto_confidence, role, role_source.
    Manual overrides from structure_map always win. Modifies chunks in place.
    """
    for ch in chunks:
        page_start = getattr(ch, "page_start", None)
        page_end = getattr(ch, "page_end", None)
        override = _structure_map_override(page_start, page_end, structure_map)
        auto_role, auto_conf = infer_role_from_text(
            ch.text or "",
            min_chars_for_question_block=min_chars_for_question_block,
        )
        meta = dict(ch.metadata or {})
        meta["auto_role"] = auto_role
        meta["auto_confidence"] = round(auto_conf, 2)
        if override:
            meta["role"] = override
            meta["role_source"] = "manual"
        else:
            meta["role"] = auto_role
            meta["role_source"] = "auto"
        ch.metadata = meta


def compute_role_distribution(chunks: List[Chunk]) -> Dict[str, int]:
    """Compute role distribution for QA visibility."""
    dist: Dict[str, int] = {r: 0 for r in CHUNK_ROLES}
    for ch in chunks:
        meta = ch.metadata or {}
        role = meta.get("role") or DEFAULT_ROLE
        if role in dist:
            dist[role] += 1
        else:
            dist[DEFAULT_ROLE] += 1
    return dist


def compute_role_tagging_metrics(
    distribution: Dict[str, int],
    total_chunks: int,
) -> Dict[str, float]:
    """
    Compute lightweight QA metrics for role tagging.
    known_role_ratio, exercise_ratio, concept_ratio.
    """
    if total_chunks <= 0:
        return {
            "known_role_ratio": 0.0,
            "exercise_ratio": 0.0,
            "concept_ratio": 0.0,
            "total_chunks": 0,
        }
    unknown = distribution.get("unknown", 0)
    known_role_ratio = 1.0 - (unknown / total_chunks)
    exercise = sum(distribution.get(r, 0) for r in ("exercise_prompt", "exam_question"))
    concept = sum(distribution.get(r, 0) for r in ("concept", "worked_example"))
    return {
        "known_role_ratio": round(known_role_ratio, 4),
        "exercise_ratio": round(exercise / total_chunks, 4),
        "concept_ratio": round(concept / total_chunks, 4),
        "total_chunks": total_chunks,
    }
