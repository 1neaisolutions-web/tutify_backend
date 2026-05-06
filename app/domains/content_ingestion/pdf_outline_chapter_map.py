"""
Derive a table-of-contents style chapter_map from PDF bookmarks / outline.

Board-agnostic: many curriculum PDFs embed an outline (even when the body is
scanned). When the uploader does not supply chapter_map JSON, we can still
chunk with meaningful topic_title values for quiz / catalog topic strands.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from app.core.logging import get_logger
from app.domains.content_ingestion.topic_label_normalize import normalize_topic_label

logger = get_logger(__name__)


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
