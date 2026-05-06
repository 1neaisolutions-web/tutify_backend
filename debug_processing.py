"""
Debug document processing to find why chunks aren't being created.
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.db.session import SessionLocal
from app.domains.content_ingestion.models import Document, Chunk, PageText, DocumentProcessingRun
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
    print(f"Pages: {doc.total_pages}")
    print()
    
    # Check page texts
    page_texts = db.query(PageText).filter(PageText.document_id == doc.id).all()
    print(f"Page texts: {len(page_texts)}")
    if page_texts:
        total_chars = sum(p.char_count for p in page_texts)
        avg_chars = total_chars / len(page_texts) if page_texts else 0
        print(f"Total characters: {total_chars}")
        print(f"Average chars per page: {avg_chars:.0f}")
        print(f"Sample page 1 text length: {len(page_texts[0].text) if page_texts else 0}")
    
    # Check chunks
    chunks = db.query(Chunk).filter(Chunk.document_id == doc.id).all()
    print(f"\nChunks: {len(chunks)}")
    
    # Check processing runs
    runs = db.query(DocumentProcessingRun).filter(
        DocumentProcessingRun.document_id == doc.id
    ).order_by(DocumentProcessingRun.started_at.desc()).limit(3).all()
    
    print(f"\nProcessing runs: {len(runs)}")
    for run in runs:
        print(f"  Run {run.id}: {run.status} - {run.current_step}")
        print(f"    Pages processed: {run.pages_processed}")
        print(f"    Chunks created: {run.chunks_created}")
        print(f"    Vectors stored: {run.vectors_stored}")
        print(f"    Progress: {run.progress_percentage}%")
        if run.error_message:
            print(f"    Error: {run.error_message}")
    
finally:
    db.close()
