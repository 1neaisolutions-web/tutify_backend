"""Tests for quiz catalog structure and scope preview."""
import uuid

from app.domains.content_ingestion.document_topics_service import populate_document_topics
from app.domains.content_ingestion.enums import DocumentStatus
from app.domains.content_ingestion.models import Chunk, ContentPack, Document
from app.domains.content_ingestion.quiz_catalog_schemas import CatalogListParams, ScopePreviewRequest
from app.domains.content_ingestion.quiz_catalog_service import QuizCatalogService


def _seed_pack(db, *, tenant_id, name, subject, grade, publish=True):
    """Lightweight pack + optional published document for catalog filter tests."""
    pack = ContentPack(
        id=uuid.uuid4(),
        name=name,
        subject=subject,
        grade=grade,
        tenant_id=tenant_id,
        is_active=True,
    )
    db.add(pack)
    if publish:
        doc = Document(
            id=uuid.uuid4(),
            pack_id=pack.id,
            filename=f"{name}.pdf",
            file_path="dummy",
            source_type="pdf",
            status=DocumentStatus.PUBLISHED.value,
            tenant_id=tenant_id,
            title=name,
        )
        db.add(doc)
    db.commit()
    db.refresh(pack)
    return pack


def _seed_catalog_packs(db):
    tenant_id = uuid.uuid4()
    math_g8 = _seed_pack(
        db,
        tenant_id=tenant_id,
        name="Heinemann Math 8",
        subject="Mathematics",
        grade="Grade 8",
    )
    math_band = _seed_pack(
        db,
        tenant_id=tenant_id,
        name="Middle School Math",
        subject="math",
        grade="6-8",
    )
    physics_g9 = _seed_pack(
        db,
        tenant_id=tenant_id,
        name="Physics 9",
        subject="Physics",
        grade="9",
    )
    blank_subject = _seed_pack(
        db,
        tenant_id=tenant_id,
        name="Untagged Book",
        subject=None,
        grade="8",
    )
    return tenant_id, math_g8, math_band, physics_g9, blank_subject


def test_catalog_filter_math_grade_8(db):
    tenant_id, math_g8, math_band, physics_g9, blank_subject = _seed_catalog_packs(db)
    service = QuizCatalogService(db)
    items, total, near = service.get_catalog(
        tenant_id=tenant_id,
        params=CatalogListParams(subject="math", grade="8", strict=True),
    )
    ids = {p.id for p in items}
    assert total == 2
    assert math_g8.id in ids
    assert math_band.id in ids
    assert physics_g9.id not in ids
    assert blank_subject.id not in ids
    assert near == []


def test_catalog_grade_band_6_8_matches_grade_8(db):
    tenant_id, _, math_band, _, _ = _seed_catalog_packs(db)
    service = QuizCatalogService(db)
    items, total, _ = service.get_catalog(
        tenant_id=tenant_id,
        params=CatalogListParams(subject="math", grade="8"),
    )
    assert total >= 1
    assert any(p.id == math_band.id for p in items)


def test_catalog_grade_9_excludes_grade_8(db):
    tenant_id, _, _, physics_g9, _ = _seed_catalog_packs(db)
    service = QuizCatalogService(db)
    items, total, _ = service.get_catalog(
        tenant_id=tenant_id,
        params=CatalogListParams(subject="physics", grade="8"),
    )
    assert physics_g9.id not in {p.id for p in items}


def test_catalog_subject_alias_maths(db):
    tenant_id, math_g8, _, _, _ = _seed_catalog_packs(db)
    service = QuizCatalogService(db)
    items, total, _ = service.get_catalog(
        tenant_id=tenant_id,
        params=CatalogListParams(subject="math", grade="8"),
    )
    assert math_g8.id in {p.id for p in items}
    assert total >= 1


def test_catalog_strict_false_returns_all(db):
    tenant_id, math_g8, _, physics_g9, blank_subject = _seed_catalog_packs(db)
    service = QuizCatalogService(db)
    items, total, _ = service.get_catalog(
        tenant_id=tenant_id,
        params=CatalogListParams(subject="math", grade="8", strict=False),
    )
    ids = {p.id for p in items}
    assert math_g8.id in ids
    assert physics_g9.id in ids
    assert blank_subject.id in ids
    assert total == 4


def test_catalog_upload_blank_subject_excluded_strict(db):
    tenant_id, _, _, _, blank_subject = _seed_catalog_packs(db)
    service = QuizCatalogService(db)
    items, total, _ = service.get_catalog(
        tenant_id=tenant_id,
        params=CatalogListParams(subject="math", grade="8", strict=True),
    )
    assert blank_subject.id not in {p.id for p in items}


def test_catalog_near_matches_same_subject(db):
    tenant_id = uuid.uuid4()
    _seed_pack(
        db,
        tenant_id=tenant_id,
        name="Physics G9",
        subject="Physics",
        grade="9",
    )
    _seed_pack(
        db,
        tenant_id=tenant_id,
        name="Cambridge Physics",
        subject="Physics",
        grade="AS & A Level",
    )
    service = QuizCatalogService(db)
    items, total, near = service.get_catalog(
        tenant_id=tenant_id,
        params=CatalogListParams(
            subject="physics",
            grade="8",
            strict=True,
            include_near_matches=True,
        ),
    )
    assert total == 0
    assert len(near) == 2
    assert {p.name for p in near} == {"Physics G9", "Cambridge Physics"}


def test_catalog_cambridge_matches_physics_g11(db):
    tenant_id = uuid.uuid4()
    cambridge = _seed_pack(
        db,
        tenant_id=tenant_id,
        name="Cambridge AS Physics",
        subject="Physics",
        grade="AS & A Level",
    )
    service = QuizCatalogService(db)
    items, total, _ = service.get_catalog(
        tenant_id=tenant_id,
        params=CatalogListParams(subject="physics", grade="11", strict=True),
    )
    assert total == 1
    assert items[0].id == cambridge.id


def test_catalog_cambridge_excluded_for_grade_8(db):
    tenant_id = uuid.uuid4()
    _seed_pack(
        db,
        tenant_id=tenant_id,
        name="Cambridge AS Physics",
        subject="Physics",
        grade="AS & A Level",
    )
    service = QuizCatalogService(db)
    items, total, _ = service.get_catalog(
        tenant_id=tenant_id,
        params=CatalogListParams(subject="physics", grade="8", strict=True),
    )
    assert total == 0


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


def _seed_hierarchical_sections(db):
    tenant_id = uuid.uuid4()
    pack = ContentPack(
        id=uuid.uuid4(),
        name="Bio",
        subject="Biology",
        grade="10",
        tenant_id=tenant_id,
        is_active=True,
    )
    db.add(pack)
    doc = Document(
        id=uuid.uuid4(),
        pack_id=pack.id,
        filename="bio.pdf",
        file_path="dummy",
        source_type="pdf",
        status=DocumentStatus.PUBLISHED.value,
        tenant_id=tenant_id,
        title="Biology",
        chapter_map=[
            {
                "id": "ch-1",
                "title": "Chapter 1",
                "level": 1,
                "parent_id": None,
                "start_page_pdf": 1,
                "end_page_pdf": 20,
            },
            {
                "id": "ch-1-s1",
                "title": "1.1 Cells",
                "level": 2,
                "parent_id": "ch-1",
                "start_page_pdf": 1,
                "end_page_pdf": 10,
            },
            {
                "id": "ch-1-s2",
                "title": "1.2 Tissues",
                "level": 2,
                "parent_id": "ch-1",
                "start_page_pdf": 11,
                "end_page_pdf": 20,
            },
        ],
    )
    db.add(doc)
    db.flush()
    db.add_all(
        [
            Chunk(
                id=uuid.uuid4(),
                document_id=doc.id,
                chunk_id="s1",
                text="cell content",
                page_start_pdf=2,
                page_end_pdf=3,
                topic_id="ch-1-s1",
                topic_title="1.1 Cells",
            ),
            Chunk(
                id=uuid.uuid4(),
                document_id=doc.id,
                chunk_id="s2",
                text="tissue content",
                page_start_pdf=12,
                page_end_pdf=13,
                topic_id="ch-1-s2",
                topic_title="1.2 Tissues",
            ),
        ]
    )
    db.commit()
    populate_document_topics(db, doc, replace_existing=True)
    db.commit()
    db.refresh(doc)
    return tenant_id, pack, doc


def test_section_only_scope(db):
    tenant_id, pack, doc = _seed_hierarchical_sections(db)
    s1_id = next(t for t in doc.document_topics if t.topic_key == "ch-1-s1").id
    service = QuizCatalogService(db)
    resp = service.get_scope_preview(
        tenant_id=tenant_id,
        req=ScopePreviewRequest(
            pack_ids=[pack.id],
            topic_ids=[s1_id],
            include_sub_topics=False,
        ),
    )
    assert resp.estimated_segments == 1
    tree = service.get_catalog_structure(tenant_id=tenant_id, pack_ids=[pack.id])
    ch1 = tree.packs[0].documents[0].topic_tree[0]
    assert len(ch1.children) == 2
