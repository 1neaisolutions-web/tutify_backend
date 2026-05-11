"""
Unit tests for TeacherExamService helpers and CRUD in app/domains/teacher_exam/service.py.
"""
import uuid
from unittest.mock import MagicMock

import pytest

from app.domains.teacher_exam.service import (
    TeacherExamService,
    _topic_summary,
    compute_total_marks_from_paper,
)
from app.domains.teacher_exam.errors import ExamError
from app.domains.teacher_exam.models import TeacherExam, TeacherExamQuestion


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

class TestTopicSummary:
    def test_single_topic(self):
        assert _topic_summary(["Genetics"], None) == "Genetics"

    def test_multiple_topics(self):
        result = _topic_summary(["Physics", "Chemistry"], None)
        assert "Physics" in result and "Chemistry" in result

    def test_refinement_included(self):
        result = _topic_summary(["Biology"], "focus on cells")
        assert "focus on cells" in result

    def test_empty_returns_default(self):
        assert _topic_summary([], None) == "General scope"


class TestComputeTotalMarksFromPaper:
    def test_mcq_only(self):
        paper = {"objCount": 10, "objMarksPer": 1.0}
        assert compute_total_marks_from_paper(paper) == 10.0

    def test_short_answer_all_rule(self):
        paper = {"shortCount": 5, "shortMarksPer": 2.0, "shortRule": "all"}
        assert compute_total_marks_from_paper(paper) == 10.0

    def test_short_answer_pick_n_rule(self):
        paper = {"shortCount": 5, "shortN": 3, "shortMarksPer": 2.0, "shortRule": "pickNM"}
        assert compute_total_marks_from_paper(paper) == 6.0

    def test_long_answer_pick_n_rule(self):
        paper = {"longCount": 4, "longN": 2, "longMarksPer": 5.0, "longRule": "pickNM"}
        assert compute_total_marks_from_paper(paper) == 10.0

    def test_combined_paper(self):
        paper = {
            "objCount": 10, "objMarksPer": 1.0,
            "shortCount": 5, "shortMarksPer": 2.0, "shortRule": "all",
            "longCount": 3, "longMarksPer": 5.0, "longRule": "all",
        }
        assert compute_total_marks_from_paper(paper) == 35.0

    def test_empty_paper_returns_zero(self):
        assert compute_total_marks_from_paper({}) == 0.0

    def test_none_paper_returns_zero(self):
        assert compute_total_marks_from_paper(None) == 0.0


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_user():
    user = MagicMock()
    user.id = uuid.uuid4()
    user.tenant_id = uuid.uuid4()
    return user


def _make_exam():
    exam = MagicMock(spec=TeacherExam)
    exam.id = uuid.uuid4()
    exam.title = "Midterm Exam"
    exam.subject = "Physics"
    exam.grade = "Grade 10"
    exam.questions = []
    exam.sections = []
    exam.scope_topics = ["Mechanics"]
    exam.scope_refinement = None
    exam.source_pack_ids = []
    exam.generate_without_sources = True
    exam.paper_config = {}
    exam.total_marks = 0.0
    exam.sections_count = 0
    exam.mcq_count = 0
    exam.short_count = 0
    exam.long_count = 0
    exam.content_version = 1
    exam.status = "draft"
    return exam


def _make_svc():
    db = MagicMock()
    svc = TeacherExamService(db)
    svc.repo = MagicMock()
    svc.retrieval = MagicMock()
    svc.generator = MagicMock()
    return svc


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

class TestGetExam:
    def test_returns_exam_when_found(self):
        user = _make_user()
        exam = _make_exam()
        svc = _make_svc()
        svc.repo.get_exam.return_value = exam

        result = svc.get_exam(current_user=user, exam_id=exam.id)
        assert result is exam

    def test_raises_not_found_when_missing(self):
        user = _make_user()
        svc = _make_svc()
        svc.repo.get_exam.return_value = None

        with pytest.raises(ExamError) as exc_info:
            svc.get_exam(current_user=user, exam_id=uuid.uuid4())
        assert exc_info.value.http_status == 404


class TestCreateExam:
    def test_creates_exam_and_delegates_to_repo(self):
        user = _make_user()
        exam = _make_exam()
        svc = _make_svc()
        svc.repo.create_exam.return_value = exam

        payload = {"title": "Midterm", "subject": "Physics", "grade": "Grade 10"}
        result = svc.create_exam(current_user=user, payload=payload)

        svc.repo.create_exam.assert_called_once()
        assert result is exam

    def test_default_status_is_draft(self):
        user = _make_user()
        captured = {}
        svc = _make_svc()

        def capture(exam):
            captured["exam"] = exam
            return exam

        svc.repo.create_exam.side_effect = capture
        svc.create_exam(
            current_user=user,
            payload={"title": "T", "subject": "S", "grade": "G"},
        )
        assert captured["exam"].status == "draft"


class TestDeleteExam:
    def test_delete_calls_repo(self):
        user = _make_user()
        exam = _make_exam()
        svc = _make_svc()
        svc.repo.get_exam.return_value = exam

        svc.delete_exam(current_user=user, exam_id=exam.id)
        svc.repo.delete_exam.assert_called_once_with(exam)

    def test_delete_not_found_raises(self):
        user = _make_user()
        svc = _make_svc()
        svc.repo.get_exam.return_value = None

        with pytest.raises(ExamError) as exc_info:
            svc.delete_exam(current_user=user, exam_id=uuid.uuid4())
        assert exc_info.value.http_status == 404


class TestRecalcCounts:
    def test_recalc_updates_section_and_question_counts(self):
        svc = _make_svc()
        exam = MagicMock(spec=TeacherExam)
        exam.sections = [MagicMock(), MagicMock()]

        q_mcq = MagicMock(spec=TeacherExamQuestion)
        q_mcq.question_type = "mcq"
        q_short = MagicMock(spec=TeacherExamQuestion)
        q_short.question_type = "short"
        q_long = MagicMock(spec=TeacherExamQuestion)
        q_long.question_type = "long"
        exam.questions = [q_mcq, q_short, q_long]
        exam.paper_config = {}

        svc._recalc_counts(exam)

        assert exam.sections_count == 2
        assert exam.mcq_count == 1
        assert exam.short_count == 1
        assert exam.long_count == 1
