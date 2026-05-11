"""
Unit tests for TeacherQuizService in app/domains/teacher_quiz/service.py.
Repository, retrieval, and generator are mocked so tests run without a DB.
"""
import uuid
from datetime import datetime, timezone
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domains.teacher_quiz.errors import QuizError
from app.domains.teacher_quiz.models import TeacherQuiz, TeacherQuizQuestion
from app.domains.teacher_quiz.service import TeacherQuizService, _compute_total_marks, _topic_summary


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

class TestTopicSummary:
    def test_single_topic(self):
        assert _topic_summary(["Algebra"], None) == "Algebra"

    def test_multiple_topics_joined_with_dot(self):
        result = _topic_summary(["Algebra", "Geometry"], None)
        assert result == "Algebra · Geometry"

    def test_refinement_appended(self):
        result = _topic_summary(["Algebra"], "focus on quadratics")
        assert "focus on quadratics" in result

    def test_empty_topics_returns_default(self):
        assert _topic_summary([], None) == "General scope"

    def test_blank_topics_skipped(self):
        result = _topic_summary(["", "  ", "Science"], None)
        assert result == "Science"


class TestComputeTotalMarks:
    def _q(self, points: float) -> TeacherQuizQuestion:
        q = MagicMock(spec=TeacherQuizQuestion)
        q.points = points
        return q

    def test_sums_all_question_points(self):
        questions = [self._q(1.0), self._q(2.5), self._q(1.5)]
        assert _compute_total_marks(questions) == 5.0

    def test_empty_list_returns_zero(self):
        assert _compute_total_marks([]) == 0.0

    def test_none_points_treated_as_zero(self):
        q = MagicMock(spec=TeacherQuizQuestion)
        q.points = None
        assert _compute_total_marks([q]) == 0.0


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_user():
    user = MagicMock()
    user.id = uuid.uuid4()
    user.tenant_id = uuid.uuid4()
    return user


def _make_quiz(with_questions=True):
    quiz = MagicMock(spec=TeacherQuiz)
    quiz.id = uuid.uuid4()
    quiz.title = "Sample Quiz"
    quiz.subject = "Math"
    quiz.grade = "Grade 7"
    quiz.questions = (
        [MagicMock(spec=TeacherQuizQuestion, prompt="Q1", points=1.0)] if with_questions else []
    )
    quiz.questions_count = len(quiz.questions)
    quiz.total_marks = 1.0
    quiz.content_version = 1
    quiz.scope_topics = ["Algebra"]
    quiz.scope_refinement = None
    quiz.source_pack_ids = []
    quiz.generate_without_sources = True
    quiz.topic_summary = "Algebra"
    quiz.teacher_notes = None
    quiz.difficulty = "medium"
    quiz.status = "draft"
    return quiz


def _make_svc(db=None):
    db = db or MagicMock()
    svc = TeacherQuizService(db)
    svc.repo = MagicMock()
    svc.retrieval = MagicMock()
    svc.generator = MagicMock()
    return svc


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

class TestGetQuiz:
    def test_returns_quiz_when_found(self):
        user = _make_user()
        quiz = _make_quiz()
        svc = _make_svc()
        svc.repo.get_quiz.return_value = quiz

        result = svc.get_quiz(current_user=user, quiz_id=quiz.id)
        assert result is quiz

    def test_raises_not_found_when_missing(self):
        user = _make_user()
        svc = _make_svc()
        svc.repo.get_quiz.return_value = None

        with pytest.raises(QuizError) as exc_info:
            svc.get_quiz(current_user=user, quiz_id=uuid.uuid4())
        assert exc_info.value.http_status == 404


class TestCreateQuiz:
    def test_creates_quiz_with_required_fields(self):
        user = _make_user()
        quiz = _make_quiz()
        svc = _make_svc()
        svc.repo.create_quiz.return_value = quiz

        payload = {
            "title": "Math Quiz",
            "subject": "Math",
            "grade": "Grade 7",
        }
        result = svc.create_quiz(current_user=user, payload=payload)

        svc.repo.create_quiz.assert_called_once()
        assert result is quiz

    def test_create_quiz_defaults_status_to_draft(self):
        user = _make_user()
        svc = _make_svc()
        captured = {}

        def capture(quiz):
            captured["quiz"] = quiz
            return quiz

        svc.repo.create_quiz.side_effect = capture
        svc.create_quiz(
            current_user=user,
            payload={"title": "T", "subject": "S", "grade": "G"},
        )
        assert captured["quiz"].status == "draft"

    def test_create_quiz_defaults_shuffle_questions_to_true(self):
        user = _make_user()
        svc = _make_svc()
        captured = {}

        def capture(quiz):
            captured["quiz"] = quiz
            return quiz

        svc.repo.create_quiz.side_effect = capture
        svc.create_quiz(
            current_user=user,
            payload={"title": "T", "subject": "S", "grade": "G"},
        )
        assert captured["quiz"].shuffle_questions is True


class TestPatchQuiz:
    def test_patch_updates_title(self):
        user = _make_user()
        quiz = _make_quiz()
        svc = _make_svc()
        svc.repo.get_quiz.return_value = quiz
        svc.repo.update_quiz.return_value = quiz

        result = svc.patch_quiz(current_user=user, quiz_id=quiz.id, patch={"title": "Updated Title"})
        assert quiz.title == "Updated Title"

    def test_patch_not_found_raises(self):
        user = _make_user()
        svc = _make_svc()
        svc.repo.get_quiz.return_value = None

        with pytest.raises(QuizError) as exc_info:
            svc.patch_quiz(current_user=user, quiz_id=uuid.uuid4(), patch={"title": "X"})
        assert exc_info.value.http_status == 404

    def test_patch_updates_topic_summary_when_scope_changes(self):
        user = _make_user()
        quiz = _make_quiz()
        quiz.scope_topics = ["Algebra"]
        quiz.scope_refinement = None
        svc = _make_svc()
        svc.repo.get_quiz.return_value = quiz
        svc.repo.update_quiz.return_value = quiz

        svc.patch_quiz(
            current_user=user,
            quiz_id=quiz.id,
            patch={"scopeTopics": ["Algebra", "Calculus"]},
        )
        assert "Calculus" in quiz.topic_summary


class TestDeleteQuiz:
    def test_delete_existing_quiz(self):
        user = _make_user()
        quiz = _make_quiz()
        svc = _make_svc()
        svc.repo.get_quiz.return_value = quiz

        svc.delete_quiz(current_user=user, quiz_id=quiz.id)
        svc.repo.delete_quiz.assert_called_once_with(quiz)

    def test_delete_not_found_raises(self):
        user = _make_user()
        svc = _make_svc()
        svc.repo.get_quiz.return_value = None

        with pytest.raises(QuizError) as exc_info:
            svc.delete_quiz(current_user=user, quiz_id=uuid.uuid4())
        assert exc_info.value.http_status == 404


class TestDuplicateQuiz:
    def test_duplicate_creates_copy_with_suffix(self):
        user = _make_user()
        quiz = _make_quiz()
        quiz.title = "Original"
        svc = _make_svc()
        svc.repo.get_quiz.return_value = quiz

        copied = _make_quiz()
        copied.title = "Original (copy)"
        svc.repo.duplicate_quiz.return_value = copied

        result = svc.duplicate_quiz(current_user=user, quiz_id=quiz.id)
        assert "(copy)" in svc.repo.duplicate_quiz.call_args.kwargs["new_title"]


# ---------------------------------------------------------------------------
# Question CRUD
# ---------------------------------------------------------------------------

class TestAddQuestion:
    def test_add_question_appends_to_quiz(self):
        user = _make_user()
        quiz = _make_quiz()
        svc = _make_svc()
        svc.repo.get_quiz.return_value = quiz
        svc.repo.add_question.return_value = quiz

        payload = {"type": "mcq", "prompt": "What is 2+2?", "points": 1.0}
        result = svc.add_question(current_user=user, quiz_id=quiz.id, payload=payload)

        svc.repo.add_question.assert_called_once()

    def test_add_question_quiz_not_found_raises(self):
        user = _make_user()
        svc = _make_svc()
        svc.repo.get_quiz.return_value = None

        with pytest.raises(QuizError) as exc_info:
            svc.add_question(current_user=user, quiz_id=uuid.uuid4(), payload={"type": "mcq", "prompt": "X"})
        assert exc_info.value.http_status == 404


class TestDeleteQuestion:
    def test_cannot_delete_last_question(self):
        user = _make_user()
        quiz = _make_quiz()
        quiz.questions = [MagicMock()]  # only 1 question
        question = quiz.questions[0]
        svc = _make_svc()
        svc.repo.get_quiz.return_value = quiz
        svc.repo.get_question.return_value = question

        with pytest.raises(QuizError) as exc_info:
            svc.delete_question(current_user=user, quiz_id=quiz.id, question_id=uuid.uuid4())
        assert exc_info.value.http_status == 422

    def test_delete_question_calls_repo(self):
        user = _make_user()
        quiz = _make_quiz()
        q1, q2 = MagicMock(), MagicMock()
        quiz.questions = [q1, q2]
        svc = _make_svc()
        svc.repo.get_quiz.return_value = quiz
        svc.repo.get_question.return_value = q1
        svc.repo.delete_question.return_value = quiz

        svc.delete_question(current_user=user, quiz_id=quiz.id, question_id=uuid.uuid4())
        svc.repo.delete_question.assert_called_once_with(quiz, q1)
