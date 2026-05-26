"""Tests for 504 plan markdown splitting and bullet normalization."""
from app.utils.markdown_converter import (
    finalize_plan_504_output,
    split_plan_504_combined_markdown,
    _bulletize_section_body,
)


def test_bulletize_paragraphs():
    body = "Provide fidgets.\n\nAllow headphones."
    out = _bulletize_section_body(body)
    assert out.startswith("- Provide fidgets.")
    assert "- Allow headphones." in out


def test_split_combined_markdown():
    combined = """## Present Levels of Performance

Student needs support.

## Accommodations

Provide fidgets. Allow headphones.

## Goals

Will stay on task 80% of the time. Will wait for turn.

## Monitoring and Review

Review quarterly."""
    split = split_plan_504_combined_markdown(combined)
    assert "present_levels_of_performance" in split
    assert split["accommodations"].startswith("- ")
    assert split["goals"].startswith("- ")


def test_finalize_legacy_plan_504_draft_field():
    legacy = {
        "plan_504_draft": """## Present Levels of Performance

Needs help.

## Accommodations

Item one. Item two.

## Goals

Goal one. Goal two.

## Monitoring and Review

Monitored monthly."""
    }
    out = finalize_plan_504_output(legacy)
    assert out.get("present_levels_of_performance")
    assert out["accommodations"].startswith("- ")
