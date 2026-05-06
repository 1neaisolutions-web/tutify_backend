"""
Fix document status and trigger proper OCR processing.
"""
import sys
import os
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from app.db.session import SessionLocal
from app.domains.content_ingestion.models import Document
from app.domains.content_ingestion.enums import DocumentStatus
from app.domains.content_ingestion.jobs import run_ingestion_job_sync
from uuid import UUID

DOCUMENT_ID = "4eb16c21-4470-4ac4-bb6e-f5f1b247e860"

def main():
    # Set OCR engine to easyocr
    os.environ['OCR_ENGINE'] = 'easyocr'
    
    db = SessionLocal()
    try:
        print(f"Fixing document: {DOCUMENT_ID}")
        
        # Get document
        doc = db.query(Document).filter(Document.id == UUID(DOCUMENT_ID)).first()
        if not doc:
            print("Document not found!")
            return
        
        print(f"Current status: {doc.status}")
        print(f"Chunks: {doc.chunks_count if hasattr(doc, 'chunks_count') else 'N/A'}")
        print(f"Force OCR: {doc.processing_metadata.get('force_ocr', False) if doc.processing_metadata else False}")
        
        # Reset status to uploaded
        print("\nResetting status to UPLOADED...")
        doc.status = DocumentStatus.UPLOADED.value
        doc.error_code = None
        doc.error_message = None
        doc.remediation_hint = None
        
        # Ensure force_ocr is set
        if not doc.processing_metadata:
            doc.processing_metadata = {}
        doc.processing_metadata['force_ocr'] = True
        
        db.commit()
        print("Status reset successfully")
        
        # Trigger ingestion job
        print("\nStarting ingestion pipeline...")
        print("This will process 193 pages with OCR (may take 15-30 minutes)...")
        run_ingestion_job_sync(UUID(DOCUMENT_ID))
        
        # Check final status
        db.refresh(doc)
        print(f"\nProcessing completed!")
        print(f"Final status: {doc.status}")
        print(f"Error: {doc.error_message or 'None'}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    main()
