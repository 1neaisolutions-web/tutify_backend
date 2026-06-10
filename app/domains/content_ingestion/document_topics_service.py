"""
Populate and maintain document_topics rows and chunks.topic_fk links.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domains.content_ingestion.models import Chunk, Document, DocumentTopic

logger = get_logger(__name__)


def _page_range(entry: Dict[str, Any]) -> Tuple[Optional[int], Optional[int]]:
    start = entry.get("start_page_pdf") or entry.get("start_page")
    end = entry.get("end_page_pdf") or entry.get("end_page")
    return (int(start) if start is not None else None, int(end) if end is not None else None)


def _parent_key(entry: Dict[str, Any], id_to_key: Dict[str, str]) -> Optional[str]:
    parent_id = entry.get("parent_id")
    if not parent_id:
        return None
    return id_to_key.get(str(parent_id))


@dataclass
class TopicAssignmentReport:
    total_chunks: int = 0
    chunks_assigned: int = 0
    chapters_with_zero_chunks: List[str] = field(default_factory=list)
    coverage: float = 0.0
    unmatched_topic_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_chunks": self.total_chunks,
            "chunks_assigned": self.chunks_assigned,
            "coverage": self.coverage,
            "chapters_with_zero_chunks": self.chapters_with_zero_chunks,
            "unmatched_topic_ids": self.unmatched_topic_ids,
        }


def populate_document_topics(
    db: Session,
    document: Document,
    *,
    replace_existing: bool = True,
) -> TopicAssignmentReport:
    """
    Build document_topics from chapter_map + chunk topic labels; link chunks.topic_fk.

    1. Insert rows from chapter_map (hierarchy preserved).
    2. Insert any chunk-only topic keys not in chapter_map.
    3. Update chunk_count, page ranges, and topic_fk on chunks.
    """
    report = TopicAssignmentReport()
    chunks: List[Chunk] = (
        db.query(Chunk)
        .filter(Chunk.document_id == document.id)
        .order_by(Chunk.page_start_pdf.nullsfirst(), Chunk.chunk_id)
        .all()
    )
    report.total_chunks = len(chunks)

    if replace_existing:
        db.query(Chunk).filter(Chunk.document_id == document.id).update(
            {Chunk.topic_fk: None}, synchronize_session=False
        )
        db.query(DocumentTopic).filter(DocumentTopic.document_id == document.id).delete(
            synchronize_session=False
        )
        db.flush()

    chapter_map: List[Dict[str, Any]] = list(document.chapter_map or [])
    id_to_key: Dict[str, str] = {}
    key_to_row: Dict[str, DocumentTopic] = {}

    for i, entry in enumerate(chapter_map):
        topic_key = str(entry.get("id") or entry.get("topic_key") or f"ch-{i + 1}")
        id_to_key[str(entry.get("id") or topic_key)] = topic_key
        start_page, end_page = _page_range(entry)
        row = DocumentTopic(
            id=uuid.uuid4(),
            document_id=document.id,
            topic_key=topic_key,
            parent_key=None,
            level=int(entry.get("level") or 1),
            display_title=str(entry.get("title") or entry.get("display_title") or topic_key)[:500],
            start_page_pdf=start_page,
            end_page_pdf=end_page,
            sort_order=i,
            chunk_count=0,
        )
        db.add(row)
        key_to_row[topic_key] = row

    db.flush()

    for entry in chapter_map:
        topic_key = id_to_key.get(str(entry.get("id") or entry.get("topic_key") or ""))
        if not topic_key or topic_key not in key_to_row:
            continue
        parent = _parent_key(entry, id_to_key)
        if parent:
            key_to_row[topic_key].parent_key = parent

    chunk_groups: Dict[str, List[Chunk]] = defaultdict(list)
    for ch in chunks:
        key = ch.topic_id or f"title:{ch.topic_title or 'unknown'}"
        chunk_groups[key].append(ch)

    for key, group in chunk_groups.items():
        if key in key_to_row:
            continue
        sample = group[0]
        topic_key = sample.topic_id or f"scope:unknown-{key[:40]}"
        if topic_key in key_to_row:
            continue
        pages = [c.page_start_pdf for c in group if c.page_start_pdf] + [
            c.page_end_pdf for c in group if c.page_end_pdf
        ]
        row = DocumentTopic(
            id=uuid.uuid4(),
            document_id=document.id,
            topic_key=topic_key,
            parent_key=None,
            level=1,
            display_title=(sample.topic_title or topic_key)[:500],
            start_page_pdf=min(pages) if pages else None,
            end_page_pdf=max(pages) if pages else None,
            sort_order=len(key_to_row),
            chunk_count=0,
        )
        db.add(row)
        key_to_row[topic_key] = row

    db.flush()

    title_to_keys: Dict[str, Set[str]] = defaultdict(set)
    for tk, row in key_to_row.items():
        title_to_keys[row.display_title.lower().strip()].add(tk)

    assigned = 0
    unmatched: Set[str] = set()
    for ch in chunks:
        fk: Optional[DocumentTopic] = None
        if ch.topic_id and ch.topic_id in key_to_row:
            fk = key_to_row[ch.topic_id]
        elif ch.topic_title:
            keys = title_to_keys.get(ch.topic_title.lower().strip(), set())
            if len(keys) == 1:
                fk = key_to_row[next(iter(keys))]
            elif ch.topic_id:
                for tk in keys:
                    if tk == ch.topic_id:
                        fk = key_to_row[tk]
                        break
        if fk:
            ch.topic_fk = fk.id
            assigned += 1
        elif ch.topic_id:
            unmatched.add(ch.topic_id)

    counts: Dict[uuid.UUID, int] = defaultdict(int)
    page_lo: Dict[uuid.UUID, int] = {}
    page_hi: Dict[uuid.UUID, int] = {}
    for ch in chunks:
        if not ch.topic_fk:
            continue
        counts[ch.topic_fk] += 1
        if ch.page_start_pdf is not None:
            page_lo[ch.topic_fk] = min(page_lo.get(ch.topic_fk, ch.page_start_pdf), ch.page_start_pdf)
        if ch.page_end_pdf is not None:
            page_hi[ch.topic_fk] = max(page_hi.get(ch.topic_fk, ch.page_end_pdf), ch.page_end_pdf)

    empty_chapters: List[str] = []
    for row in key_to_row.values():
        row.chunk_count = counts.get(row.id, 0)
        if row.id in page_lo:
            row.start_page_pdf = row.start_page_pdf or page_lo[row.id]
        if row.id in page_hi:
            row.end_page_pdf = row.end_page_pdf or page_hi[row.id]
        if row.chunk_count == 0 and not row.topic_key.startswith("scope:pages"):
            empty_chapters.append(row.display_title)

    report.chunks_assigned = assigned
    report.coverage = assigned / report.total_chunks if report.total_chunks else 0.0
    report.chapters_with_zero_chunks = empty_chapters
    report.unmatched_topic_ids = sorted(unmatched)

    meta = dict(document.processing_metadata or {})
    meta["topic_assignment_report"] = report.to_dict()
    document.processing_metadata = meta

    db.flush()
    return report


def resolve_topic_ids_with_descendants(
    db: Session,
    topic_ids: List[uuid.UUID],
    *,
    include_sub_topics: bool = True,
) -> List[uuid.UUID]:
    """Expand topic UUIDs to include child document_topics in the same document."""
    if not topic_ids:
        return []
    roots = (
        db.query(DocumentTopic)
        .filter(DocumentTopic.id.in_(topic_ids))
        .all()
    )
    resolved: Set[uuid.UUID] = {r.id for r in roots}
    if not include_sub_topics:
        return list(resolved)

    by_doc: Dict[uuid.UUID, List[DocumentTopic]] = defaultdict(list)
    for r in roots:
        by_doc[r.document_id].append(r)

    for doc_id, doc_roots in by_doc.items():
        parent_keys = {r.topic_key for r in doc_roots}
        if not parent_keys:
            continue
        children = (
            db.query(DocumentTopic)
            .filter(
                DocumentTopic.document_id == doc_id,
                DocumentTopic.parent_key.in_(list(parent_keys)),
            )
            .all()
        )
        for child in children:
            resolved.add(child.id)
            grandchildren = (
                db.query(DocumentTopic)
                .filter(
                    DocumentTopic.document_id == doc_id,
                    DocumentTopic.parent_key == child.topic_key,
                )
                .all()
            )
            for gc in grandchildren:
                resolved.add(gc.id)

    return list(resolved)
