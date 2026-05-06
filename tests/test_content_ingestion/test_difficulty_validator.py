"""
Regression tests for worksheet difficulty validator.
Ensures easy/medium/hard produce measurably different scores and
difficulty_fidelity_check enforces thresholds.
"""
import pytest

from app.domains.content_ingestion.services.difficulty_validator import (
    score_question,
    get_worksheet_difficulty_stats,
    difficulty_fidelity_check,
)


def _q(text: str, question_key: str = "question") -> dict:
    return {question_key: text}


class TestScoreQuestion:
    """score_question returns higher for harder-style questions."""

    def test_easy_single_step_low_score(self):
        q = _q("What is 2 + 3?")
        assert score_question(q) < 1.0

    def test_justify_style_increases_score(self):
        q = _q("Justify why the sum of angles in a triangle is 180 degrees.")
        assert score_question(q) >= 1.0

    def test_question_text_key(self):
        q = _q("Explain why x + 0 = x.", question_key="question_text")
        assert score_question(q) > 0.5

    def test_multi_step_phrases_increase_score(self):
        q = _q("First find the value of x. Then using that, find the area.")
        assert score_question(q) > score_question(_q("What is 2 + 3?"))

    def test_empty_text_zero(self):
        assert score_question(_q("")) == 0.0


class TestGetWorksheetDifficultyStats:
    """get_worksheet_difficulty_stats returns avg_score, pct_justify_style, pct_multi_step."""

    def test_empty_questions(self):
        stats = get_worksheet_difficulty_stats([])
        assert stats["avg_score"] == 0.0
        assert stats["pct_justify_style"] == 0.0
        assert stats["pct_multi_step"] == 0.0

    def test_easy_set_low_avg(self):
        questions = [
            _q("What is 3 + 5?"),
            _q("Identify the coefficient of x in 2x + 1."),
            _q("Simplify 2 + 2."),
        ]
        stats = get_worksheet_difficulty_stats(questions)
        assert stats["avg_score"] < 1.2
        assert len(stats["scores"]) == 3

    def test_hard_set_higher_avg(self):
        questions = [
            _q("Prove that the sum of two even numbers is even."),
            _q("Using the result from part (a), show that n^2 + n is even for all integers n."),
            _q("Compare and evaluate the two methods given in the text."),
        ]
        stats = get_worksheet_difficulty_stats(questions)
        assert stats["avg_score"] >= 1.0
        assert stats["pct_justify_style"] >= 0.3
        assert stats["pct_multi_step"] >= 0.3


class TestDifficultyFidelityCheck:
    """difficulty_fidelity_check enforces easy/medium/hard thresholds."""

    def test_no_constraint_passes(self):
        questions = [_q("Anything goes.") for _ in range(5)]
        passed, _ = difficulty_fidelity_check(questions, None, None)
        assert passed is True

    def test_easy_fails_when_too_many_justify(self):
        questions = [
            _q("Justify why A holds."),
            _q("Prove that B."),
            _q("Explain why C."),
            _q("What is 2+2?"),
            _q("What is 3+3?"),
        ]
        passed, report = difficulty_fidelity_check(questions, "easy", None)
        assert passed is False
        assert "justify" in report.lower() or "10%" in report

    def test_easy_passes_with_simple_questions(self):
        questions = [_q("What is 2 + 3?"), _q("Simplify 1 + 1.")] * 5
        passed, report = difficulty_fidelity_check(questions, "easy", None)
        assert passed is True

    def test_medium_requires_multi_step_share(self):
        # All single-step recall
        questions = [_q("What is 2 + 2?"), _q("What is 3 + 3?")] * 5
        passed, report = difficulty_fidelity_check(questions, "medium", None)
        assert passed is False

    def test_medium_passes_with_mixed(self):
        questions = [
            _q("First find x. Then find the area."),
            _q("Using the formula, calculate the value."),
            _q("What is 2 + 2?"),
        ] * 3
        passed, _ = difficulty_fidelity_check(questions, "medium", None)
        assert passed is True

    def test_hard_fails_when_too_easy(self):
        questions = [_q("What is 1+1?"), _q("What is 2+2?")] * 5
        passed, report = difficulty_fidelity_check(questions, "hard", None)
        assert passed is False

    def test_hard_passes_with_higher_order(self):
        questions = [
            _q("Prove that the following holds."),
            _q("Using part (a), show that the result is true."),
            _q("Compare the two methods and evaluate."),
            _q("Explain why this is true."),
            _q("Derive the formula."),
        ] * 2
        passed, _ = difficulty_fidelity_check(questions, "hard", None)
        assert passed is True


class TestDifficultyOrdering:
    """Same pack/topic: easy worksheet score < medium < hard (validator scores)."""

    def test_easy_medium_hard_ordering_by_avg_score(self):
        easy_qs = [
            _q("What is 2 + 3?"),
            _q("Identify the term."),
            _q("Simplify 1 + 1."),
        ] * 3
        medium_qs = [
            _q("First find x. Then using that, find the area."),
            _q("Using the given formula, calculate the value when a=2."),
            _q("What is 2 + 2?"),
        ] * 3
        hard_qs = [
            _q("Prove that the sum of two evens is even."),
            _q("Using part (a), show that n^2 + n is even."),
            _q("Compare and evaluate the two methods."),
        ] * 3
        easy_stats = get_worksheet_difficulty_stats(easy_qs)
        medium_stats = get_worksheet_difficulty_stats(medium_qs)
        hard_stats = get_worksheet_difficulty_stats(hard_qs)
        assert easy_stats["avg_score"] < medium_stats["avg_score"]
        assert medium_stats["avg_score"] < hard_stats["avg_score"]

    def test_easy_medium_hard_each_pass_own_level(self):
        easy_qs = [_q("What is 2+2?"), _q("Simplify 3+1.")] * 5
        medium_qs = [_q("First find x. Then find y."), _q("Using the formula, find the value.")] * 5
        hard_qs = [_q("Prove that P. Then show that Q."), _q("Compare and evaluate.")] * 5
        assert difficulty_fidelity_check(easy_qs, "easy", None)[0] is True
        assert difficulty_fidelity_check(medium_qs, "medium", None)[0] is True
        assert difficulty_fidelity_check(hard_qs, "hard", None)[0] is True
