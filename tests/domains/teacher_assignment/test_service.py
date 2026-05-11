"""
Unit tests for teacher_assignment service in app/domains/teacher_assignment/service.py.
"""
import uuid
from unittest.mock import MagicMock

import pytest

from app.domains.teacher_assignment.service import TeacherAssignmentService
from app.domains.teacher_assignment.errors import AssignmentError
from app.domains.teacher_assignment.models import TeacherAssignment


def _make_user():
    user = MagicMock()
    user.id = uuid.uuid4()
    user.tenant_id = uuid.uuid4()
    return user


def _make_assignment():
    a = MagicMock(spec=TeacherAssignment)
    a.id = uuid.uuid4()
    a.title = "Homework 1"
    a.subject = "Math"
    a.grade = "Grade 5"
    a.status = "draft"
    a.questions = []
    a.content_version = 1
    a.scope_topics = []
    a.source_pack_ids = []
    a.generate_without_sources = True
    return a


def _make_svc():
    db = MagicMock()
    svc = TeacherAssignmentService(db)
    svc.repo = MagicMock()
    svc.retrieval = MagicMock()
    svc.generator = MagicMock()
    return svc


class TestGetAssignment:
    def test_returns_assignment_when_found(self):
        user = _make_user()
        assignment = _make_assignment()
        svc = _make_svc()
        svc.repo.get_assignment.return_value = assignment

        result = svc.get_assignment(current_user=user, assignment_id=assignment.id)
        assert result is assignment

    def test_raises_not_found_when_missing(self):
        user = _make_user()
        svc = _make_svc()
        svc.repo.get_assignment.return_value = None

        with pytest.raises(AssignmentError) as exc_info:
            svc.get_assignment(current_user=user, assignment_id=uuid.uuid4())
        assert exc_info.value.http_status == 404


class TestCreateAssignment:
    def test_creates_and_returns_assignment(self):
        user = _make_user()
        assignment = _make_assignment()
        svc = _make_svc()
        svc.repo.create_assignment.return_value = assignment

        payload = {"title": "Homework 1", "subject": "Math", "grade": "Grade 5"}
        result = svc.create_assignment(current_user=user, payload=payload)

        svc.repo.create_assignment.assert_called_once()
        assert result is assignment

    def test_default_status_is_draft(self):
        user = _make_user()
        svc = _make_svc()
        captured = {}

        def capture(a):
            captured["a"] = a
            return a

        svc.repo.create_assignment.side_effect = capture
        svc.create_assignment(
            current_user=user,
            payload={"title": "T", "subject": "S", "grade": "G"},
        )
        assert captured["a"].status == "draft"


class TestDeleteAssignment:
    def test_delete_calls_repo(self):
        user = _make_user()
        assignment = _make_assignment()
        svc = _make_svc()
        svc.repo.get_assignment.return_value = assignment

        svc.delete_assignment(current_user=user, assignment_id=assignment.id)
        svc.repo.delete_assignment.assert_called_once_with(assignment)

    def test_delete_not_found_raises(self):
        user = _make_user()
        svc = _make_svc()
        svc.repo.get_assignment.return_value = None

        with pytest.raises(AssignmentError) as exc_info:
            svc.delete_assignment(current_user=user, assignment_id=uuid.uuid4())
        assert exc_info.value.http_status == 404


class TestPatchAssignment:
    def test_patch_updates_title(self):
        user = _make_user()
        assignment = _make_assignment()
        svc = _make_svc()
        svc.repo.get_assignment.return_value = assignment
        svc.repo.update_assignment.return_value = assignment

        svc.patch_assignment(
            current_user=user,
            assignment_id=assignment.id,
            patch={"title": "Updated HW"},
        )
        assert assignment.title == "Updated HW"

    def test_patch_not_found_raises(self):
        user = _make_user()
        svc = _make_svc()
        svc.repo.get_assignment.return_value = None

        with pytest.raises(AssignmentError) as exc_info:
            svc.patch_assignment(
                current_user=user, assignment_id=uuid.uuid4(), patch={"title": "X"}
            )
        assert exc_info.value.http_status == 404


class TestDuplicateAssignment:
    def test_duplicate_creates_copy_with_suffix(self):
        user = _make_user()
        original = _make_assignment()
        original.title = "HW 1"
        copied = _make_assignment()
        copied.title = "HW 1 (copy)"

        svc = _make_svc()
        svc.repo.get_assignment.return_value = original
        svc.repo.duplicate_assignment.return_value = copied

        result = svc.duplicate_assignment(current_user=user, assignment_id=original.id)
        assert "(copy)" in svc.repo.duplicate_assignment.call_args.kwargs.get("new_title", "")
