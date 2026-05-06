import asyncio
import uuid

from app.domains.content_ingestion.models import Document, PageText as PageTextModel, Chunk as ChunkModel, ContentPack
from app.domains.content_ingestion.providers.base import PageText as BasePageText
from app.domains.content_ingestion.providers.chunkers import SimpleChunker
from app.domains.content_ingestion.providers.embedding_providers import FakeEmbeddingProvider
from app.domains.content_ingestion.providers.vector_stores import PgVectorStore
from app.domains.content_ingestion.services.qa_service import QAService


def test_free_mode_pipeline_persists_embedding_v_and_qa_passes(db, monkeypatch):
    # Create pack + document
    pack = ContentPack(
        id=uuid.uuid4(),
        name="Pack",
        tenant_id=uuid.uuid4(),
        is_active=True,
    )
    db.add(pack)
    db.commit()

    doc = Document(
        id=uuid.uuid4(),
        pack_id=pack.id,
        filename="x.pdf",
        file_path="dummy",
        source_type="pdf",
        status="uploaded",
        tenant_id=pack.tenant_id,
        processing_metadata={"content_type_hint": None},
        total_pages=1,
    )
    db.add(doc)
    db.commit()

    # Ensure QA text density passes (default min_chars_per_page=100)
    page_text = "x^2 + 1 = 0\\n" + ("hello " * 50)
    db.add(PageTextModel(document_id=doc.id, page_no=1, text=page_text, char_count=len(page_text)))
    db.commit()

    # Chunk
    chunker = SimpleChunker()
    chunks = chunker.chunk(
        [BasePageText(page_no=1, text="[[MATH]] x^2 + 1 = 0 [[/MATH]]\\n" + ("hello " * 50), char_count=0)],
        chunk_size_tokens=50,
        overlap_tokens=0,
    )

    # Embed + store
    emb = FakeEmbeddingProvider()
    vectors = asyncio.run(emb.embed([c.text for c in chunks]))
    store = PgVectorStore(db=db)
    asyncio.run(
        store.upsert(
            chunks=chunks,
            vectors=vectors,
            document_id=str(doc.id),
            pack_id=str(doc.pack_id),
            embedding_model=emb.provider_name,
            embedding_dim=emb.get_embedding_dimension(),
            embedding_provider=emb.provider_name,
        )
    )

    # Assert persisted
    count = db.query(ChunkModel).filter(ChunkModel.document_id == doc.id, ChunkModel.embedding_v.isnot(None)).count()
    assert count > 0

    # QA: monkeypatch vector search (SQLite won't support pgvector operators)
    async def _fake_query(*args, **kwargs):
        return [{"chunk_id": "chunk_000000", "document_id": str(doc.id), "text": "x", "similarity_score": 0.9, "metadata": {}}]

    monkeypatch.setattr(PgVectorStore, "query", _fake_query, raising=True)
    qa = QAService(db)
    res = qa.run_qa_validation(doc.id)
    assert res.qa_status == "passed"

