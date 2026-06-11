"""Tests for strict quiz scope retrieval with page guard and sections."""
import uuid

import pytest

from app.core.config import settings
from app.domains.content_ingestion.document_topics_service import populate_document_topics
from app.domains.content_ingestion.enums import DocumentStatus
from app.domains.content_ingestion.models import Chunk, ContentPack, Document
from app.domains.content_ingestion.quiz_catalog_schemas import ScopePreviewRequest
from app.domains.content_ingestion.quiz_catalog_service import QuizCatalogService
from app.domains.content_ingestion.topic_scope import RetrievalScopeError
from app.domains.teacher_quiz.retrieval import QuizRetrievalService


def _seed_two_chapters(db):
    tenant_id = uuid.uuid4()
    pack = ContentPack(
        id=uuid.uuid4(),
        name="Physics",
        subject="Physics",
        grade="10",
        tenant_id=tenant_id,
        is_active=True,
    )
    db.add(pack)
    doc = Document(
        id=uuid.uuid4(),
        pack_id=pack.id,
        filename="physics.pdf",
        file_path="dummy",
        source_type="pdf",
        status=DocumentStatus.PUBLISHED.value,
        tenant_id=tenant_id,
        title="Physics Textbook",
        total_pages=30,
        chapter_map=[
            {
                "id": "ch-1",
                "title": "Chapter 1: Quantities",
                "level": 1,
                "parent_id": None,
                "start_page_pdf": 1,
                "end_page_pdf": 10,
            },
            {
                "id": "ch-2",
                "title": "Chapter 2: Kinematics",
                "level": 1,
                "parent_id": None,
                "start_page_pdf": 11,
                "end_page_pdf": 20,
            },
        ],
    )
    db.add(doc)
    db.flush()

    ch1 = Chunk(
        id=uuid.uuid4(),
        document_id=doc.id,
        chunk_id="c1",
        text="SI units content",
        page_start_pdf=1,
        page_end_pdf=2,
        topic_id="ch-1",
        topic_title="Chapter 1: Quantities",
    )
    ch2 = Chunk(
        id=uuid.uuid4(),
        document_id=doc.id,
        chunk_id="c2",
        text="Motion content",
        page_start_pdf=11,
        page_end_pdf=12,
        topic_id="ch-2",
        topic_title="Chapter 2: Kinematics",
    )
    db.add_all([ch1, ch2])
    db.commit()

    populate_document_topics(db, doc, replace_existing=True)
    db.commit()
    db.refresh(doc)
    return tenant_id, pack, doc


def _seed_cambridge_ch29_ch30(db):
    """Ch 29 (463-477) and Ch 30 (478-500) with mislabeled boundary chunk."""
    tenant_id = uuid.uuid4()
    pack = ContentPack(
        id=uuid.uuid4(),
        name="Cambridge Physics",
        subject="Physics",
        grade="12",
        tenant_id=tenant_id,
        is_active=True,
    )
    db.add(pack)
    doc = Document(
        id=uuid.uuid4(),
        pack_id=pack.id,
        filename="cambridge.pdf",
        file_path="dummy",
        source_type="pdf",
        status=DocumentStatus.PUBLISHED.value,
        tenant_id=tenant_id,
        title="Cambridge Physics",
        total_pages=500,
        chapter_map=[
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
        ],
    )
    db.add(doc)
    db.flush()

    chunks = [
        Chunk(
            id=uuid.uuid4(),
            document_id=doc.id,
            chunk_id="c29",
            text="Transformer step-up step-down turns ratio",
            page_start_pdf=470,
            page_end_pdf=470,
            topic_id="ch-30",
            topic_title="Chapter 30: Quantum physics",
        ),
        Chunk(
            id=uuid.uuid4(),
            document_id=doc.id,
            chunk_id="c30a",
            text="Photoelectric effect Planck constant",
            page_start_pdf=480,
            page_end_pdf=482,
            topic_id="ch-30-s30-1",
            topic_title="30.1 Photoelectric effect",
        ),
        Chunk(
            id=uuid.uuid4(),
            document_id=doc.id,
            chunk_id="c30b",
            text="de Broglie wavelength matter waves",
            page_start_pdf=492,
            page_end_pdf=494,
            topic_id="ch-30-s30-2",
            topic_title="30.2 Wave-particle duality",
        ),
    ]
    db.add_all(chunks)
    db.commit()
    populate_document_topics(db, doc, replace_existing=True)
    db.commit()
    db.refresh(doc)
    return tenant_id, pack, doc


def test_preview_matches_retrieval_chunk_count(db):
    tenant_id, pack, doc = _seed_two_chapters(db)
    ch2_id = next(t for t in doc.document_topics if t.topic_key == "ch-2").id

    catalog = QuizCatalogService(db)
    preview = catalog.get_scope_preview(
        tenant_id=tenant_id,
        req=ScopePreviewRequest(pack_ids=[pack.id], topic_ids=[ch2_id]),
    )

    retrieval = QuizRetrievalService(db)
    result = retrieval.retrieve(
        tenant_id=tenant_id,
        pack_ids=[pack.id],
        topics=[],
        scope_topic_ids=[ch2_id],
        refinement=None,
        max_chunks=30,
    )

    assert preview.estimated_segments == 1
    assert result.metadata["chunk_count"] == 1
    assert preview.estimated_segments == result.metadata["chunk_count"]


def test_zero_chunk_scope_raises(db):
    tenant_id, pack, doc = _seed_two_chapters(db)
    fake_topic = uuid.uuid4()
    retrieval = QuizRetrievalService(db)
    with pytest.raises(RetrievalScopeError):
        retrieval.retrieve(
            tenant_id=tenant_id,
            pack_ids=[pack.id],
            topics=[],
            scope_topic_ids=[fake_topic],
            refinement=None,
            max_chunks=10,
        )


def test_ch1_scope_excludes_ch2_content(db):
    tenant_id, pack, doc = _seed_two_chapters(db)
    ch1_id = next(t for t in doc.document_topics if t.topic_key == "ch-1").id
    retrieval = QuizRetrievalService(db)
    result = retrieval.retrieve(
        tenant_id=tenant_id,
        pack_ids=[pack.id],
        topics=[],
        scope_topic_ids=[ch1_id],
        refinement=None,
        max_chunks=10,
    )
    assert "Motion content" not in result.context_text
    assert "SI units" in result.context_text


def test_ch30_excludes_mislabeled_page_470(db, monkeypatch):
    monkeypatch.setattr(settings, "SCOPE_PAGE_RANGE_GUARD_ENABLED", True)
    tenant_id, pack, doc = _seed_cambridge_ch29_ch30(db)
    ch30_id = next(t for t in doc.document_topics if t.topic_key == "ch-30").id
    retrieval = QuizRetrievalService(db)
    result = retrieval.retrieve(
        tenant_id=tenant_id,
        pack_ids=[pack.id],
        topics=[],
        scope_topic_ids=[ch30_id],
        refinement=None,
        max_chunks=10,
        include_sub_topics=True,
    )
    assert "Transformer" not in result.context_text
    assert "Photoelectric" in result.context_text or "de Broglie" in result.context_text
    assert result.metadata.get("excluded_by_page_guard", 0) >= 1


def test_section_scope_excludes_sibling_section(db, monkeypatch):
    monkeypatch.setattr(settings, "SCOPE_PAGE_RANGE_GUARD_ENABLED", True)
    tenant_id, pack, doc = _seed_cambridge_ch29_ch30(db)
    s301_id = next(t for t in doc.document_topics if t.topic_key == "ch-30-s30-1").id
    retrieval = QuizRetrievalService(db)
    result = retrieval.retrieve(
        tenant_id=tenant_id,
        pack_ids=[pack.id],
        topics=[],
        scope_topic_ids=[s301_id],
        refinement=None,
        max_chunks=10,
        include_sub_topics=False,
    )
    assert "Photoelectric" in result.context_text
    assert "de Broglie" not in result.context_text


def test_chapter_scope_includes_all_sections(db, monkeypatch):
    monkeypatch.setattr(settings, "SCOPE_PAGE_RANGE_GUARD_ENABLED", True)
    tenant_id, pack, doc = _seed_cambridge_ch29_ch30(db)
    ch30_id = next(t for t in doc.document_topics if t.topic_key == "ch-30").id
    retrieval = QuizRetrievalService(db)
    result = retrieval.retrieve(
        tenant_id=tenant_id,
        pack_ids=[pack.id],
        topics=[],
        scope_topic_ids=[ch30_id],
        refinement=None,
        max_chunks=10,
        include_sub_topics=True,
    )
    assert result.metadata["chunk_count"] == 2
    assert "Photoelectric" in result.context_text
    assert "de Broglie" in result.context_text


def test_preview_matches_guarded_retrieval(db, monkeypatch):
    monkeypatch.setattr(settings, "SCOPE_PAGE_RANGE_GUARD_ENABLED", True)
    tenant_id, pack, doc = _seed_cambridge_ch29_ch30(db)
    ch30_id = next(t for t in doc.document_topics if t.topic_key == "ch-30").id
    catalog = QuizCatalogService(db)
    preview = catalog.get_scope_preview(
        tenant_id=tenant_id,
        req=ScopePreviewRequest(pack_ids=[pack.id], topic_ids=[ch30_id], include_sub_topics=True),
    )
    retrieval = QuizRetrievalService(db)
    result = retrieval.retrieve(
        tenant_id=tenant_id,
        pack_ids=[pack.id],
        topics=[],
        scope_topic_ids=[ch30_id],
        refinement=None,
        max_chunks=30,
        include_sub_topics=True,
    )
    assert preview.estimated_segments == result.metadata["chunk_count"]
