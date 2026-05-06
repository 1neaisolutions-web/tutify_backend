"""Quick system verification without long operations."""
import sys
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.domains.content_ingestion.models import Document, Chunk
from app.domains.content_ingestion.providers.ocr_providers import TesseractOCRProvider, EasyOCRProvider
from app.core.config import settings
from uuid import UUID

PACK_ID = "67ff7e11-a2e7-4eac-9177-9f682fb3ba0e"

print("="*70)
print("SYSTEM VERIFICATION")
print("="*70)
print()

# Check OCR Providers
print("1. OCR Providers:")
tesseract = TesseractOCRProvider()
easyocr = EasyOCRProvider()
tesseract_ok = tesseract.validate_config()
easyocr_ok = easyocr.validate_config()
print(f"   Tesseract: {'[OK] Available' if tesseract_ok else '[NOT AVAILABLE] Install Tesseract binary'}")
print(f"   EasyOCR: {'[OK] Available' if easyocr_ok else '[NOT AVAILABLE] Needs Visual C++ Redistributable'}")
print(f"   Current OCR_ENGINE: {settings.OCR_ENGINE}")
if not tesseract_ok and not easyocr_ok:
    print("   WARNING: No OCR provider available!")
    print("   Option 1: Install Tesseract binary")
    print("   Option 2: Install Visual C++ Redistributable for EasyOCR")
print()

# Check Document Status
print("2. Document Status:")
db: Session = SessionLocal()
try:
    pack_uuid = UUID(PACK_ID)
    documents = db.query(Document).filter(Document.pack_id == pack_uuid).all()
    
    if documents:
        doc = documents[0]
        chunks_with_emb = db.query(Chunk).filter(
            Chunk.document_id == doc.id,
            Chunk.embedding.isnot(None)
        ).count()
        
        print(f"   Document: {doc.filename}")
        print(f"   Status: {doc.status}")
        print(f"   Pages: {doc.total_pages}")
        print(f"   Chunks with embeddings: {chunks_with_emb}")
        
        if chunks_with_emb > 0:
            print("   [OK] Ready for worksheet generation")
        else:
            print("   [NEEDS PROCESSING] Document needs OCR to extract text")
    else:
        print("   ✗ No documents found")
finally:
    db.close()

print()
print("="*70)
print("VERIFICATION COMPLETE")
print("="*70)
print()
print("To complete end-to-end flow:")
print("1. Set OCR_ENGINE=easyocr")
print("2. Run: python check_and_fix_documents.py")
print("3. Wait for processing (15-30 min)")
print("4. Run: python test_end_to_end.py")
