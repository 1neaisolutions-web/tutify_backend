"""
Anti-copy (no verbatim from pack) and dedupe (regenerate uniqueness) helpers for worksheet generation.
"""
import hashlib
import re
from typing import List, Set, Tuple

# Default n-gram size for overlap check
NGRAM_SIZE = 8


def _normalize_for_hash(text: str) -> str:
    """Normalize question text for hashing: lowercase, trim, collapse whitespace, remove punctuation."""
    if not text or not isinstance(text, str):
        return ""
    t = text.lower().strip()
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"[^\w\s]", "", t)  # remove punctuation
    return t.strip()


def normalize_question_text(text: str) -> str:
    """Normalize for display/storage; same as hash normalization."""
    return _normalize_for_hash(text)


def question_hash(text: str) -> str:
    """SHA256 hash of normalized question text (for dedupe storage)."""
    return hashlib.sha256(_normalize_for_hash(text).encode()).hexdigest()


def _tokenize(text: str) -> List[str]:
    """Split into words (alphanumeric tokens)."""
    n = _normalize_for_hash(text)
    return n.split() if n else []


def tokenize_question(text: str) -> List[str]:
    """Public: tokenize question text for similarity checks."""
    return _tokenize(text)


def _ngrams(tokens: List[str], n: int) -> Set[Tuple[str, ...]]:
    """Return set of n-gram tuples."""
    if len(tokens) < n:
        return set()
    return set(tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1))


def token_overlap_ratio(question_tokens: List[str], reference_tokens: List[str]) -> float:
    """
    Overlap ratio: |intersection| / |question_tokens|.
    If question is empty, return 0.
    """
    if not question_tokens:
        return 0.0
    qset = set(question_tokens)
    rset = set(reference_tokens)
    return len(qset & rset) / len(qset)


def max_token_overlap_ratio(question_text: str, corpus_segments: List[List[str]]) -> float:
    """
    Max overlap ratio between question and any segment in the corpus.
    Used for anti-copy: if > threshold, question is too close to pack text.
    """
    q_tokens = _tokenize(question_text)
    if not q_tokens:
        return 0.0
    max_ratio = 0.0
    for seg in corpus_segments:
        r = token_overlap_ratio(q_tokens, seg)
        if r > max_ratio:
            max_ratio = r
    return max_ratio


def jaccard_similarity(tokens_a: List[str], tokens_b: List[str]) -> float:
    """Jaccard similarity |A ∩ B| / |A ∪ B|. Returns 0 if both empty."""
    sa, sb = set(tokens_a), set(tokens_b)
    if not sa and not sb:
        return 0.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def build_corpus_from_context(context_text: str) -> List[List[str]]:
    """
    Build reference corpus from context: split by sentences or by fixed-length windows, then tokenize each.
    Returns list of token lists (each segment is a list of words).
    """
    if not context_text or not context_text.strip():
        return []
    # Split on sentence boundaries and newlines
    raw = context_text.replace("\n", " ").strip()
    segments = re.split(r"[.!?]\s+", raw)
    corpus = []
    for seg in segments:
        seg = seg.strip()
        if len(seg) < 10:
            continue
        tokens = _tokenize(seg)
        if len(tokens) >= 3:  # skip very short fragments
            corpus.append(tokens)
    # Also add sliding windows of ~50 tokens to catch mid-sentence copying
    all_tokens = _tokenize(context_text)
    window_size = 50
    for i in range(0, max(1, len(all_tokens) - window_size + 1), 20):
        window = all_tokens[i : i + window_size]
        if len(window) >= 10:
            corpus.append(window)
    return corpus


def is_copying_pack(
    question_text: str,
    corpus_segments: List[List[str]],
    threshold: float,
) -> bool:
    """True if question has token overlap above threshold with any corpus segment."""
    return max_token_overlap_ratio(question_text, corpus_segments) > threshold


def is_near_duplicate(
    question_tokens: List[str],
    existing_hashes: List[Tuple[str, List[str]]],  # (hash, token_list)
    similarity_threshold: float,
) -> bool:
    """
    True if question_tokens are sufficiently similar to any existing question (by Jaccard).
    existing_hashes: list of (hash_str, tokens) for previously seen questions.
    """
    for _h, tokens in existing_hashes:
        if jaccard_similarity(question_tokens, tokens) >= similarity_threshold:
            return True
    return False
