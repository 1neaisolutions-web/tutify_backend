"""Tests for quiz catalog structure and scope preview."""
import uuid

from app.domains.content_ingestion.document_topics_service import populate_document_topics
from app.domains.content_ingestion.enums import DocumentStatus
from app.domains.content_ingestion.models import Chunk, ContentPack, Document
from app.domains.content_ingestion.quiz_catalog_schemas import ScopePreviewRequest
from app.domains.content_ingestion.quiz_catalog_service import QuizCatalogService


def _seed_pack_with_topics(db):
    tenant_id = uuid.uuid4()
    pack = ContentPack(
        id=uuid.uuid4(),
        name="Physics Grade 9",
        subject="Physics",
        grade="9",
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


def test_get_catalog_structure_returns_hierarchical_tree(db):
    tenant_id, pack, doc = _seed_pack_with_topics(db)
    service = QuizCatalogService(db)
    resp = service.get_catalog_structure(tenant_id=tenant_id, pack_ids=[pack.id])
    assert len(resp.packs) == 1
    assert resp.packs[0].pack_name == "Physics Grade 9"
    assert len(resp.packs[0].documents) == 1
    tree = resp.packs[0].documents[0].topic_tree
    assert len(tree) == 2
    assert all(node.chunk_count > 0 for node in tree)


def test_scope_preview_with_topic_ids(db):
    tenant_id, pack, doc = _seed_pack_with_topics(db)
    topic_id = next(t for t in doc.document_topics if t.topic_key == "ch-2").id
    service = QuizCatalogService(db)
    resp = service.get_scope_preview(
        tenant_id=tenant_id,
        req=ScopePreviewRequest(pack_ids=[pack.id], topic_ids=[topic_id]),
    )
    assert resp.estimated_segments == 1
    assert resp.sources_count == 1
    assert len(resp.per_document) == 1
    assert resp.per_document[0].chunk_count == 1
