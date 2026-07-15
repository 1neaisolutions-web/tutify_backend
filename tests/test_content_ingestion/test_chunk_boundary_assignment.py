"""Tests for chunk boundary assignment and section extraction."""
from app.domains.content_ingestion.providers.chunkers import (
    SimpleChunker,
    _assign_topic_for_pages,
    _split_pages_at_topic_boundaries,
)
from app.domains.content_ingestion.providers.base import PageText
from app.domains.content_ingestion.section_heading_extractor import extract_sections_from_pages


CAMBRIDGE_CH30_MAP = [
    {
        "id": "ch-29",
        "title": "Chapter 29: Alternating currents",
        "level": 1,
        "parent_id": None,
        "start_page_pdf": 463,
        "end_page_pdf": 477,
    },
    {
        "id": "ch-30",
        "title": "Chapter 30: Quantum physics",
        "level": 1,
        "parent_id": None,
        "start_page_pdf": 478,
        "end_page_pdf": 500,
    },
    {
        "id": "ch-30-s30-1",
        "title": "30.1 Photoelectric effect",
        "level": 2,
        "parent_id": "ch-30",
        "start_page_pdf": 478,
        "end_page_pdf": 488,
    },
    {
        "id": "ch-30-s30-2",
        "title": "30.2 Wave-particle duality",
        "level": 2,
        "parent_id": "ch-30",
        "start_page_pdf": 489,
        "end_page_pdf": 500,
    },
]


def test_split_pages_at_chapter_boundary():
    groups = _split_pages_at_topic_boundaries([476, 477, 478], CAMBRIDGE_CH30_MAP, page_offset=0)
    assert len(groups) == 2
    assert groups[0] == [476, 477]
    assert groups[1] == [478]


def test_median_page_assigns_section():
    tid, title = _assign_topic_for_pages([478, 479, 480], CAMBRIDGE_CH30_MAP, page_offset=0)
    assert tid == "ch-30-s30-1"
    assert "Photoelectric" in (title or "")


def test_chunker_splits_at_boundary():
    chunker = SimpleChunker()
    pages = [
        PageText(page_no=476, text="End of alternating currents chapter.", char_count=40),
        PageText(page_no=477, text="More AC content on rectification.", char_count=35),
        PageText(page_no=478, text="30.1 Photoelectric effect introduction.", char_count=40),
        PageText(page_no=479, text="Planck constant and photons.", char_count=30),
    ]
    chunks = chunker.chunk(pages, chunk_size_tokens=500, overlap_tokens=0, chapter_map=CAMBRIDGE_CH30_MAP)
    topic_ids = {c.topic_id for c in chunks}
    assert "ch-29" in topic_ids or any(
        c.page_start and c.page_start <= 477 for c in chunks if c.topic_id == "ch-29"
    )
    assert any(c.topic_id == "ch-30-s30-1" for c in chunks)
    for c in chunks:
        if c.page_start is not None and c.page_end is not None:
            assert c.page_start <= c.page_end


def test_section_extractor_finds_headings():
    pages = [
        (478, "30.1 Photoelectric effect\nSome content here."),
        (485, "30.2 Wave-particle duality\nMore content."),
    ]
    ch30 = next(e for e in CAMBRIDGE_CH30_MAP if e["id"] == "ch-30")
    sections = extract_sections_from_pages(pages, ch30)
    assert len(sections) >= 1
    assert sections[0]["level"] == 2
    assert sections[0]["parent_id"] == "ch-30"
