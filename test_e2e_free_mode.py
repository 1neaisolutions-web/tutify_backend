"""
End-to-End Ingestion Test in FREE MODE
Tests hybrid PDF and scanned PDF through full pipeline with DB evidence.
"""
import os
import sys
import io
import asyncio
import time
from pathlib import Path
from uuid import UUID
from typing import Optional, Dict, Any

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Set FREE MODE env vars BEFORE any imports
os.environ["EMBEDDING_PROVIDER"] = "fake"
os.environ["FAKE_EMBEDDING_DIM"] = "384"
os.environ["VECTOR_STORE"] = "pgvector"
os.environ["OCR_PROVIDER"] = "tesseract"

# Add project root to path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy.orm import Session
from sqlalchemy import text
from app.db.session import SessionLocal
from app.domains.content_ingestion.services.ingestion_service import IngestionService
from app.domains.content_ingestion.services.document_service import DocumentService
from app.domains.content_ingestion.models import Document, Chunk, PageText
from app.domains.content_ingestion.enums import DocumentStatus
from app.domains.content_ingestion.providers.embedding_providers import FakeEmbeddingProvider
from app.domains.content_ingestion.providers.ocr_preflight import OcrPreflight, OcrPreflightError
from app.domains.auth.models import Tenant, TenantType
from app.domains.content_ingestion.models import ContentPack
from app.core.logging import get_logger

logger = get_logger(__name__)

# Test PDFs
HYBRID_PDF = ROOT / "math_ocr_test_pack.pdf"
SCANNED_PDF = ROOT / "math_ocr_test_pack_scanned.pdf"

# Test credentials (use existing or create test user)
TEST_EMAIL = "admin@1ne.ai"
TEST_PASSWORD = "Admin123!@#"


def print_section(title: str):
    """Print a section header."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def print_result(label: str, value: Any, status: str = "INFO"):
    """Print a result line."""
    status_symbol = {"PASS": "[PASS]", "FAIL": "[FAIL]", "INFO": "[INFO]", "WARN": "[WARN]"}.get(status, "[*]")
    print(f"{status_symbol} {label}: {value}")


def get_or_create_tenant(db: Session) -> Tenant:
    """Get or create a test tenant."""
    tenant = db.query(Tenant).first()
    if not tenant:
        tenant_id = UUID("00000000-0000-0000-0000-000000000001")
        tenant = Tenant(
            id=tenant_id,
            name="E2E_TEST_TENANT",
            slug="e2e-test-tenant",
            type=TenantType.PLATFORM,
            hierarchy_path=f"/{tenant_id}/",
            is_active=True,
        )
        db.add(tenant)
        db.commit()
        print_result("Created test tenant", str(tenant.id))
    return tenant


def get_or_create_pack(db: Session, tenant_id: UUID) -> ContentPack:
    """Get or create a test content pack."""
    pack = db.query(ContentPack).filter(ContentPack.tenant_id == tenant_id).first()
    if not pack:
        pack_id = UUID("00000000-0000-0000-0000-000000000002")
        pack = ContentPack(
            id=pack_id,
            name="E2E_TEST_PACK",
            tenant_id=tenant_id,
            is_active=True,
        )
        db.add(pack)
        db.commit()
        print_result("Created test pack", str(pack.id))
    else:
        print_result("Using existing pack", str(pack.id))
    return pack


def create_document_for_pdf(
    db: Session,
    pack_id: UUID,
    tenant_id: UUID,
    pdf_path: Path,
    force_ocr: bool = False,
) -> Document:
    """Create a document record for a PDF file."""
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    import hashlib
    with open(pdf_path, "rb") as f:
        file_content = f.read()
        file_hash = hashlib.sha256(file_content).hexdigest()
        file_size = len(file_content)

    # Save file to documents directory
    from app.core.config import settings
    documents_dir = Path(settings.DOCUMENTS_DIR)
    documents_dir.mkdir(parents=True, exist_ok=True)

    import uuid
    from datetime import datetime
    file_ext = pdf_path.suffix
    unique_filename = f"{uuid.uuid4()}_{int(datetime.now().timestamp())}{file_ext}"
    file_path = documents_dir / unique_filename

    with open(file_path, "wb") as f:
        f.write(file_content)

    # Create document
    service = DocumentService(db)
    document = service.create_document(
        pack_id=pack_id,
        filename=pdf_path.name,
        file_path=str(file_path),
        file_size=file_size,
        mime_type="application/pdf",
        source_type="pdf",
        tenant_id=tenant_id,
        uploaded_by=None,  # Test mode
        title=pdf_path.stem,
        author=None,
        chapter_map=None,
        document_hash=file_hash,
    )

    if force_ocr:
        document.processing_metadata = {"force_ocr": True}
        db.commit()

    print_result(f"Created document", f"{document.id} ({pdf_path.name})")
    return document


async def run_ingestion(db: Session, document_id: UUID) -> Document:
    """Run ingestion pipeline for a document."""
    print_result("Starting ingestion", f"document_id={document_id}")
    ingestion_service = IngestionService(db)
    document = await ingestion_service.ingest_document(document_id)
    return document


def monitor_document_status(db: Session, document_id: UUID, max_wait: int = 600) -> Document:
    """Monitor document status until complete or failed."""
    start_time = time.time()
    last_status = None

    while time.time() - start_time < max_wait:
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            raise ValueError(f"Document {document_id} not found")

        status = document.status
        if status != last_status:
            elapsed = int(time.time() - start_time)
            print_result(f"[{elapsed}s] Status", status)
            last_status = status

        if status == DocumentStatus.PUBLISHED.value:
            print_result("Ingestion completed", "PUBLISHED", "PASS")
            return document

        if status == DocumentStatus.FAILED.value:
            print_result("Ingestion failed", f"{document.error_code}: {document.error_message}", "FAIL")
            return document

        time.sleep(2)
        db.refresh(document)

    print_result("Timeout", f"Processing exceeded {max_wait}s", "WARN")
    return document


def query_page_texts(db: Session, document_id: UUID) -> Dict[str, int]:
    """Query page_texts evidence."""
    result = db.execute(
        text("""
            SELECT 
                COUNT(*) AS pages,
                SUM(CASE WHEN char_count > 0 THEN 1 ELSE 0 END) AS non_empty_pages
            FROM page_texts
            WHERE document_id = :d
        """),
        {"d": str(document_id)},
    ).fetchone()

    return {
        "pages": result[0] or 0,
        "non_empty_pages": result[1] or 0,
    }


def query_chunks(db: Session, document_id: UUID) -> Dict[str, Any]:
    """Query chunk evidence."""
    # Total chunks
    total = db.execute(
        text("SELECT COUNT(*) FROM chunks WHERE document_id = :d"),
        {"d": str(document_id)},
    ).scalar_one()

    # Chunks with embedding_v
    with_vectors = db.execute(
        text("""
            SELECT COUNT(*) 
            FROM chunks 
            WHERE document_id = :d 
              AND embedding_v IS NOT NULL 
              AND embedding_model = 'fake'
        """),
        {"d": str(document_id)},
    ).scalar_one()

    # Model/dim/provider breakdown
    model_info = db.execute(
        text("""
            SELECT embedding_model, embedding_dim, embedding_provider, COUNT(*)
            FROM chunks
            WHERE document_id = :d
            GROUP BY embedding_model, embedding_dim, embedding_provider
        """),
        {"d": str(document_id)},
    ).fetchall()

    # Math blocks count
    math_blocks_count = 0
    try:
        math_blocks_count = db.execute(
            text("SELECT COUNT(*) FROM math_blocks WHERE document_id = :d"),
            {"d": str(document_id)},
        ).scalar_one()
    except Exception:
        pass  # Table might not exist

    # Chunks with math markers
    chunks_with_math = db.execute(
        text("""
            SELECT COUNT(*) 
            FROM chunks 
            WHERE document_id = :d 
              AND text LIKE '%[[MATH]]%'
        """),
        {"d": str(document_id)},
    ).scalar_one()

    return {
        "total_chunks": total,
        "chunks_with_vectors": with_vectors,
        "model_info": model_info,
        "math_blocks": math_blocks_count,
        "chunks_with_math_markers": chunks_with_math,
    }


async def test_retrieval_async(db: Session, document_id: UUID) -> list:
    """Test vector retrieval."""
    # Generate query embedding
    emb_provider = FakeEmbeddingProvider()
    query_text = "solve linear equation"
    query_vec = (await emb_provider.embed([query_text]))[0]
    provider_dim = len(query_vec)

    # Pad to 1536 for pgvector column
    PGVECTOR_DIM = 1536
    q_vec_padded = list(query_vec) + [0.0] * (PGVECTOR_DIM - provider_dim)
    vector_str = "[" + ",".join(str(float(x)) for x in q_vec_padded) + "]"

    # Run similarity search
    results = db.execute(
        text(f"""
            SELECT 
                chunk_id, 
                page_start_pdf, 
                page_end_pdf,
                (embedding_v <=> '{vector_str}'::vector) AS distance,
                LEFT(text, 120) AS snippet
            FROM chunks
            WHERE document_id = :d
              AND embedding_v IS NOT NULL
              AND embedding_model = 'fake'
            ORDER BY embedding_v <=> '{vector_str}'::vector
            LIMIT 5
        """),
        {"d": str(document_id)},
    ).fetchall()

    return results


async def print_evidence(db: Session, document_id: UUID, pdf_name: str):
    """Print all DB evidence for a document."""
    print_section(f"DB EVIDENCE: {pdf_name}")

    # Page texts
    page_info = query_page_texts(db, document_id)
    print_result("Page texts - Total pages", page_info["pages"])
    print_result("Page texts - Non-empty pages", page_info["non_empty_pages"])

    # Chunks
    chunk_info = query_chunks(db, document_id)
    print_result("Chunks - Total", chunk_info["total_chunks"])
    print_result("Chunks - With embedding_v", chunk_info["chunks_with_vectors"])
    print_result("Math blocks", chunk_info["math_blocks"])
    print_result("Chunks with math markers", chunk_info["chunks_with_math_markers"])

    # Model info
    print("\nModel/Dim/Provider breakdown:")
    for row in chunk_info["model_info"]:
        print(f"  {row[0]} | dim={row[1]} | provider={row[2]} | count={row[3]}")

    # Retrieval test (will be called from async context)
    print("\nRetrieval test results (top 5):")
    retrieval_results = await test_retrieval_async(db, document_id)
    for i, row in enumerate(retrieval_results, 1):
        print(f"  {i}. chunk_id={row[0]}, distance={row[3]:.4f}, pages={row[1]}-{row[2]}")
        print(f"     snippet: {row[4][:100]}...")


async def test_pdf(pdf_path: Path, force_ocr: bool = False) -> Dict[str, Any]:
    """Test ingestion for a single PDF."""
    db = SessionLocal()
    try:
        pdf_name = pdf_path.name
        print_section(f"TESTING: {pdf_name}")

        # Setup
        tenant = get_or_create_tenant(db)
        pack = get_or_create_pack(db, tenant.id)

        # Create document
        document = create_document_for_pdf(db, pack.id, tenant.id, pdf_path, force_ocr=force_ocr)
        document_id = document.id

        # Run ingestion
        document = await run_ingestion(db, document_id)

        # Monitor status
        document = monitor_document_status(db, document_id)

        # Print evidence
        await print_evidence(db, document_id, pdf_name)

        # Final status
        final_status = document.status
        error_info = None
        if final_status == DocumentStatus.FAILED.value:
            error_info = {
                "error_code": document.error_code,
                "error_message": document.error_message,
                "failed_step": document.processing_metadata.get("failed_step") if document.processing_metadata else None,
            }

        # Get evidence
        page_info = query_page_texts(db, document_id)
        chunk_info = query_chunks(db, document_id)
        retrieval_results = await test_retrieval_async(db, document_id)

        return {
            "document_id": str(document_id),
            "pdf_name": pdf_name,
            "status": final_status,
            "error_info": error_info,
            "page_info": page_info,
            "chunk_info": chunk_info,
            "retrieval_results": retrieval_results,
        }
    finally:
        db.close()


async def main():
    """Main test runner."""
    print_section("END-TO-END FREE MODE INGESTION TEST")
    print_result("EMBEDDING_PROVIDER", os.getenv("EMBEDDING_PROVIDER", "NOT SET"))
    print_result("FAKE_EMBEDDING_DIM", os.getenv("FAKE_EMBEDDING_DIM", "NOT SET"))
    print_result("OCR_PROVIDER", os.getenv("OCR_PROVIDER", "NOT SET"))
    print_result("VECTOR_STORE", os.getenv("VECTOR_STORE", "NOT SET"))
    
    # Check OCR preflight
    print_section("OCR PREFLIGHT CHECK")
    try:
        preflight_result = OcrPreflight.check()
        print_result("Tesseract found", preflight_result["tesseract_found"], "PASS" if preflight_result["tesseract_found"] else "FAIL")
        if preflight_result["tesseract_path"]:
            print_result("Tesseract path", preflight_result["tesseract_path"])
        print_result("Poppler found", preflight_result["poppler_found"], "PASS" if preflight_result["poppler_found"] else "FAIL")
        if preflight_result["poppler_path"]:
            print_result("Poppler path", preflight_result["poppler_path"])
        if preflight_result["errors"]:
            print("\n[WARN] OCR binaries missing - scanned PDF test will fail:")
            for error in preflight_result["errors"]:
                print(f"  {error}")
    except Exception as e:
        print_result("Preflight check failed", str(e), "FAIL")

    results = []

    # Test 1: Hybrid PDF
    if HYBRID_PDF.exists():
        result1 = await test_pdf(HYBRID_PDF, force_ocr=False)
        results.append(result1)
    else:
        print_result(f"Hybrid PDF not found", str(HYBRID_PDF), "FAIL")

    # Test 2: Scanned PDF
    if SCANNED_PDF.exists():
        result2 = await test_pdf(SCANNED_PDF, force_ocr=True)  # Force OCR for scanned
        results.append(result2)
    else:
        print_result(f"Scanned PDF not found", str(SCANNED_PDF), "FAIL")

    # Final summary
    print_section("FINAL SUMMARY")
    for result in results:
        print(f"\n[PDF] {result['pdf_name']}")
        print(f"   Document ID: {result['document_id']}")
        print(f"   Status: {result['status']}")
        print(f"   Pages: {result['page_info']['pages']} (non-empty: {result['page_info']['non_empty_pages']})")
        print(f"   Chunks: {result['chunk_info']['total_chunks']} (with vectors: {result['chunk_info']['chunks_with_vectors']})")
        if result['error_info']:
            print(f"   [FAIL] Error: {result['error_info']['error_code']} - {result['error_info']['error_message']}")
        if result['retrieval_results']:
            top_result = result['retrieval_results'][0]
            print(f"   [RETRIEVAL] Top result: distance={top_result[3]:.4f}, snippet={top_result[4][:60]}...")


if __name__ == "__main__":
    asyncio.run(main())
