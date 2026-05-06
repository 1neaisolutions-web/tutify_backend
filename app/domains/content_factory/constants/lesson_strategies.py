"""Lesson strategy registry and deterministic mix scaling helpers."""

from __future__ import annotations

from typing import Dict, List, Optional


STRATEGY_QUESTION_TYPE_TO_SCHEMA_STYLE = {
    "multiple_choice": "multiple_choice",
    "discussion_prompt": "discussion_prompt",
    "quick_check": "quick_check",
    "higher_order": "higher_order",
    "short_answer": "higher_order",
    "scenario_based": "higher_order",
    "reflection": "discussion_prompt",
    "vocabulary": "quick_check",
    "procedure": "quick_check",
    "safety": "quick_check",
    "prediction": "higher_order",
    "listening_comprehension": "quick_check",
}

STRATEGY_TYPE_INTENT_INSTRUCTIONS = {
    "short_answer": "Write concise constructed-response questions that require explanation, not simple recall.",
    "scenario_based": "Frame the question as a realistic scenario requiring application, judgment, or decision-making.",
    "reflection": "Use reflective prompts that invite personal connection, emotional awareness, or metacognitive thinking.",
    "vocabulary": "Focus on key terminology, word meaning, usage, or vocabulary recognition from the video context.",
    "procedure": "Check understanding of steps, sequence, method, or correct procedure.",
    "safety": "Check safety awareness, precautions, risks, or responsible action.",
    "prediction": "Ask students to predict outcomes and justify their reasoning.",
    "listening_comprehension": "Check comprehension of what was heard, inferred, or identified from the video/transcript.",
    "multiple_choice": "Use plausible distractors and one clearly correct answer.",
    "higher_order": "Require analysis, inference, justification, or transfer of learning.",
    "quick_check": "Use brief, objective checks with one_word, short_phrase, or true_false answers.",
    "discussion_prompt": "Invite open-ended classroom discussion with facilitation angles.",
}


LESSON_STRATEGIES = {
    "inquiry_launch": {
        "id": "inquiry_launch",
        "title": "Inquiry Launch",
        "teaching_mode": "Facilitated discovery",
        "description": "Curate short clips to launch your next project-based learning inquiry or case study.",
        "learning_objectives": [
            "activate prior knowledge",
            "encourage curiosity",
            "promote discussion",
        ],
        "base_question_mix": {
            "multiple_choice": 2,
            "short_answer": 2,
            "discussion_prompt": 2,
        },
        "generation_rules": [
            "first question must be a curiosity or prediction-based question",
            "include at least one why/how reasoning question",
            "include at least one open-ended discussion prompt",
        ],
        "instruction": "Design the quiz as an inquiry-based learning experience.",
        "recommended_quiz_type": "Open-ended + Discussion",
        "estimated_classroom_time": "20-25 minutes",
        "recommended_export_format": "Google Forms (discussion mode) or printed reflection sheet",
        "best_use_case": "Project-based learning launch, wonder walls, case study openers",
        "teacher_prompt": "\"What do you notice? What do you wonder? Where does this connect to your world?\"",
        "differentiation_note": "Provide sentence stems for ELL students. Offer visual anchor charts for concept support.",
    },
    "flipped_mini_lesson": {
        "id": "flipped_mini_lesson",
        "title": "Flipped Mini-lesson",
        "teaching_mode": "Asynchronous pre-learning",
        "description": "Assign explanatory videos for home viewing with instant comprehension checks when class starts.",
        "learning_objectives": [
            "check comprehension",
            "identify misconceptions",
            "reinforce key concepts",
        ],
        "base_question_mix": {
            "multiple_choice": 3,
            "quick_check": 2,
            "vocabulary": 1,
        },
        "generation_rules": [
            "focus on recall and concept clarity",
            "include at least one misconception-check question",
            "avoid overly open-ended questions",
        ],
        "instruction": "Design the quiz for a flipped classroom focusing on comprehension checks.",
        "recommended_quiz_type": "Multiple choice + Quick check",
        "estimated_classroom_time": "10-15 min (home) + 5 min in-class debrief",
        "recommended_export_format": "LMS embed (Google Classroom, Canvas) or QR code handout",
        "best_use_case": "Homework alternative, station rotation, flipped classroom model",
        "teacher_prompt": "\"Before class, watch the video and answer 3 questions. Bring your biggest question to discuss.\"",
        "differentiation_note": "Allow extended time for async viewers. Provide a vocabulary preview sheet.",
    },
    "career_spotlight": {
        "id": "career_spotlight",
        "title": "Career Spotlight",
        "teaching_mode": "Real-world connections",
        "description": "Highlight industry interviews and connect them to course standards with scenario-based questions.",
        "learning_objectives": [
            "connect learning to real-world careers",
            "encourage application of knowledge",
            "promote decision-making",
        ],
        "base_question_mix": {
            "scenario_based": 2,
            "higher_order": 2,
            "discussion_prompt": 2,
        },
        "generation_rules": [
            "frame questions using real-world scenarios",
            "include at least one decision-making question",
            "relate concepts to real-life professions",
        ],
        "instruction": "Design the quiz with real-world and career-oriented scenarios.",
        "recommended_quiz_type": "Scenario-based + Higher-order thinking",
        "estimated_classroom_time": "25-30 minutes",
        "recommended_export_format": "Printed career exploration worksheet or digital portfolio entry",
        "best_use_case": "Career & Technical Education, advisory, post-secondary readiness units",
        "teacher_prompt": "\"If you were in this person's role, what decision would you make? What skills would you need?\"",
        "differentiation_note": "Offer a career interest inventory alongside. Allow choice in response format (written or oral).",
    },
    "sel_morning_meeting": {
        "id": "sel_morning_meeting",
        "title": "SEL Morning Meeting",
        "teaching_mode": "Community building & reflection",
        "description": "Use calming or empathy-building clips to kick off advisory with reflection prompts.",
        "learning_objectives": [
            "encourage self-reflection",
            "build emotional awareness",
            "promote group discussion",
        ],
        "base_question_mix": {
            "reflection": 3,
            "discussion_prompt": 2,
            "quick_check": 1,
        },
        "generation_rules": [
            "prioritize reflection-based questions",
            "use open-ended emotional or personal prompts",
            "avoid overly technical or academic phrasing",
        ],
        "instruction": "Design the quiz as a reflective and discussion-based session.",
        "recommended_quiz_type": "Discussion prompt + Reflection journal",
        "estimated_classroom_time": "10-15 minutes",
        "recommended_export_format": "Printed reflection journal or anonymous digital exit ticket",
        "best_use_case": "Advisory periods, homeroom, beginning-of-unit relationship building",
        "teacher_prompt": "\"After watching, share one word that describes how the person in the video made you feel.\"",
        "differentiation_note": "Allow drawing or symbol responses. Provide sentence starters. Never require sharing aloud.",
    },
    "stem_lab_prep": {
        "id": "stem_lab_prep",
        "title": "STEM Lab Prep",
        "teaching_mode": "Procedural preview & safety briefing",
        "description": "Share lab demonstration videos before experiments to walk students through safety and setup.",
        "learning_objectives": [
            "prepare students for lab procedures",
            "reinforce safety awareness",
            "encourage prediction before experimentation",
        ],
        "base_question_mix": {
            "procedure": 2,
            "safety": 2,
            "prediction": 2,
        },
        "generation_rules": [
            "include step-based procedural questions",
            "include at least one safety-focused question",
            "include prediction before experiment execution",
        ],
        "instruction": "Design the quiz to prepare students for a lab session.",
        "recommended_quiz_type": "Quick check + Lab skills",
        "estimated_classroom_time": "12-18 minutes pre-lab",
        "recommended_export_format": "Printed lab guide with built-in quiz checkpoints",
        "best_use_case": "Science labs, engineering design challenges, maker space sessions",
        "teacher_prompt": "\"Identify two safety precautions shown in the video. What would you do differently?\"",
        "differentiation_note": "Pair students for lab roles based on quiz performance. Offer visual safety cards.",
    },
    "language_listening_center": {
        "id": "language_listening_center",
        "title": "Language Listening Center",
        "teaching_mode": "Listening comprehension & vocabulary acquisition",
        "description": "Supply authentic language videos with comprehension checks for multilingual classrooms.",
        "learning_objectives": [
            "build vocabulary",
            "improve listening comprehension",
            "reinforce language understanding",
        ],
        "base_question_mix": {
            "vocabulary": 2,
            "listening_comprehension": 2,
            "multiple_choice": 2,
        },
        "generation_rules": [
            "focus on vocabulary extraction from transcript",
            "include listening comprehension checks",
            "ensure language simplicity and clarity",
        ],
        "instruction": "Design the quiz to improve listening and vocabulary skills.",
        "recommended_quiz_type": "Vocabulary development + Multiple choice",
        "estimated_classroom_time": "15-20 minutes",
        "recommended_export_format": "Dual-language worksheet or digital vocabulary card set",
        "best_use_case": "ELL/ESL stations, world language classes, multilingual literacy blocks",
        "teacher_prompt": "\"Listen once for meaning, then again for vocabulary. Which word surprised you?\"",
        "differentiation_note": "Enable captions. Allow native language annotations. Pair with bilingual anchor text.",
    },
}


def get_strategy_by_id(strategy_id: str):
    return LESSON_STRATEGIES.get(strategy_id)


def map_strategy_mix_to_schema_styles(base_mix: Dict[str, int]) -> Dict[str, int]:
    mapped: Dict[str, int] = {}
    for strategy_type, count in base_mix.items():
        schema_style = STRATEGY_QUESTION_TYPE_TO_SCHEMA_STYLE.get(strategy_type)
        if not schema_style:
            continue
        mapped[schema_style] = mapped.get(schema_style, 0) + count
    return mapped


def build_strategy_intent_lines(base_mix: Dict[str, int]) -> List[str]:
    lines: List[str] = []
    for strategy_type in base_mix.keys():
        schema_style = STRATEGY_QUESTION_TYPE_TO_SCHEMA_STYLE.get(strategy_type)
        instruction = STRATEGY_TYPE_INTENT_INSTRUCTIONS.get(strategy_type)
        if schema_style and instruction:
            lines.append(
                f"- Original strategy type '{strategy_type}' must be generated as schema style '{schema_style}'. Intent: {instruction}"
            )
    return lines


def scale_question_mix(base_mix: Dict[str, int], total_questions: int) -> Dict[str, int]:
    total_base = sum(base_mix.values())
    scaled: Dict[str, int] = {}

    for key, value in base_mix.items():
        scaled[key] = round((value / total_base) * total_questions)

    diff = total_questions - sum(scaled.values())
    if diff != 0:
        last_key = list(scaled.keys())[-1]
        scaled[last_key] += diff

    return scaled

