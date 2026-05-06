"""
Difficulty fidelity validator for worksheet generation.
Uses fast, deterministic heuristics to ensure easy/medium/hard outputs
are measurably different and match requested difficulty.
"""
from typing import Any, Dict, List, Optional, Tuple

# Phrases that indicate higher-order / justification style (hard)
HIGHER_ORDER_PHRASES = [
    "justify", "prove", "explain why", "explain how", "why does", "why is",
    "show that", "derive", "compare", "evaluate", "which is greater",
    "reasoning", "give a reason", "without using", "hence find", "hence show",
]
# Constraint / multi-constraint signals
CONSTRAINT_PHRASES = ["if ", "when ", "given that", "given ", "at least", "at most", "such that", "where "]
# Multi-step signals
MULTI_STEP_PHRASES = [
    "first ", "then ", "using ", "and hence", "step 1", "step 2",
    "using the above", "from part (a)", "from part (b)", "hence ", "thus ",
]
# Math-specific: expressions, interpretation, constraints
MATH_DEPTH_PHRASES = [
    "form an expression", "form an equation", "write down the expression",
    "interpret", "state the", "in terms of", "solve the inequality",
    "show that", "hence find", "find the value of",
]


def _get_question_text(q: Dict[str, Any]) -> str:
    """Extract question text from question dict (API or LLM format)."""
    text = (q.get("question") or q.get("question_text") or "").strip()
    return text if isinstance(text, str) else ""


def score_question(question: Dict[str, Any]) -> float:
    """
    Compute a rough complexity score for a single question (0 = very easy, higher = harder).
    Deterministic heuristics only; no LLM.
    """
    text = _get_question_text(question).lower()
    if not text:
        return 0.0

    score = 0.0

    # Higher-order / justify style: strong signal for hard
    for phrase in HIGHER_ORDER_PHRASES:
        if phrase in text:
            score += 1.2
            break
    # Additional justify-style (count once)
    if any(p in text for p in ["why", "explain", "justify", "prove", "show that", "derive"]):
        score += 0.5

    # Constraints: commas/clauses as proxy for "number of conditions"
    constraint_count = sum(1 for p in CONSTRAINT_PHRASES if p in text)
    score += 0.4 * min(constraint_count, 4)
    # Comma/clause heuristic (rough)
    comma_clauses = max(0, text.count(",") - 1) + (1 if " and " in text or " or " in text else 0)
    score += 0.15 * min(comma_clauses, 5)

    # Multi-step
    for phrase in MULTI_STEP_PHRASES:
        if phrase in text:
            score += 0.6
            break
    if "part (a)" in text or "part (b)" in text or "(i)" in text or "(ii)" in text:
        score += 0.8

    # Math depth
    for phrase in MATH_DEPTH_PHRASES:
        if phrase in text:
            score += 0.5
            break

    # Length heuristic: longer often = more complex (cap effect)
    word_count = len(text.split())
    if word_count > 40:
        score += 0.4
    elif word_count > 25:
        score += 0.2

    return round(score, 2)


def _pct_justify_style(questions: List[Dict[str, Any]]) -> float:
    """Fraction of questions that contain justify/prove/explain why style."""
    if not questions:
        return 0.0
    count = 0
    for q in questions:
        text = _get_question_text(q).lower()
        if any(p in text for p in ["justify", "prove", "explain why", "show that", "derive", "why does", "why is"]):
            count += 1
    return count / len(questions)


def _pct_multi_step(questions: List[Dict[str, Any]]) -> float:
    """Fraction of questions that suggest 2+ step reasoning (multi-step phrases or part (a)/(b))."""
    if not questions:
        return 0.0
    count = 0
    for q in questions:
        text = _get_question_text(q).lower()
        if any(p in text for p in MULTI_STEP_PHRASES + ["part (a)", "part (b)", "(i)", "(ii)", "first ", "then ", "hence "]):
            count += 1
    return count / len(questions)


def get_worksheet_difficulty_stats(questions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Return average complexity score and distribution stats."""
    if not questions:
        return {"avg_score": 0.0, "pct_justify_style": 0.0, "pct_multi_step": 0.0, "scores": []}
    scores = [score_question(q) for q in questions]
    return {
        "avg_score": round(sum(scores) / len(scores), 2),
        "pct_justify_style": round(_pct_justify_style(questions), 2),
        "pct_multi_step": round(_pct_multi_step(questions), 2),
        "scores": scores,
    }


def difficulty_fidelity_check(
    questions: List[Dict[str, Any]],
    target_difficulty: Optional[str] = None,
    difficulty_mix: Optional[Dict[str, float]] = None,
) -> Tuple[bool, str]:
    """
    Validate that worksheet difficulty matches request.
    target_difficulty: "easy" | "medium" | "hard" (single level)
    difficulty_mix: e.g. {"easy": 0.3, "medium": 0.5, "hard": 0.2}

    Returns (passed, report_string).
    If neither target_difficulty nor meaningful difficulty_mix is set, returns (True, "No difficulty constraint.").
    """
    if not questions:
        return False, "No questions to validate."

    # No difficulty constraint: pass
    has_single = target_difficulty in ("easy", "medium", "hard")
    mix = difficulty_mix or {}
    hard_pct = mix.get("hard") or 0.0
    easy_pct = mix.get("easy") or 0.0
    if not has_single and hard_pct < 0.2 and easy_pct < 0.5:
        # Effectively "mixed" with no strong easy/hard requirement
        return True, "No strict difficulty constraint."

    stats = get_worksheet_difficulty_stats(questions)
    avg = stats["avg_score"]
    pct_justify = stats["pct_justify_style"]
    pct_multi = stats["pct_multi_step"]

    # Single target difficulty
    if has_single:
        if target_difficulty == "easy":
            # Easy: low avg, <10% justify/prove style
            if pct_justify > 0.10:
                return False, f"Easy worksheet: too many justify/prove style questions ({pct_justify:.0%}); require <10%."
            if avg > 1.2:
                return False, f"Easy worksheet: average complexity too high ({avg:.2f}); require low (e.g. ≤1.2)."
            return True, f"Easy: avg={avg:.2f}, justify%={pct_justify:.0%}."

        if target_difficulty == "medium":
            # Medium: moderate avg, at least 20% multi-step (slightly more lenient to avoid excessive retries)
            if pct_multi < 0.20:
                return False, f"Medium worksheet: multi-step share too low ({pct_multi:.0%}); require ≥20%."
            if avg < 0.3:
                return False, f"Medium worksheet: average complexity too low ({avg:.2f}); require moderate."
            if avg > 2.5:
                return False, f"Medium worksheet: average complexity too high ({avg:.2f}); require moderate."
            return True, f"Medium: avg={avg:.2f}, multi_step%={pct_multi:.0%}."

        if target_difficulty == "hard":
            # Hard: high avg, ≥40% multi-step or justification
            higher_order_pct = max(pct_justify, pct_multi)
            if higher_order_pct < 0.35:
                return False, f"Hard worksheet: multi-step/justify share too low ({higher_order_pct:.0%}); require ≥35%."
            if avg < 1.0:
                return False, f"Hard worksheet: average complexity too low ({avg:.2f}); require high."
            return True, f"Hard: avg={avg:.2f}, higher_order%={higher_order_pct:.0%}."

    # Difficulty mix: require ordering easy < medium < hard by average score when we have distinct requests
    # For mix we only enforce soft checks: hard-heavy mix should have higher avg than easy-heavy
    if hard_pct >= 0.4 and avg < 1.0:
        return False, f"Mix (hard≥40%): average complexity too low ({avg:.2f}); require higher."
    if easy_pct >= 0.5 and pct_justify > 0.15:
        return False, f"Mix (easy≥50%): too many justify/prove style ({pct_justify:.0%})."
    return True, f"Mix: avg={avg:.2f}, justify%={pct_justify:.0%}, multi%={pct_multi:.0%}."
