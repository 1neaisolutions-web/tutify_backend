"""Tests for chapter_map_validator."""
from app.domains.content_ingestion.chapter_map_validator import validate_chapter_map


def test_rejects_overlapping_sibling_ranges():
    result = validate_chapter_map(
        [
            {"id": "ch-1", "title": "Ch 1", "level": 1, "parent_id": None, "start_page_pdf": 1, "end_page_pdf": 10},
            {"id": "ch-2", "title": "Ch 2", "level": 1, "parent_id": None, "start_page_pdf": 8, "end_page_pdf": 20},
        ]
    )
    assert not result.ok
    assert any("Overlapping" in e for e in result.errors)


def test_accepts_valid_map():
    result = validate_chapter_map(
        [
            {"id": "ch-1", "title": "Ch 1", "level": 1, "parent_id": None, "start_page_pdf": 1, "end_page_pdf": 10},
            {"id": "ch-2", "title": "Ch 2", "level": 1, "parent_id": None, "start_page_pdf": 11, "end_page_pdf": 20},
        ],
        total_pages=25,
    )
    assert result.ok
