"""
Extract section headings (N.M pattern) from page text within chapter ranges.
Optional helper for building level-2 chapter_map entries.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

SECTION_HEADING_RE = re.compile(
    r"^(?P<num>\d+\.\d+)\s+(?P<title>.{3,120})$",
    re.MULTILINE,
)


def extract_sections_from_pages(
    pages: List[Tuple[int, str]],
    chapter_entry: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Scan digital page text for numbered section headings within a chapter's page range.

    pages: list of (page_no, text)
    chapter_entry: level-1 chapter_map row with id, start_page_pdf, end_page_pdf
    """
    ch_id = str(chapter_entry.get("id") or "ch")
    ch_start = int(chapter_entry.get("start_page_pdf") or chapter_entry.get("start_page") or 1)
    ch_end = int(chapter_entry.get("end_page_pdf") or chapter_entry.get("end_page") or ch_start)

    hits: List[Tuple[int, str, str]] = []
    for page_no, text in pages:
        if page_no < ch_start or page_no > ch_end:
            continue
        for m in SECTION_HEADING_RE.finditer(text or ""):
            hits.append((page_no, m.group("num"), m.group("title").strip()))

    if not hits:
        return []

    sections: List[Dict[str, Any]] = []
    for i, (start_page, num, title) in enumerate(hits):
        end_page = ch_end
        if i + 1 < len(hits):
            end_page = max(start_page, hits[i + 1][0] - 1)
        sid = f"{ch_id}-s{num.replace('.', '-')}"
        sections.append(
            {
                "id": sid,
                "title": f"{num} {title}",
                "level": 2,
                "parent_id": ch_id,
                "start_page_pdf": start_page,
                "end_page_pdf": end_page,
                "keywords": [],
            }
        )
    return sections


def merge_sections_into_chapter_map(
    chapter_map: List[Dict[str, Any]],
    pages: List[Tuple[int, str]],
) -> List[Dict[str, Any]]:
    """Return chapter_map with auto-extracted sections appended after each level-1 chapter."""
    out = list(chapter_map)
    seen_ids: set[str] = {str(e.get("id") or "") for e in chapter_map if e.get("id")}
    for entry in chapter_map:
        if int(entry.get("level") or 1) != 1:
            continue
        for section in extract_sections_from_pages(pages, entry):
            sid = str(section.get("id") or "")
            if not sid:
                continue
            unique_sid = sid
            suffix = 1
            while unique_sid in seen_ids:
                unique_sid = f"{sid}-p{section.get('start_page_pdf', suffix)}"
                suffix += 1
            if unique_sid != sid:
                section = dict(section)
                section["id"] = unique_sid
            seen_ids.add(unique_sid)
            out.append(section)
    return out
