"""
Chunker implementations.
Preserves [[MATH]]...[[/MATH]] blocks (no split inside).
"""
import hashlib
import re
from typing import List, Dict, Any, Optional, Tuple

import tiktoken

from app.core.logging import get_logger
from app.core.config import settings
from app.domains.content_ingestion.providers.base import Chunker, Chunk, PageText

logger = get_logger(__name__)

MATH_BLOCK_PATTERN = re.compile(r"\[\[MATH\]\](.*?)\[\[/MATH\]\]", re.DOTALL)
PAGE_PROXIMITY_THRESHOLD = 5

CHAPTER_HEADING_PATTERNS = [
    re.compile(r"^(chapter|unit|section|module|part|lesson)\s+\d+", re.I),
    re.compile(r"^(capítulo|unidad|sección)\s+\d+", re.I),
    re.compile(r"^(chapitre|unité|section)\s+\d+", re.I),
    re.compile(r"^(kapitel|einheit|abschnitt)\s+\d+", re.I),
]

TOC_LINE_PATTERNS = [
    re.compile(r"(.+?)\s*\.{2,}\s*(\d+)\s*$"),
    re.compile(r"(.+?)\s{3,}(\d+)\s*$"),
    re.compile(r"(.+?)\s+(\d+)\s*$"),
]


def _split_into_segments(text: str) -> List[Tuple[str, bool]]:
    """Split text into segments; each is (segment_text, is_math). Do not split inside [[MATH]]...[[/MATH]]."""
    segments = []
    pos = 0
    while True:
        m = MATH_BLOCK_PATTERN.search(text, pos)
        if not m:
            if pos < len(text):
                segments.append((text[pos:].strip(), False))
            break
        if m.start() > pos:
            segments.append((text[pos : m.start()].strip(), False))
        segments.append((m.group(0).strip(), True))
        pos = m.end()
    return [s for s in segments if s[0]]


class SimpleChunker(Chunker):
    """Simple token-based chunker with overlap."""
    
    provider_name = "simple"
    
    def __init__(self):
        """Initialize simple chunker."""
        try:
            # Use cl100k_base encoding (used by GPT models)
            self.encoding = tiktoken.get_encoding("cl100k_base")
        except Exception as e:
            logger.warning(f"tiktoken not available: {e}")
            self.encoding = None
    
    def _count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        if self.encoding:
            return len(self.encoding.encode(text))
        # Fallback: approximate 4 chars per token
        return len(text) // 4
    
    def _assign_topic(
        self,
        page_no: int,
        chapter_map: Optional[List[Dict[str, Any]]],
        page_offset: int = 0,
        page_numbers: Optional[List[int]] = None,
    ) -> tuple[Optional[str], Optional[str]]:
        pages = page_numbers if page_numbers else [page_no]
        return _assign_topic_for_pages(pages, chapter_map, page_offset)
    
    def _flush_segments(
        self,
        segments: List[Tuple[int, str]],
        chapter_map: Optional[List[Dict[str, Any]]],
        page_offset: int,
        chunk_counter: int,
    ) -> tuple[List[Chunk], int]:
        if not segments:
            return [], chunk_counter
        prefix = f"chunk_{chunk_counter:06d}"
        new_chunks = _segments_to_chunks(segments, chapter_map, page_offset, prefix)
        return new_chunks, chunk_counter + len(new_chunks)

    def _page_crosses_topic_boundary(
        self,
        page_no: int,
        current_pages: List[int],
        chapter_map: Optional[List[Dict[str, Any]]],
        page_offset: int,
    ) -> bool:
        if not chapter_map or not current_pages:
            return False
        prev_matches = _matching_entries(current_pages[-1], chapter_map, page_offset)
        new_matches = _matching_entries(page_no, chapter_map, page_offset)
        if not prev_matches or not new_matches:
            return False
        return str(prev_matches[0].get("id") or "") != str(new_matches[0].get("id") or "")
    
    def chunk(
        self,
        pages: List[PageText],
        chunk_size_tokens: int = 500,
        overlap_tokens: int = 50,
        chapter_map: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> List[Chunk]:
        """
        Chunk text from pages into smaller pieces.
        
        Args:
            pages: List of PageText objects
            chunk_size_tokens: Target chunk size in tokens
            overlap_tokens: Overlap between chunks in tokens
            chapter_map: Optional chapter map for topic assignment
            
        Returns:
            List of Chunk objects
        """
        if not pages:
            return []

        page_offset = 0
        if chapter_map:
            page_offset = _detect_page_offset(pages, chapter_map)
        
        logger.info(f"Chunking {len(pages)} pages (chunk_size={chunk_size_tokens}, overlap={overlap_tokens})")
        
        chunks = []
        current_chunk_text = ""
        current_chunk_tokens = 0
        current_chunk_pages: List[int] = []
        current_segments: List[Tuple[int, str]] = []
        chunk_counter = 0
        
        for page in pages:
            page_text = page.text.strip()
            if not page_text:
                continue
            
            page_tokens = self._count_tokens(page_text)
            
            # If single page exceeds chunk size, split by segments (preserve [[MATH]]...[[/MATH]])
            if page_tokens > chunk_size_tokens:
                # Save current chunk if any
                if current_chunk_text:
                    flushed, chunk_counter = self._flush_segments(
                        current_segments, chapter_map, page_offset, chunk_counter
                    )
                    chunks.extend(flushed)
                    current_chunk_text = ""
                    current_chunk_tokens = 0
                    current_chunk_pages = []
                    current_segments = []
                # Split by segments so we never split inside [[MATH]]...[[/MATH]]
                segments = _split_into_segments(page_text)
                for seg_text, is_math in segments:
                    seg_tokens = self._count_tokens(seg_text)
                    if is_math or seg_tokens <= chunk_size_tokens:
                        if current_chunk_tokens + seg_tokens > chunk_size_tokens and current_chunk_text:
                            chunk_id = f"chunk_{chunk_counter:06d}"
                            topic_id, topic_title = self._assign_topic(page.page_no, chapter_map, page_offset)
                            chunks.append(Chunk(chunk_id=chunk_id, text=current_chunk_text, page_start=page.page_no, page_end=page.page_no, topic_id=topic_id, topic_title=topic_title))
                            chunk_counter += 1
                            current_chunk_text = ""
                            current_chunk_tokens = 0
                        current_chunk_text = (current_chunk_text + "\n\n" + seg_text).strip() if current_chunk_text else seg_text
                        current_chunk_tokens += seg_tokens
                        current_chunk_pages = [page.page_no]
                        continue
                    # Non-math segment too large: split by words
                    words = seg_text.split()
                    current_words = []
                    current_word_tokens = 0
                    for word in words:
                        word_tokens = self._count_tokens(word + " ")
                        if current_word_tokens + word_tokens > chunk_size_tokens and current_words:
                            chunk_text = " ".join(current_words)
                            chunk_id = f"chunk_{chunk_counter:06d}"
                            topic_id, topic_title = self._assign_topic(page.page_no, chapter_map, page_offset)
                            chunks.append(Chunk(
                                chunk_id=chunk_id,
                                text=chunk_text,
                                page_start=page.page_no,
                                page_end=page.page_no,
                                topic_id=topic_id,
                                topic_title=topic_title
                            ))
                            chunk_counter += 1
                            overlap_size = min(overlap_tokens, current_word_tokens)
                            overlap_words = []
                            overlap_tokens_count = 0
                            for w in reversed(current_words):
                                w_tokens = self._count_tokens(w + " ")
                                if overlap_tokens_count + w_tokens <= overlap_size:
                                    overlap_words.insert(0, w)
                                    overlap_tokens_count += w_tokens
                                else:
                                    break
                            current_words = overlap_words + [word]
                            current_word_tokens = overlap_tokens_count + word_tokens
                        else:
                            current_words.append(word)
                            current_word_tokens += word_tokens
                    if current_words:
                        chunk_text = " ".join(current_words)
                        chunk_id = f"chunk_{chunk_counter:06d}"
                        topic_id, topic_title = self._assign_topic(page.page_no, chapter_map, page_offset)
                        chunks.append(Chunk(
                            chunk_id=chunk_id,
                            text=chunk_text,
                            page_start=page.page_no,
                            page_end=page.page_no,
                            topic_id=topic_id,
                            topic_title=topic_title
                        ))
                        chunk_counter += 1
                continue
            
            # Check if adding this page would exceed chunk size
            if current_chunk_tokens + page_tokens > chunk_size_tokens and current_chunk_text:
                flushed, chunk_counter = self._flush_segments(
                    current_segments, chapter_map, page_offset, chunk_counter
                )
                chunks.extend(flushed)
                chunk_counter += 0  # already updated in _flush_segments
                
                # Start new chunk with overlap
                overlap_size = min(overlap_tokens, current_chunk_tokens)
                if overlap_size > 0:
                    # Keep last N tokens as overlap
                    words = current_chunk_text.split()
                    overlap_words = []
                    overlap_tokens_count = 0
                    for word in reversed(words):
                        word_tokens = self._count_tokens(word + " ")
                        if overlap_tokens_count + word_tokens <= overlap_size:
                            overlap_words.insert(0, word)
                            overlap_tokens_count += word_tokens
                        else:
                            break
                    current_chunk_text = " ".join(overlap_words) + "\n\n" + page_text
                    current_chunk_tokens = overlap_tokens_count + page_tokens
                    current_chunk_pages = [page.page_no]
                    current_segments = [(page.page_no, page_text)]
                else:
                    current_chunk_text = page_text
                    current_chunk_tokens = page_tokens
                    current_chunk_pages = [page.page_no]
                    current_segments = [(page.page_no, page_text)]
            else:
                if self._page_crosses_topic_boundary(
                    page.page_no, current_chunk_pages, chapter_map, page_offset
                ) and current_chunk_text:
                    flushed, chunk_counter = self._flush_segments(
                        current_segments, chapter_map, page_offset, chunk_counter
                    )
                    chunks.extend(flushed)
                    current_chunk_text = ""
                    current_chunk_tokens = 0
                    current_chunk_pages = []
                    current_segments = []
                # Add page to current chunk
                if current_chunk_text:
                    current_chunk_text += "\n\n" + page_text
                else:
                    current_chunk_text = page_text
                current_chunk_tokens += page_tokens
                current_chunk_pages.append(page.page_no)
                current_segments.append((page.page_no, page_text))
        
        # Add final chunk
        if current_chunk_text:
            flushed, chunk_counter = self._flush_segments(
                current_segments, chapter_map, page_offset, chunk_counter
            )
            chunks.extend(flushed)
        
        logger.info(f"Created {len(chunks)} chunks from {len(pages)} pages")
        return chunks


def _split_pages_at_topic_boundaries(
    page_numbers: List[int],
    chapter_map: Optional[List[Dict[str, Any]]],
    page_offset: int = 0,
) -> List[List[int]]:
    """Split page list when deepest TOC topic id changes (chapter or section boundary)."""
    if not page_numbers:
        return []
    if not chapter_map or len(page_numbers) == 1:
        return [page_numbers]

    def _tid(pn: int) -> Optional[str]:
        matches = _matching_entries(pn, chapter_map, page_offset)
        if not matches:
            return None
        return str(matches[0].get("id") or "")

    groups: List[List[int]] = [[page_numbers[0]]]
    prev = _tid(page_numbers[0])
    for pn in page_numbers[1:]:
        cur = _tid(pn)
        if cur and prev and cur != prev:
            groups.append([pn])
            prev = cur
        else:
            groups[-1].append(pn)
            if cur:
                prev = cur
    return groups


def _segments_to_chunks(
    segments: List[Tuple[int, str]],
    chapter_map: Optional[List[Dict[str, Any]]],
    page_offset: int,
    chunk_id_prefix: str,
) -> List[Chunk]:
    """Build Chunk objects from (page_no, text) segments, splitting at topic boundaries."""
    if not segments:
        return []
    page_numbers = [s[0] for s in segments]
    page_text_map = {s[0]: s[1] for s in segments}
    out: List[Chunk] = []
    for i, group in enumerate(_split_pages_at_topic_boundaries(page_numbers, chapter_map, page_offset)):
        text = "\n\n".join(page_text_map[p] for p in group if page_text_map.get(p))
        if not text.strip():
            continue
        topic_id, topic_title = _assign_topic_for_pages(group, chapter_map, page_offset)
        out.append(
            Chunk(
                chunk_id=f"{chunk_id_prefix}_{i:03d}",
                text=text,
                page_start=min(group),
                page_end=max(group),
                topic_id=topic_id,
                topic_title=topic_title,
            )
        )
    return out


def _page_bounds(chapter: Dict[str, Any]) -> tuple[int, int]:
    start = chapter.get("start_page_pdf") or chapter.get("start_page") or 0
    end = chapter.get("end_page_pdf") or chapter.get("end_page") or 0
    return int(start), int(end)


def _find_nearest_chapter(page_no: int, chapter_map: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    nearest = None
    best_dist = None
    for chapter in chapter_map:
        start, _ = _page_bounds(chapter)
        dist = abs(page_no - start)
        if best_dist is None or dist < best_dist:
            best_dist = dist
            nearest = chapter
    return nearest


def _matching_entries(
    page_no: int,
    chapter_map: List[Dict[str, Any]],
    page_offset: int,
) -> List[Dict[str, Any]]:
    corrected = page_no + page_offset
    matches = []
    for chapter in chapter_map:
        start, end = _page_bounds(chapter)
        if start <= corrected <= end:
            matches.append(chapter)
    if not matches:
        return []
    max_level = max(int(c.get("level") or 1) for c in matches)
    deepest = [c for c in matches if int(c.get("level") or 1) == max_level]
    if len(deepest) == 1:
        return deepest
    # Narrowest page span wins at same level
    return [min(deepest, key=lambda c: _page_bounds(c)[1] - _page_bounds(c)[0])]


def _assign_topic_for_pages(
    page_numbers: List[int],
    chapter_map: Optional[List[Dict[str, Any]]],
    page_offset: int = 0,
) -> tuple[Optional[str], Optional[str]]:
    if not chapter_map or not page_numbers:
        return None, None
    sorted_pages = sorted(page_numbers)
    median_page = sorted_pages[len(sorted_pages) // 2]
    matches = _matching_entries(median_page, chapter_map, page_offset)
    if matches:
        entry = matches[0]
        cid = str(entry.get("id") or "")
        if cid:
            return cid, str(entry.get("title") or cid)

    if getattr(settings, "CHUNK_NEAREST_CHAPTER_FALLBACK", False):
        corrected = median_page + page_offset
        nearest = _find_nearest_chapter(corrected, chapter_map)
        if nearest:
            start, _ = _page_bounds(nearest)
            if abs(corrected - start) <= PAGE_PROXIMITY_THRESHOLD:
                return nearest.get("id"), nearest.get("title")
    return None, None


def _assign_topic_by_page_range(
    page_no: int,
    chapter_map: Optional[List[Dict[str, Any]]],
    page_offset: int = 0,
) -> tuple[Optional[str], Optional[str]]:
    return _assign_topic_for_pages([page_no], chapter_map, page_offset)


def _detect_page_offset(pages: List[PageText], chapter_map: List[Dict[str, Any]]) -> int:
    """Detect PDF page numbering offset using heading patterns on early pages."""
    if not pages or not chapter_map:
        return 0
    first_chapter = min(chapter_map, key=lambda c: _page_bounds(c)[0])
    start, _ = _page_bounds(first_chapter)
    title = (first_chapter.get("title") or "").lower()
    for page in pages[: min(20, len(pages))]:
        text_lower = (page.text or "").lower()
        if title and title[:20] in text_lower:
            return start - page.page_no
        for pat in CHAPTER_HEADING_PATTERNS:
            if pat.search(text_lower.split("\n", 1)[0].strip()):
                return start - page.page_no
    return 0


def validate_topic_assignment(
    chunks: List[Chunk],
    chapter_map: Optional[List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """Post-chunking report: coverage and chapters with zero assigned chunks."""
    total = len(chunks)
    assigned = sum(1 for c in chunks if c.topic_id)
    empty_chapters: List[str] = []
    if chapter_map:
        for ch in chapter_map:
            cid = ch.get("id")
            title = ch.get("title") or cid
            if cid and not any(c.topic_id == cid for c in chunks):
                if not str(cid).startswith("scope:pages"):
                    empty_chapters.append(str(title))
    coverage = assigned / total if total else 0.0
    return {
        "total_chunks": total,
        "chunks_assigned": assigned,
        "coverage": coverage,
        "chapters_with_zero_chunks": empty_chapters,
    }
