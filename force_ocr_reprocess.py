"""
Force OCR reprocessing for document with empty page texts.
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Set OCR engine before importing
os.environ['OCR_ENGINE'] = 'easyocr'

from app.db.session import SessionLocal
from app.domains.content_ingestion.models import Document, PageText
from app.domains.content_ingestion.enums import DocumentStatus
from app.domains.content_ingestion.services.ingestion_service import IngestionService
from uuid import UUID

DOCUMENT_ID = "4eb16c21-4470-4ac4-bb6e-f5f1b247e860"

db = SessionLocal()
try:
    doc = db.query(Document).filter(Document.id == UUID(DOCUMENT_ID)).first()
    if not doc:
        print("Document not found")
        sys.exit(1)
    
    print(f"Document: {doc.filename}")
    print(f"Status: {doc.status}")
    print(f"File path: {doc.file_path}")
    
    # Check page texts
    page_texts = db.query(PageText).filter(PageText.document_id == doc.id).all()
    print(f"\nPage texts: {len(page_texts)}")
    
    if page_texts:
        total_chars = sum(p.char_count for p in page_texts)
        print(f"Total characters: {total_chars}")
        
        if total_chars == 0:
            print("\n[WARN] All page texts are empty! OCR needs to run.")
            print("Deleting empty page texts and resetting status...")
            
            # Delete empty page texts
            for pt in page_texts:
                db.delete(pt)
            db.commit()
            print(f"Deleted {len(page_texts)} empty page texts")
    
    # Reset document status
    print("\nResetting document status...")
    doc.status = DocumentStatus.UPLOADED.value
    doc.error_code = None
    doc.error_message = None
    doc.remediation_hint = None
    if not doc.processing_metadata:
        doc.processing_metadata = {}
    doc.processing_metadata['force_ocr'] = True
    db.commit()
    print("Status reset to UPLOADED with force_ocr=True")
    
    # Run ingestion
    print("\nStarting ingestion with OCR...")
    print("This will:")
    print("  1. Extract text (will be empty)")
    print("  2. Detect need for OCR (force_ocr=True)")
    print("  3. Run EasyOCR on all 193 pages")
    print("  4. Extract text from OCR")
    print("  5. Create chunks")
    print("  6. Generate embeddings")
    print("  7. Store in vector DB")
    print()
    
    # Run ingestion with progress monitoring
    print("\n" + "="*70)
    print("STARTING PROCESSING PIPELINE")
    print("="*70)
    print("Steps:")
    print("  1. Extract text (will be empty for scanned PDF)")
    print("  2. Run OCR with EasyOCR (193 pages - may take 15-30 minutes)")
    print("  3. Normalize extracted text")
    print("  4. Create chunks (500 tokens each)")
    print("  5. Generate embeddings (OpenAI)")
    print("  6. Store in vector database")
    print("  7. Verify chunks saved")
    print("  8. Run QA validation")
    print("  9. Publish (only if chunks verified)")
    print("="*70 + "\n")
    
    ingestion_service = IngestionService(db)
    import asyncio
    
    # Run with progress updates
    print("[INFO] Starting ingestion pipeline...")
    print("[INFO] This will take 15-30 minutes for OCR...")
    print()
    
    try:
        result = asyncio.run(ingestion_service.ingest_document(UUID(DOCUMENT_ID)))
        
        print("\n" + "="*70)
        print("PROCESSING COMPLETED")
        print("="*70)
        print(f"Final status: {result.status}")
    
    # Check chunks
    from app.domains.content_ingestion.models import Chunk
    chunks = db.query(Chunk).filter(Chunk.document_id == doc.id).count()
    chunks_with_emb = db.query(Chunk).filter(
        Chunk.document_id == doc.id,
        Chunk.embedding.isnot(None)
    ).count()
    
    print(f"Chunks: {chunks} total, {chunks_with_emb} with embeddings")
    
    if result.status == 'published' and chunks_with_emb > 0:
        print("\n[PASS] Document successfully processed!")
    elif result.status == 'failed':
        print(f"\n[FAIL] Processing failed: {result.error_message}")
    else:
        print(f"\n[WARN] Status: {result.status}, Chunks: {chunks_with_emb}")
        
except Exception as e:
    print(f"\n[FAIL] Error: {e}")
    import traceback
    traceback.print_exc()
finally:
    db.close()
