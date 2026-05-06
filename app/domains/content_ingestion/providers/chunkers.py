"""
Chunker implementations.
Preserves [[MATH]]...[[/MATH]] blocks (no split inside).
"""
import hashlib
import re
from typing import List, Dict, Any, Optional, Tuple

import tiktoken

from app.core.logging import get_logger
from app.domains.content_ingestion.providers.base import Chunker, Chunk, PageText

logger = get_logger(__name__)

MATH_BLOCK_PATTERN = re.compile(r"\[\[MATH\]\](.*?)\[\[/MATH\]\]", re.DOTALL)


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
        chapter_map: Optional[List[Dict[str, Any]]]
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Assign topic_id and topic_title based on page number and chapter map.
        
        Args:
            page_no: Page number (1-indexed)
            chapter_map: List of chapter objects with start_page, end_page
            
        Returns:
            Tuple of (topic_id, topic_title) or (None, None)
        """
        if not chapter_map:
            return None, None
        
        for chapter in chapter_map:
            start_page = chapter.get("start_page_pdf", 0)
            end_page = chapter.get("end_page_pdf", 0)
            
            if start_page <= page_no <= end_page:
                topic_id = chapter.get("id")
                topic_title = chapter.get("title")
                return topic_id, topic_title
        
        return None, None
    
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
        
        logger.info(f"Chunking {len(pages)} pages (chunk_size={chunk_size_tokens}, overlap={overlap_tokens})")
        
        chunks = []
        current_chunk_text = ""
        current_chunk_tokens = 0
        current_chunk_pages = []
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
                    chunk_id = f"chunk_{chunk_counter:06d}"
                    topic_id, topic_title = self._assign_topic(
                        current_chunk_pages[0] if current_chunk_pages else page.page_no,
                        chapter_map
                    )
                    chunks.append(Chunk(
                        chunk_id=chunk_id,
                        text=current_chunk_text,
                        page_start=min(current_chunk_pages) if current_chunk_pages else page.page_no,
                        page_end=max(current_chunk_pages) if current_chunk_pages else page.page_no,
                        topic_id=topic_id,
                        topic_title=topic_title
                    ))
                    chunk_counter += 1
                    current_chunk_text = ""
                    current_chunk_tokens = 0
                    current_chunk_pages = []
                # Split by segments so we never split inside [[MATH]]...[[/MATH]]
                segments = _split_into_segments(page_text)
                for seg_text, is_math in segments:
                    seg_tokens = self._count_tokens(seg_text)
                    if is_math or seg_tokens <= chunk_size_tokens:
                        if current_chunk_tokens + seg_tokens > chunk_size_tokens and current_chunk_text:
                            chunk_id = f"chunk_{chunk_counter:06d}"
                            topic_id, topic_title = self._assign_topic(page.page_no, chapter_map)
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
                            topic_id, topic_title = self._assign_topic(page.page_no, chapter_map)
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
                        topic_id, topic_title = self._assign_topic(page.page_no, chapter_map)
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
                # Save current chunk
                chunk_id = f"chunk_{chunk_counter:06d}"
                chunk_hash = hashlib.sha256(current_chunk_text.encode()).hexdigest()
                topic_id, topic_title = self._assign_topic(
                    current_chunk_pages[0] if current_chunk_pages else page.page_no,
                    chapter_map
                )
                
                chunks.append(Chunk(
                    chunk_id=chunk_id,
                    text=current_chunk_text,
                    page_start=min(current_chunk_pages) if current_chunk_pages else page.page_no,
                    page_end=max(current_chunk_pages) if current_chunk_pages else page.page_no,
                    topic_id=topic_id,
                    topic_title=topic_title
                ))
                chunk_counter += 1
                
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
                else:
                    current_chunk_text = page_text
                    current_chunk_tokens = page_tokens
                    current_chunk_pages = [page.page_no]
            else:
                # Add page to current chunk
                if current_chunk_text:
                    current_chunk_text += "\n\n" + page_text
                else:
                    current_chunk_text = page_text
                current_chunk_tokens += page_tokens
                current_chunk_pages.append(page.page_no)
        
        # Add final chunk
        if current_chunk_text:
            chunk_id = f"chunk_{chunk_counter:06d}"
            topic_id, topic_title = self._assign_topic(
                current_chunk_pages[0] if current_chunk_pages else pages[-1].page_no,
                chapter_map
            )
            
            chunks.append(Chunk(
                chunk_id=chunk_id,
                text=current_chunk_text,
                page_start=min(current_chunk_pages) if current_chunk_pages else pages[-1].page_no,
                page_end=max(current_chunk_pages) if current_chunk_pages else pages[-1].page_no,
                topic_id=topic_id,
                topic_title=topic_title
            ))
        
        logger.info(f"Created {len(chunks)} chunks from {len(pages)} pages")
        return chunks
