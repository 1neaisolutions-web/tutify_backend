"""
Unit tests for teacher_worksheet service in app/domains/teacher_worksheet/service.py.
"""
import uuid
from unittest.mock import MagicMock

import pytest

from app.domains.teacher_worksheet.service import TeacherWorksheetService
from app.domains.teacher_worksheet.errors import WorksheetError
from app.domains.teacher_worksheet.models import TeacherWorksheet


def _make_user():
    user = MagicMock()
    user.id = uuid.uuid4()
    user.tenant_id = uuid.uuid4()
    return user


def _make_worksheet():
    w = MagicMock(spec=TeacherWorksheet)
    w.id = uuid.uuid4()
    w.title = "Chapter 3 Worksheet"
    w.subject = "English"
    w.grade = "Grade 6"
    w.status = "draft"
    w.questions = []
    w.content_version = 1
    w.scope_topics = ["Reading"]
    w.source_pack_ids = []
    w.generate_without_sources = True
    return w


def _make_svc():
    db = MagicMock()
    svc = TeacherWorksheetService(db)
    svc.repo = MagicMock()
    svc.retrieval = MagicMock()
    svc.generator = MagicMock()
    return svc


class TestGetWorksheet:
    def test_returns_worksheet_when_found(self):
        user = _make_user()
        ws = _make_worksheet()
        svc = _make_svc()
        svc.repo.get_worksheet.return_value = ws

        result = svc.get_worksheet(current_user=user, worksheet_id=ws.id)
        assert result is ws

    def test_raises_not_found_when_missing(self):
        user = _make_user()
        svc = _make_svc()
        svc.repo.get_worksheet.return_value = None

        with pytest.raises(WorksheetError) as exc_info:
            svc.get_worksheet(current_user=user, worksheet_id=uuid.uuid4())
        assert exc_info.value.http_status == 404


class TestCreateWorksheet:
    def test_creates_and_returns_worksheet(self):
        user = _make_user()
        ws = _make_worksheet()
        svc = _make_svc()
        svc.repo.create_worksheet.return_value = ws

        result = svc.create_worksheet(
            current_user=user,
            payload={"title": "Chapter 3 WS", "subject": "English", "grade": "Grade 6"},
        )
        svc.repo.create_worksheet.assert_called_once()
        assert result is ws

    def test_default_status_is_draft(self):
        user = _make_user()
        svc = _make_svc()
        captured = {}

        def capture(w):
            captured["w"] = w
            return w

        svc.repo.create_worksheet.side_effect = capture
        svc.create_worksheet(
            current_user=user,
            payload={"title": "T", "subject": "S", "grade": "G"},
        )
        assert captured["w"].status == "draft"


class TestDeleteWorksheet:
    def test_delete_calls_repo(self):
        user = _make_user()
        ws = _make_worksheet()
        svc = _make_svc()
        svc.repo.get_worksheet.return_value = ws

        svc.delete_worksheet(current_user=user, worksheet_id=ws.id)
        svc.repo.delete_worksheet.assert_called_once_with(ws)

    def test_delete_not_found_raises(self):
        user = _make_user()
        svc = _make_svc()
        svc.repo.get_worksheet.return_value = None

        with pytest.raises(WorksheetError) as exc_info:
            svc.delete_worksheet(current_user=user, worksheet_id=uuid.uuid4())
        assert exc_info.value.http_status == 404


class TestPatchWorksheet:
    def test_patch_updates_field(self):
        user = _make_user()
        ws = _make_worksheet()
        svc = _make_svc()
        svc.repo.get_worksheet.return_value = ws
        svc.repo.update_worksheet.return_value = ws

        svc.patch_worksheet(
            current_user=user,
            worksheet_id=ws.id,
            patch={"title": "Updated WS"},
        )
        assert ws.title == "Updated WS"

    def test_patch_not_found_raises(self):
        user = _make_user()
        svc = _make_svc()
        svc.repo.get_worksheet.return_value = None

        with pytest.raises(WorksheetError) as exc_info:
            svc.patch_worksheet(
                current_user=user,
                worksheet_id=uuid.uuid4(),
                patch={"title": "X"},
            )
        assert exc_info.value.http_status == 404


class TestDuplicateWorksheet:
    def test_duplicate_creates_copy_with_suffix(self):
        user = _make_user()
        original = _make_worksheet()
        original.title = "WS 1"
        copied = _make_worksheet()
        copied.title = "WS 1 (copy)"

        svc = _make_svc()
        svc.repo.get_worksheet.return_value = original
        svc.repo.duplicate_worksheet.return_value = copied

        svc.duplicate_worksheet(current_user=user, worksheet_id=original.id)
        call_kwargs = svc.repo.duplicate_worksheet.call_args.kwargs
        assert "(copy)" in call_kwargs.get("new_title", "")
