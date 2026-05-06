"""
RAG pipeline fundamentals sanity script.

Phases:
1) Libraries + local embedding model sanity
2) PgVector write test using PgVectorStore.upsert
3) Similarity search using pgvector operator on embedding_v

Run with: python tools/rag_sanity.py
"""
import os
import sys
import uuid
import asyncio
import traceback
from pathlib import Path
from typing import List

# Ensure project root is on sys.path so `import app` works when run as a script
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def phase1() -> tuple[bool, int | None]:
    """
    Phase 1:
    - For EMBEDDING_PROVIDER=fake: only check core libs (sqlalchemy, pgvector, tiktoken)
    - For EMBEDDING_PROVIDER=local: additionally require torch + sentence_transformers and load model
    """
    print("=== PHASE 1: LIBRARIES + MODEL SANITY ===", flush=True)
    ok = True
    dim: int | None = None

    embedding_provider = (os.getenv("EMBEDDING_PROVIDER") or "fake").lower()
    print(f"EMBEDDING_PROVIDER={embedding_provider}")

    def _import(name: str, module: str) -> None:
        nonlocal ok
        try:
            __import__(module)
            print(f"IMPORT {name}: PASS ({module})")
        except Exception as e:
            ok = False
            print(f"IMPORT {name}: FAIL ({module}) -> {e}")
            traceback.print_exc()

    # Core imports required for both fake/local
    _import("tiktoken", "tiktoken")
    _import("sqlalchemy", "sqlalchemy")
    _import("pgvector", "pgvector")

    try:
        from pgvector.sqlalchemy import Vector  # noqa: F401
        print("IMPORT pgvector.sqlalchemy.Vector: PASS")
    except Exception as e:
        ok = False
        print(f"IMPORT pgvector.sqlalchemy.Vector: FAIL -> {e}")

    # Fake provider: no torch/sentence-transformers required
    if embedding_provider == "fake":
        if ok:
            print("PHASE 1 RESULT: PASS (fake provider, core libs OK)")
            return True, None
        print("PHASE 1 RESULT: FAIL (fake provider, core libs missing)")
        return False, None

    # Local provider: require torch + sentence_transformers and load model
    _import("torch", "torch")
    _import("SentenceTransformer", "sentence_transformers")
    model_name = os.getenv("LOCAL_EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")
    print(f"MODEL NAME: {model_name}")

    try:
        from sentence_transformers import SentenceTransformer

        print("Loading SentenceTransformer model...")
        model = SentenceTransformer(model_name)
        texts = [
            "This is a test.",
            "Another test sentence.",
            "Solve x^2 + 2x + 1 = 0.",
        ]
        import numpy as np

        vecs: np.ndarray = model.encode(texts, convert_to_numpy=True)  # type: ignore[assignment]
        dim = int(vecs.shape[1])
        print(f"Embedding vectors shape: {vecs.shape}")
        print(f"embedding_dim={dim}")
        print(f"len(vectors)={len(vecs)}")
        first5 = vecs[0][:5].tolist()
        print(f"first5={first5}")
        print("PHASE 1 RESULT: PASS")
        return True, dim
    except Exception as e:
        ok = False
        print("PHASE 1 RESULT: FAIL (model load/embed)")
        print("ERROR:", e)
        traceback.print_exc()
        cache_dir = os.getenv("TRANSFORMERS_CACHE") or os.path.expanduser("~/.cache/huggingface/hub")
        print(f"Model cache directory (guess): {cache_dir}")
        return False, dim


async def phase2(embedding_dim_hint: int | None) -> tuple[bool, uuid.UUID | None]:
    print("\n=== PHASE 2: PGVECTOR WRITE TEST ===", flush=True)
    try:
        from sqlalchemy.orm import Session
        from app.db.session import SessionLocal
        from app.domains.content_ingestion.providers.base import Chunk as ChunkDTO
        from app.domains.content_ingestion.providers.embedding_providers import (
            FakeEmbeddingProvider,
            LocalSentenceTransformersEmbeddingProvider,
        )
        from app.domains.content_ingestion.providers.vector_stores import PgVectorStore

        embedding_provider = (os.getenv("EMBEDDING_PROVIDER") or "fake").lower()
        if embedding_provider == "local":
            emb = LocalSentenceTransformersEmbeddingProvider()
            if not emb.validate_config():
                print("LocalSentenceTransformersEmbeddingProvider: validate_config()=False")
                return False, None
        else:
            emb = FakeEmbeddingProvider()

        texts = [
            "Solve x + 1 = 0",
            "Solve x^2 + 2x + 1 = 0",
            "Linear equations in one variable",
            "Quadratic equation basics",
            "Graph of a linear function",
        ]
        print(f"Generating embeddings for {len(texts)} test chunks using provider={emb.provider_name}...")
        vecs: List[List[float]] = await emb.embed(texts)
        dim = embedding_dim_hint or emb.get_embedding_dimension()
        print(f"embedding_dim (provider)={emb.get_embedding_dimension()}, used_dim={dim}")

        # Build fake Chunk DTOs
        doc_id = uuid.uuid4()
        pack_id = uuid.uuid4()
        chunks: List[ChunkDTO] = []
        for i, text in enumerate(texts):
            chunks.append(
                ChunkDTO(
                    chunk_id=f"test_chunk_{i}",
                    text=text,
                    page_start=1,
                    page_end=1,
                    topic_id=None,
                    topic_title=None,
                    metadata={"test": True},
                )
            )

        # Use real PgVectorStore + DB session
        db: Session = SessionLocal()
        store = PgVectorStore(db=db)
        if not store.validate_config():
            print("PgVectorStore.validate_config(): FAIL (pgvector extension not available or DB down)")
            db.close()
            return False, None

        # Create dummy document and pack (required by FK constraint)
        from app.domains.content_ingestion.models import Document, ContentPack
        from datetime import datetime, timezone
        from app.domains.content_ingestion.enums import DocumentStatus

        # Get or create a tenant (required by FK)
        from app.domains.auth.models import Tenant, TenantType
        tenant = db.query(Tenant).first()
        if not tenant:
            tenant_id = uuid.uuid4()
            tenant = Tenant(
                id=tenant_id,
                name="RAG_SANITY_TEST_TENANT",
                slug=f"rag-sanity-test-{tenant_id.hex[:8]}",
                type=TenantType.PLATFORM,
                hierarchy_path=f"/{tenant_id}/",
                is_active=True,
            )
            db.add(tenant)
            db.flush()
            print(f"Created test tenant_id={tenant.id}")

        # Create pack first
        pack = ContentPack(
            id=pack_id,
            name="RAG_SANITY_TEST_PACK",
            tenant_id=tenant.id,
            is_active=True,
        )
        db.add(pack)
        db.flush()

        # Create document
        doc = Document(
            id=doc_id,
            pack_id=pack_id,
            filename="rag_sanity_test.pdf",
            file_path="/dev/null",
            source_type="pdf",
            status=DocumentStatus.UPLOADED.value,
            tenant_id=tenant.id,
        )
        db.add(doc)
        db.flush()
        print(f"Created test document_id={doc_id}, pack_id={pack_id}")

        print(f"Calling PgVectorStore.upsert() for document_id={doc_id} ...")
        stored = await store.upsert(
            chunks=chunks,
            vectors=vecs,
            document_id=str(doc_id),
            pack_id=str(pack_id),
            embedding_model=emb.provider_name,
            embedding_dim=dim,
            embedding_provider=emb.provider_name,
        )
        print(f"PgVectorStore.upsert stored_count={stored}")

        # SQL verification
        from sqlalchemy import text

        total = db.execute(
            text("SELECT COUNT(*) FROM chunks WHERE document_id = :d"),
            {"d": str(doc_id)},
        ).scalar_one()
        non_null = db.execute(
            text(
                "SELECT COUNT(*) FROM chunks "
                "WHERE document_id = :d AND embedding_v IS NOT NULL"
            ),
            {"d": str(doc_id)},
        ).scalar_one()
        rows = db.execute(
            text(
                "SELECT embedding_model, embedding_dim, embedding_provider, COUNT(*) "
                "FROM chunks WHERE document_id = :d "
                "GROUP BY embedding_model, embedding_dim, embedding_provider"
            ),
            {"d": str(doc_id)},
        ).fetchall()
        print(f"SQL total chunks for test doc: {total}")
        print(f"SQL chunks with embedding_v IS NOT NULL: {non_null}")
        print("SQL distinct embedding_model, embedding_dim, embedding_provider, count:")
        for r in rows:
            print("  ", r)

        ok = (stored == len(texts)) and (non_null == len(texts))
        print(f"PHASE 2 RESULT: {'PASS' if ok else 'FAIL'}")
        db.close()
        return ok, doc_id if ok else None
    except Exception as e:
        print("PHASE 2 RESULT: FAIL")
        print("ERROR:", e)
        traceback.print_exc()
        return False, None


async def phase3(doc_id: uuid.UUID | None) -> bool:
    print("\n=== PHASE 3: SIMILARITY SEARCH TEST ===", flush=True)
    if not doc_id:
        print("Skipping Phase 3: Phase 2 did not produce a document_id.")
        return False
    try:
        from sqlalchemy.orm import Session
        from sqlalchemy import text
        from app.db.session import SessionLocal
        from app.domains.content_ingestion.providers.embedding_providers import (
            FakeEmbeddingProvider,
            LocalSentenceTransformersEmbeddingProvider,
        )

        db: Session = SessionLocal()

        embedding_provider = (os.getenv("EMBEDDING_PROVIDER") or "fake").lower()
        if embedding_provider == "local":
            emb = LocalSentenceTransformersEmbeddingProvider()
            if not emb.validate_config():
                print("LocalSentenceTransformersEmbeddingProvider: validate_config()=False")
                db.close()
                return False
        else:
            emb = FakeEmbeddingProvider()
        query_text = "solve linear equation x"
        q_vec_raw = (await emb.embed([query_text]))[0]
        provider_dim = len(q_vec_raw)
        print(f"Query vector dimension from provider: {provider_dim}")

        # Pad to 1536 to match embedding_v column definition (vector(1536))
        # Note: Only first {provider_dim} dimensions are meaningful, rest are zero-padded
        PGVECTOR_DIM = 1536
        q_vec = list(q_vec_raw) + [0.0] * (PGVECTOR_DIM - provider_dim) if provider_dim < PGVECTOR_DIM else list(q_vec_raw)[:PGVECTOR_DIM]
        vector_str = "[" + ",".join(str(float(x)) for x in q_vec) + "]"

        print(f"Running pgvector similarity search for document_id={doc_id} using provider={emb.provider_name} (query_dim={provider_dim}, padded_to={len(q_vec)})...")
        # Use vector_str directly in SQL (pgvector requires literal vector syntax)
        rows = db.execute(
            text(
                f"SELECT chunk_id, text, "
                f"embedding_v <=> '{vector_str}'::vector AS distance "
                f"FROM chunks "
                f"WHERE document_id = :d AND embedding_v IS NOT NULL AND embedding_model = :m "
                f"ORDER BY embedding_v <=> '{vector_str}'::vector "
                f"LIMIT 5"
            ),
            {"d": str(doc_id), "m": emb.provider_name},
        ).fetchall()

        if not rows:
            print("No results returned from similarity search.")
            db.close()
            print("PHASE 3 RESULT: FAIL")
            return False

        print("Top-k results:")
        for r in rows:
            snippet = (r.text or "")[:80].replace("\n", " ")
            print(f"  chunk_id={r.chunk_id}, distance={r.distance:.4f}, snippet={snippet!r}")

        print("PHASE 3 RESULT: PASS")
        db.close()
        return True
    except Exception as e:
        print("PHASE 3 RESULT: FAIL")
        print("ERROR:", e)
        traceback.print_exc()
        return False


def main() -> None:
    phase1_ok, dim = phase1()
    if not phase1_ok:
        print("\nOVERALL: STOP after Phase 1 (model/lib failure).")
        sys.exit(1)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        phase2_ok, doc_id = loop.run_until_complete(phase2(dim))
        if not phase2_ok:
            print("\nOVERALL: STOP after Phase 2 (pgvector write failure).")
            sys.exit(1)
        phase3_ok = loop.run_until_complete(phase3(doc_id))
    finally:
        loop.close()

    print("\n=== SUMMARY ===")
    print(f"Phase 1 (libs + model): {'PASS' if phase1_ok else 'FAIL'}")
    print(f"Phase 2 (pgvector write): {'PASS' if phase2_ok else 'FAIL'}")
    print(f"Phase 3 (similarity search): {'PASS' if phase3_ok else 'FAIL'}")
    if phase1_ok and phase2_ok and phase3_ok:
        print("OVERALL: PASS")
    else:
        print("OVERALL: FAIL")


if __name__ == "__main__":
    main()

