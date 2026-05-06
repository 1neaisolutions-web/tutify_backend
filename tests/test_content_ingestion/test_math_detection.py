from app.domains.content_ingestion.providers.math_providers import is_math_line, BaselineMathExtractionProvider
from app.domains.content_ingestion.providers.base import PageText


def test_math_line_detector_marks_math():
    assert is_math_line("x^2 + 2x + 1 = 0")
    assert is_math_line("sin(x) + cos(x)")
    assert not is_math_line("This is a normal sentence about math.")


def test_math_marker_injection():
    pt = PageText(page_no=1, text="x^2 + 1 = 0\nHello world", char_count=0)
    out = BaselineMathExtractionProvider.inject_markers_into_text(pt)
    assert "[[MATH]]" in out.text
    assert "[[/MATH]]" in out.text

