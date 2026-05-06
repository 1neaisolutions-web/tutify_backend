"""
Worksheet generation prompt templates by difficulty.
- Base system prompt: use ONLY CONTEXT, citations required, strict JSON, no verbatim copying.
- EASY / MEDIUM / HARD: difficulty composition targets and rubric requirements.
"""
from typing import List, Optional


def get_base_system_prompt(
    topic_text: str,
    grade_instruction: str,
    allowed: List[str],
    forbidden: List[str],
    algebraic_rules: str = "",
) -> str:
    """Shared base system prompt: facts from CONTEXT only, citations, JSON only, no copying."""
    return f"""You are an international-standard assessment author and a strict JSON generator.

CRITICAL: You MUST generate questions strictly about the topic: "{topic_text}". Use ONLY the provided book excerpts. If excerpts do not contain the topic, do not invent content from other topics.

HARD RULES:
1) Output MUST be valid JSON only. No markdown, no explanations, no extra text.
2) Use ONLY the provided CONTEXT for facts. Do not use outside knowledge.
3) Do NOT copy or closely paraphrase sentences from the CONTEXT. Rephrase in your own words so questions are grounded in the same concepts but worded differently.
4) Do NOT write "Based on the content/passage/context…" and do NOT ask to explain a paragraph.
5) Create real assessment items ONLY on the topic "{topic_text}":
   - MCQ: 4 options (option text only, NO leading letters like A) or B) — the frontend will add A., B., C., D.).
   - Short: concise answer (rule statement or computed result).
   - Long: extended answer, more marks, marking by criteria.
6) {grade_instruction}
7) Return EXACTLY the requested number of questions (num_questions from INPUT). The "questions" array MUST have exactly that many items—no fewer, no more. Count is mandatory; do not stop short.
8) Every question MUST include at least one citation: {{chunk_id, document_id, page_range}}.
9) Answers must NOT be copied verbatim from context. They must be short and student-facing.
10) Keep answers concise. Maximum 2 short sentences per explanation.
11) Marking criteria must be short bullet points, max 2 lines. Do NOT write long paragraphs.
12) Provide a professional marking scheme with mark allocation + acceptable answers + common errors (keep brief).
11) Allowed concepts (use these from the excerpts): {", ".join(allowed) if allowed else "from context"}.
12) FORBIDDEN: Do NOT write questions about: {", ".join(forbidden) if forbidden else "unrelated topics"}.
{algebraic_rules}

Generate an international-level worksheet and marking scheme in JSON. Return ONLY the final JSON."""


def get_grade_level_english_rule() -> str:
    """Grade-level English rule: short sentences, no advanced vocabulary, international/neutral contexts."""
    return """
GRADE-LEVEL ENGLISH (mandatory):
- Keep sentences short and clear.
- Avoid advanced vocabulary; use language appropriate to the grade.
- Avoid idioms and region-specific contexts.
- Use neutral contexts (e.g. school clubs, surveys, sports, library).
- Write in international English.
"""


def get_difficulty_user_prompt_section(
    target_difficulty: Optional[str],
    mcq_count: int,
    short_count: int,
    long_count: int,
) -> str:
    """
    Difficulty-specific instruction block (hard constraints).
    EASY: mostly 1-step, definitions/basic application, no justification.
    MEDIUM: at least 25% multi-step; scenario→set notation/constraints; avoid definition-only.
    HARD: at least 35% multi-step or justify/explain; multi-constraint; always/sometimes/never + justification where appropriate.
    """
    if target_difficulty == "easy":
        return """
DIFFICULTY CONTRACT — EASY (non-negotiable):
- Mostly 1-step questions: definitions and basic application only.
- No justification, no "explain why", "prove", "show that", "derive", "compare", "evaluate".
- At most 10% of questions may ask for brief explanation; the rest must be straightforward recall or single-step apply.
- Use small numbers and simple structures.
"""
    if target_difficulty == "medium":
        return f"""
DIFFICULTY CONTRACT — MEDIUM (non-negotiable):
- At least 25% of questions MUST be multi-step (e.g. scenario → set notation / constraints, "first... then...", "using... find...").
- Include scenario-based or constraint-based questions; avoid a worksheet that is purely definition-only.
- Some justify/explain (e.g. "explain why", "give a reason") is allowed but not required for the minimum.
- Exactly {mcq_count} MCQ, {short_count} short, {long_count} long. Marks: MCQ=1, short=2 or 3, long=3 or 4 with criteria.
"""
    if target_difficulty == "hard":
        return f"""
DIFFICULTY CONTRACT — HARD (non-negotiable):
- At least 35% of questions MUST be multi-step OR justify/explain (e.g. "justify", "explain why", "show that", "derive").
- Include multi-constraint scenarios and "always/sometimes/never" + justification where appropriate for the topic.
- Synthesis across concepts; not recall-only. Points-based rubrics for long answers.
- Exactly {mcq_count} MCQ, {short_count} short, {long_count} long.
"""
    return f"""
DIFFICULTY: Mixed (~20% easy, ~60% medium, ~20% hard). Spread question complexity accordingly.
Exactly {mcq_count} MCQ, {short_count} short, {long_count} long.
"""


def get_board_grounded_system_prompt(
    board_curriculum: str,
    topic_text: str,
    grade: str,
    subject: str,
    grade_instruction: str,
    target_difficulty: Optional[str],
) -> str:
    """
    System prompt for BOARD_GROUNDED mode: no retrieval context.
    Uses board/curriculum, grade, subject, topic_text and difficulty contract.
    Citations are not required; return empty citations.
    """
    diff_note = f"Target difficulty: {target_difficulty}." if target_difficulty in ("easy", "medium", "hard") else "Difficulty: mixed."
    return f"""You are an international-standard assessment author and a strict JSON generator.

You MUST generate questions strictly about the topic: "{topic_text}".
Use the board/curriculum: {board_curriculum}. Grade: {grade}. Subject: {subject}.
No book excerpts are provided; generate from curriculum expectations for this board, grade, and subject.

HARD RULES:
1) Output MUST be valid JSON only. No markdown, no explanations, no extra text.
2) Questions must align with {board_curriculum} curriculum expectations for {grade} {subject}.
3) Do NOT copy from any specific passage; create original assessment items.
4) MCQ: exactly 4 options (option text only, NO leading letters A) or B)); frontend adds A., B., C., D.
5) {grade_instruction}
6) Return EXACTLY the requested number of questions. The "questions" array MUST have exactly that many items.
7) For BOARD_GROUNDED mode, use empty citations: "citations": [] for each question (no chunk_id/document_id required).
8) Answers must be short and student-facing. Keep answers concise. Maximum 2 short sentences per explanation.
9) Marking criteria must be short bullet points, max 2 lines. Do NOT write long paragraphs.
10) Provide a professional marking scheme with mark allocation (keep brief).
11) {diff_note}
12) Language: international English, grade-level appropriate, short sentences, no advanced vocabulary, neutral contexts (school clubs, surveys, sports, library).

Generate an international-level worksheet and marking scheme in JSON. Return ONLY the final JSON."""


def get_banned_questions_section(banned_question_texts: List[str]) -> str:
    """Section for regenerate: list of BANNED QUESTIONS the model must not repeat or closely paraphrase."""
    if not banned_question_texts:
        return ""
    lines = "\n".join(f"- {q[:500]}" for q in banned_question_texts[:30])  # cap to avoid token overflow
    return f"""
BANNED QUESTIONS — Do NOT generate questions that repeat or are near-duplicates of these. Create new questions on the same topic and difficulty instead:
{lines}
"""
