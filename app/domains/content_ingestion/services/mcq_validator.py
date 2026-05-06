"""
MCQ validity checks for worksheet generation.
- Exactly 4 options per MCQ.
- correct_answer in A–D.
- Options unique.
- Reject stems that imply multiple correct answers (e.g. "identify a proper subset" unless only one option is proper).
"""
from typing import Any, Dict, List, Tuple


def _get_question_text(q: Dict[str, Any]) -> str:
    """Extract question text from question dict."""
    text = (q.get("question") or q.get("question_text") or "").strip()
    return text if isinstance(text, str) else ""


def _normalize_option(o: Any) -> str:
    """Normalize option for uniqueness check."""
    if o is None:
        return ""
    s = str(o).strip()
    # Strip leading A), B), A., B. so "A) 2" and "2" from another option don't collide
    if len(s) >= 2 and s[0].upper() in "ABCD" and s[1] in ".)":
        s = s[2:].strip()
    return s


def validate_mcq(questions: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """
    Validate all MCQ questions: exactly 4 options, correct_answer A–D, options unique.
    Returns (passed, report_string).
    """
    if not questions:
        return True, "No questions to validate."

    failures: List[str] = []
    for i, q in enumerate(questions):
        qtype = (q.get("type") or "").lower()
        if "mcq" not in qtype and "multiple" not in qtype:
            continue

        opts = q.get("options")
        if not isinstance(opts, list):
            failures.append(f"Q{i+1}: MCQ missing or invalid 'options' (must be a list).")
            continue
        if len(opts) != 4:
            failures.append(f"Q{i+1}: MCQ must have exactly 4 options, got {len(opts)}.")
            continue

        # correct_answer: may be "A"/"B"/"C"/"D" or "correct_option" in some schemas
        correct = (q.get("correct_answer") or q.get("correct_option") or "").strip().upper()
        if correct not in ("A", "B", "C", "D"):
            failures.append(f"Q{i+1}: MCQ correct_answer must be A, B, C, or D, got {repr(q.get('correct_answer') or q.get('correct_option'))}.")
            continue

        # Options unique (after normalizing letter prefix)
        normalized = [_normalize_option(o) for o in opts]
        if len(normalized) != len(set(normalized)):
            failures.append(f"Q{i+1}: MCQ options must be unique.")
            continue

        # Ambiguous stem heuristic: "identify a proper subset" / "which of the following is a" can allow multiple
        # We only flag obvious "identify one" vs "identify all/any" if we have a simple check. For now we require
        # exactly one correct and 4 options; ambiguous stems are harder to detect without LLM. Skip for v1.

    if failures:
        return False, "MCQ validation failed: " + "; ".join(failures[:5])
    return True, "MCQ validation passed."
