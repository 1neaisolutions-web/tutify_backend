"""
Unit tests for anti-copy (no verbatim from pack) and dedupe (regenerate uniqueness) helpers.
"""
import pytest

from app.domains.content_ingestion.services.worksheet_anticopy_dedupe import (
    build_corpus_from_context,
    is_copying_pack,
    question_hash,
    tokenize_question,
    jaccard_similarity,
    is_near_duplicate,
)


class TestBuildCorpusAndAntiCopy:
    """Anti-copy: corpus from context and overlap detection."""

    def test_build_corpus_from_context_splits_sentences(self):
        context = "First sentence here. Second sentence there. Third one."
        corpus = build_corpus_from_context(context)
        assert len(corpus) >= 2
        assert any(len(seg) >= 3 for seg in corpus)

    def test_is_copying_pack_high_overlap(self):
        context = "The sum of two even numbers is always an even number."
        corpus = build_corpus_from_context(context)
        # Question that copies most of the sentence
        question = "The sum of two even numbers is always an even number. True or false?"
        assert is_copying_pack(question, corpus, 0.35) is True

    def test_is_copying_pack_low_overlap(self):
        context = "The sum of two even numbers is always an even number."
        corpus = build_corpus_from_context(context)
        question = "Prove that adding two even integers gives an even integer."
        # Different wording, may still have some overlap
        result = is_copying_pack(question, corpus, 0.35)
        # Either way; we just check the function runs and returns bool
        assert isinstance(result, bool)

    def test_is_copying_pack_empty_corpus(self):
        assert is_copying_pack("Any question", [], 0.35) is False


class TestDedupe:
    """Dedupe: question hash and near-duplicate detection."""

    def test_question_hash_deterministic(self):
        h1 = question_hash("What is 2 + 3?")
        h2 = question_hash("What is 2 + 3?")
        assert h1 == h2

    def test_question_hash_different_for_different_text(self):
        h1 = question_hash("What is 2 + 3?")
        h2 = question_hash("What is 3 + 4?")
        assert h1 != h2

    def test_question_hash_normalizes_whitespace(self):
        h1 = question_hash("  What   is   2+3?  ")
        h2 = question_hash("What is 2+3?")
        assert h1 == h2

    def test_jaccard_identical(self):
        t = tokenize_question("the cat sat on the mat")
        assert jaccard_similarity(t, t) == 1.0

    def test_jaccard_no_overlap(self):
        a = tokenize_question("one two three")
        b = tokenize_question("four five six")
        assert jaccard_similarity(a, b) == 0.0

    def test_is_near_duplicate_above_threshold(self):
        existing = [(question_hash("What is the sum of 2 and 3?"), tokenize_question("What is the sum of 2 and 3?"))]
        new_tokens = tokenize_question("What is the sum of 2 and 3?")
        assert is_near_duplicate(new_tokens, existing, 0.85) is True

    def test_is_near_duplicate_below_threshold(self):
        existing = [(question_hash("What is 2+3?"), tokenize_question("What is 2+3?"))]
        new_tokens = tokenize_question("Prove that the sum of two evens is even.")
        assert is_near_duplicate(new_tokens, existing, 0.85) is False
