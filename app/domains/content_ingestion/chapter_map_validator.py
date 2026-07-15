"""
Server-side validation for manual chapter_map JSON on document upload.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass
class ChapterMapValidationResult:
    ok: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def _page_range(entry: Dict[str, Any]) -> tuple[int, int]:
    start = entry.get("start_page_pdf") or entry.get("start_page")
    end = entry.get("end_page_pdf") or entry.get("end_page")
    return int(start), int(end)


def validate_chapter_map(
    chapter_map: List[Dict[str, Any]],
    *,
    total_pages: Optional[int] = None,
) -> ChapterMapValidationResult:
    errors: List[str] = []
    warnings: List[str] = []

    if not chapter_map:
        return ChapterMapValidationResult(ok=True)

    seen_ids: Set[str] = set()
    id_set: Set[str] = set()
    for entry in chapter_map:
        cid = str(entry.get("id") or "")
        if cid:
            id_set.add(cid)

    for i, entry in enumerate(chapter_map):
        cid = str(entry.get("id") or f"row-{i}")
        if cid in seen_ids:
            errors.append(f"Duplicate id '{cid}' at entry {i + 1}.")
        seen_ids.add(cid)

        title = (entry.get("title") or "").strip()
        if not title:
            errors.append(f"Entry {i + 1} ({cid}): missing title.")

        try:
            start, end = _page_range(entry)
        except (TypeError, ValueError):
            errors.append(f"Entry {i + 1} ({cid}): invalid page numbers.")
            continue

        if start < 1 or end < 1:
            errors.append(f"Entry {i + 1} ({cid}): pages must be >= 1.")
        if end < start:
            errors.append(f"Entry {i + 1} ({cid}): end_page before start_page.")
        if total_pages and end > total_pages:
            errors.append(f"Entry {i + 1} ({cid}): end_page {end} exceeds PDF length {total_pages}.")

        parent_id = entry.get("parent_id")
        if parent_id is not None and str(parent_id) not in id_set:
            errors.append(f"Entry {i + 1} ({cid}): parent_id '{parent_id}' not found.")

    # Overlap check among siblings (same parent_key / level)
    by_parent: Dict[Optional[str], List[tuple[int, int, str]]] = {}
    for entry in chapter_map:
        cid = str(entry.get("id") or "")
        parent = str(entry.get("parent_id")) if entry.get("parent_id") else None
        try:
            start, end = _page_range(entry)
        except (TypeError, ValueError):
            continue
        by_parent.setdefault(parent, []).append((start, end, cid))

    for parent, ranges in by_parent.items():
        sorted_ranges = sorted(ranges, key=lambda x: x[0])
        for j in range(1, len(sorted_ranges)):
            prev_start, prev_end, prev_id = sorted_ranges[j - 1]
            cur_start, cur_end, cur_id = sorted_ranges[j]
            if cur_start <= prev_end:
                errors.append(
                    f"Overlapping pages: '{prev_id}' ({prev_start}-{prev_end}) "
                    f"and '{cur_id}' ({cur_start}-{cur_end}) under parent {parent!r}."
                )

    # Gap before first chapter
    level1 = [e for e in chapter_map if int(e.get("level") or 1) == 1]
    if level1:
        try:
            min_start = min(_page_range(e)[0] for e in level1)
            if min_start > 1:
                warnings.append(
                    f"Pages 1-{min_start - 1} are not covered by any chapter; "
                    "consider adding a front-matter entry."
                )
        except (TypeError, ValueError):
            pass

    return ChapterMapValidationResult(ok=len(errors) == 0, errors=errors, warnings=warnings)
