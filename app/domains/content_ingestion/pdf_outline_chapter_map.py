"""
Derive a table-of-contents style chapter_map from PDF bookmarks / outline.

Board-agnostic: many curriculum PDFs embed an outline (even when the body is
scanned). When the uploader does not supply chapter_map JSON, we can still
chunk with meaningful topic_title values for quiz / catalog topic strands.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple

from app.core.logging import get_logger
from app.domains.content_ingestion.topic_label_normalize import normalize_topic_label

logger = get_logger(__name__)

TOC_LINE_PATTERNS = [
    re.compile(r"(.+?)\s*\.{2,}\s*(\d+)\s*$"),
    re.compile(r"(.+?)\s{3,}(\d+)\s*$"),
    re.compile(r"(.+?)\s+(\d+)\s*$"),
]

CHAPTER_HEADING_PATTERNS = [
    re.compile(r"^(chapter|unit|section|module|part|lesson)\s+\d+", re.I),
    re.compile(r"^(capítulo|unidad|sección)\s+\d+", re.I),
    re.compile(r"^(chapitre|unité|section)\s+\d+", re.I),
    re.compile(r"^(kapitel|einheit|abschnitt)\s+\d+", re.I),
]


def _flatten_outline(nodes: Any) -> List[Any]:
    """pypdf outline trees are nested lists of Destination-like objects."""
    out: List[Any] = []
    if nodes is None:
        return out
    if not isinstance(nodes, list):
        return [nodes]
    for item in nodes:
        if isinstance(item, list):
            out.extend(_flatten_outline(item))
        else:
            out.append(item)
    return out


def _destination_page_one_based(reader: Any, dest: Any) -> Optional[int]:
    """Resolve bookmark destination to 1-based PDF page index."""
    try:
        if hasattr(reader, "get_destination_page_number"):
            idx = reader.get_destination_page_number(dest)
            if idx is None:
                return None
            return int(idx) + 1
    except Exception as e:
        logger.debug("get_destination_page_number failed: %s", e)
    try:
        # Older pypdf: page index on destination
        page0 = getattr(dest, "page", None)
        if page0 is None:
            return None
        if hasattr(page0, "indirect_reference") and page0.indirect_reference is not None:
            for i, p in enumerate(reader.pages):
                if getattr(p, "indirect_reference", None) == page0.indirect_reference:
                    return i + 1
        if isinstance(page0, int):
            return int(page0) + 1
    except Exception as e:
        logger.debug("fallback destination page resolve failed: %s", e)
    return None


def _outline_title(dest: Any) -> str:
    raw = getattr(dest, "title", None)
    if raw is None and isinstance(dest, dict):
        raw = dest.get("/Title")
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError:
            raw = raw.decode("utf-8", errors="replace")
    return normalize_topic_label(str(raw) if raw is not None else "", max_len=500)


def build_chapter_map_from_pdf_outline(
    file_path: str,
    total_pages: int,
    *,
    max_entries: int = 150,
    min_entries: int = 2,
) -> Optional[List[Dict[str, Any]]]:
    """
    Build chapter_map entries compatible with SimpleChunker (start_page_pdf / end_page_pdf).

    Returns None if the file is missing, not a PDF, has no outline, or outline is too sparse.
    """
    if not file_path or not os.path.isfile(file_path):
        return None
    if total_pages < 1:
        return None
    try:
        from pypdf import PdfReader
    except ImportError:
        return None

    try:
        reader = PdfReader(file_path)
    except Exception as e:
        logger.info("pdf_outline_reader_failed", extra={"path": file_path, "error": str(e)})
        return None

    try:
        outline = reader.outline
    except Exception:
        outline = None
    if not outline:
        return None

    flat = _flatten_outline(outline)
    raw_points: List[Tuple[int, str]] = []
    for dest in flat:
        title = _outline_title(dest)
        if len(title) < 2:
            continue
        page = _destination_page_one_based(reader, dest)
        if page is None or page < 1 or page > total_pages:
            continue
        raw_points.append((page, title[:500]))

    if len(raw_points) < min_entries:
        return None

    raw_points.sort(key=lambda x: (x[0], x[1]))
    deduped: List[Tuple[int, str]] = []
    seen: set = set()
    for page, title in raw_points:
        key = (page, title[:120])
        if key in seen:
            continue
        seen.add(key)
        deduped.append((page, title))
        if len(deduped) >= max_entries:
            break

    if len(deduped) < min_entries:
        return None

    chapters: List[Dict[str, Any]] = []
    for i, (start_page, title) in enumerate(deduped):
        if i + 1 < len(deduped):
            end_page = max(start_page, deduped[i + 1][0] - 1)
        else:
            end_page = total_pages
        end_page = min(max(end_page, start_page), total_pages)
        chapters.append(
            {
                "id": f"outline-{i + 1}",
                "title": title,
                "level": 1,
                "parent_id": None,
                "start_page_pdf": int(start_page),
                "end_page_pdf": int(end_page),
                "keywords": [],
            }
        )
    return chapters


def _parse_toc_page_text(pages_text: List[str], total_pages: int) -> Optional[List[Dict[str, Any]]]:
    """Parse TOC lines from first pages: 'Chapter 1 ..... 5'."""
    combined = "\n".join(pages_text[:15])
    if "contents" not in combined.lower() and "table of contents" not in combined.lower():
        if not any(p.search(combined[:2000]) for p in CHAPTER_HEADING_PATTERNS):
            pass
    entries: List[tuple[int, str]] = []
    for line in combined.splitlines():
        line = line.strip()
        if len(line) < 4:
            continue
        for pat in TOC_LINE_PATTERNS:
            m = pat.match(line)
            if m:
                title = m.group(1).strip().strip(".")
                page_num = int(m.group(2))
                if 1 <= page_num <= total_pages and len(title) >= 2:
                    entries.append((page_num, title[:500]))
                break
    if len(entries) < 2:
        return None
    entries.sort(key=lambda x: x[0])
    chapters: List[Dict[str, Any]] = []
    for i, (start_page, title) in enumerate(entries):
        end_page = entries[i + 1][0] - 1 if i + 1 < len(entries) else total_pages
        end_page = min(max(end_page, start_page), total_pages)
        chapters.append(
            {
                "id": f"toc-{i + 1}",
                "title": title,
                "level": 1,
                "parent_id": None,
                "start_page_pdf": start_page,
                "end_page_pdf": end_page,
                "keywords": [],
            }
        )
    return chapters


def _chapter_map_from_heading_heuristics(
    pages_text: List[tuple[int, str]],
    total_pages: int,
) -> Optional[List[Dict[str, Any]]]:
    """Detect chapter starts from heading patterns across page boundaries."""
    starts: List[tuple[int, str]] = []
    for page_no, text in pages_text:
        for line in (text or "").splitlines()[:8]:
            line = line.strip()
            if len(line) < 4:
                continue
            for pat in CHAPTER_HEADING_PATTERNS:
                if pat.match(line):
                    starts.append((page_no, line[:500]))
                    break
    if len(starts) < 2:
        return None
    starts.sort(key=lambda x: x[0])
    chapters: List[Dict[str, Any]] = []
    for i, (start_page, title) in enumerate(starts):
        end_page = starts[i + 1][0] - 1 if i + 1 < len(starts) else total_pages
        end_page = min(max(end_page, start_page), total_pages)
        chapters.append(
            {
                "id": f"heading-{i + 1}",
                "title": title,
                "level": 1,
                "parent_id": None,
                "start_page_pdf": start_page,
                "end_page_pdf": end_page,
                "keywords": [],
            }
        )
    return chapters


def extract_chapter_map(
    document: Any,
    pages: Optional[List[Any]] = None,
    *,
    file_path: Optional[str] = None,
    total_pages: int = 0,
) -> tuple[Optional[List[Dict[str, Any]]], str]:
    """
    Ranked TOC extraction strategies. Returns (chapter_map, toc_source).
    """
    if document.chapter_map and isinstance(document.chapter_map, list) and len(document.chapter_map) >= 1:
        return document.chapter_map, "client_json"

    path = file_path or getattr(document, "file_path", None)
    tp = total_pages or getattr(document, "total_pages", 0) or 0

    outline_map = build_chapter_map_from_pdf_outline(path, tp) if path and tp else None
    if outline_map:
        return outline_map, "pdf_outline_auto"

    page_texts: List[str] = []
    page_pairs: List[tuple[int, str]] = []
    if pages:
        for p in pages:
            text = getattr(p, "text", "") or ""
            page_texts.append(text)
            page_pairs.append((getattr(p, "page_no", 0), text))

    if page_texts and tp:
        toc_map = _parse_toc_page_text(page_texts, tp)
        if toc_map:
            return toc_map, "toc_page_text"

    if page_pairs and tp:
        heading_map = _chapter_map_from_heading_heuristics(page_pairs, tp)
        if heading_map:
            return heading_map, "heading_heuristics"

    return None, "none"
