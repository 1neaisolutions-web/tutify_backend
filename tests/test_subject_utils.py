import pytest

from app.domains.external_context.subject_utils import (
    resolve_subject_value,
    subject_label,
    subject_teacher_tools_label,
    subject_template_label,
    subjects_match,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Mathematics", "math"),
        ("math", "math"),
        ("English", "ela"),
        ("English Language Arts", "ela"),
        ("Biology", "biology"),
        ("Computer Science", "computer_science"),
        ("Science", "science"),
        (None, None),
        ("unknown_subject", None),
    ],
)
def test_resolve_subject_value(raw, expected):
    assert resolve_subject_value(raw) == expected


def test_subject_teacher_tools_label():
    assert subject_teacher_tools_label("math") == "Mathematics"
    assert subject_teacher_tools_label("ela") == "English"
    assert subject_teacher_tools_label("Mathematics") == "Mathematics"


def test_subject_template_label():
    assert subject_template_label("math") == "Math"
    assert subject_template_label("ela") == "English"
    assert subject_template_label("computer_science") == "Technology"


def test_subjects_match():
    assert subjects_match("math", "Mathematics") is True
    assert subjects_match("ela", "English") is True
    assert subjects_match("math", "Science") is False


def test_subject_label():
    assert subject_label("math") == "Mathematics"
    assert subject_label("unknown") == "unknown"
