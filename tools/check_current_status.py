"""
Check current status of the document being processed.
"""
import sys
import io
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.domains.content_ingestion.models import Document, PageText, Chunk, DocumentProcessingRun
from uuid import UUID

DOCUMENT_ID = "34ee0763-88fa-47d4-b696-ad15e4f9bb9b"

db = SessionLocal()
try:
    doc = db.query(Document).filter(Document.id == UUID(DOCUMENT_ID)).first()
    if not doc:
        print(f"[FAIL] Document {DOCUMENT_ID} not found")
        sys.exit(1)
    
    print("=" * 80)
    print("CURRENT DOCUMENT STATUS")
    print("=" * 80)
    print()
    print(f"Document ID: {doc.id}")
    print(f"Filename: {doc.filename}")
    print(f"Status: {doc.status}")
    print(f"Total Pages: {doc.total_pages}")
    print(f"File Size: {doc.file_size / 1024 / 1024:.2f} MB" if doc.file_size else "N/A")
    print()
    
    # Check error info
    if doc.error_code:
        print(f"[ERROR] Error Code: {doc.error_code}")
    if doc.error_message:
        print(f"[ERROR] Error Message: {doc.error_message[:200]}")
    if doc.remediation_hint:
        print(f"[HINT] {doc.remediation_hint[:200]}")
    print()
    
    # Check processing metadata
    if doc.processing_metadata:
        meta = doc.processing_metadata
        print("Processing Metadata:")
        if "ocr_attempted" in meta:
            print(f"  OCR Attempted: {meta['ocr_attempted']}")
        if "pdf_type" in meta:
            print(f"  PDF Type: {meta['pdf_type']}")
        if "preflight_result" in meta:
            preflight = meta.get("preflight_result", {})
            print(f"  Tesseract Found: {preflight.get('tesseract_found', False)}")
            print(f"  Poppler Found: {preflight.get('poppler_found', False)}")
        print()
    
    # Check page texts
    page_texts = db.query(PageText).filter(PageText.document_id == doc.id).all()
    total_pages = len(page_texts)
    pages_with_text = sum(1 for p in page_texts if p.char_count > 0)
    total_chars = sum(p.char_count for p in page_texts)
    
    print("Page Texts:")
    print(f"  Total Page Records: {total_pages}")
    print(f"  Pages with Text (char_count > 0): {pages_with_text}")
    print(f"  Total Characters: {total_chars:,}")
    print()
    
    # Show first few pages status
    if page_texts:
        print("First 10 Pages Status:")
        for page in sorted(page_texts[:10], key=lambda x: x.page_no):
            status = f"{page.char_count} chars" if page.char_count > 0 else "[NO TEXT]"
            ocr_info = f" (OCR: {page.ocr_engine})" if page.ocr_engine else ""
            print(f"  Page {page.page_no}: {status}{ocr_info}")
        if len(page_texts) > 10:
            print(f"  ... and {len(page_texts) - 10} more pages")
        print()
    
    # Check chunks
    chunks = db.query(Chunk).filter(Chunk.document_id == doc.id).all()
    chunks_with_embeddings = sum(1 for c in chunks if c.embedding_v is not None)
    
    print("Chunks:")
    print(f"  Total Chunks: {len(chunks)}")
    print(f"  Chunks with Embeddings: {chunks_with_embeddings}")
    print()
    
    # Check processing runs
    runs = db.query(DocumentProcessingRun).filter(
        DocumentProcessingRun.document_id == doc.id
    ).order_by(DocumentProcessingRun.started_at.desc()).limit(5).all()
    
    if runs:
        print("Recent Processing Runs:")
        for run in runs:
            started = run.started_at.replace(tzinfo=timezone.utc) if run.started_at.tzinfo is None else run.started_at
            elapsed = ""
            if run.started_at:
                elapsed_seconds = (datetime.now(timezone.utc) - started).total_seconds()
                elapsed_minutes = elapsed_seconds / 60
                elapsed = f" ({elapsed_minutes:.1f} minutes ago)"
            print(f"  Run {str(run.id)[:8]}...")
            print(f"    Status: {run.status}")
            print(f"    Step: {run.current_step or 'N/A'}")
            print(f"    Progress: {run.progress_percentage}%")
            print(f"    Started: {started.strftime('%Y-%m-%d %H:%M:%S UTC')}{elapsed}")
            if run.error_message:
                print(f"    Error: {run.error_message[:100]}")
            print()
    
    # Calculate time since creation
    if doc.created_at:
        created = doc.created_at.replace(tzinfo=timezone.utc) if doc.created_at.tzinfo is None else doc.created_at
        elapsed = (datetime.now(timezone.utc) - created).total_seconds()
        elapsed_minutes = elapsed / 60
        print(f"Time Since Upload: {elapsed_minutes:.1f} minutes ({elapsed_minutes/60:.1f} hours)")
        print()
    
    # Status assessment
    print("=" * 80)
    print("STATUS ASSESSMENT")
    print("=" * 80)
    print()
    
    if doc.status == "ocr_running":
        if pages_with_text == 0:
            print("[STUCK] OCR is running but no pages have text yet.")
            print("  This suggests OCR is either:")
            print("  1. Still converting PDF to images (can take 2-5 minutes for 193 pages)")
            print("  2. Processing pages but text not committed yet (all-or-nothing)")
            print("  3. Stuck/hanging due to memory or other issues")
            print()
            print("  Recommendation: Check backend terminal logs for:")
            print("    - 'Running Tesseract OCR on'")
            print("    - 'OCR completed for page X'")
            print("    - Any error messages")
        else:
            print(f"[PROGRESS] OCR is working - {pages_with_text}/{total_pages} pages have text")
    elif doc.status == "failed":
        print("[FAILED] Document processing failed.")
        print(f"  Check error_message above for details.")
    elif doc.status == "published":
        print("[SUCCESS] Document is published!")
        if chunks_with_embeddings > 0:
            print(f"  {chunks_with_embeddings} chunks with embeddings ready.")
    else:
        print(f"[INFO] Document status: {doc.status}")
    
    print()
    print("=" * 80)
    
finally:
    db.close()
