"""
Test OCR directly on the document to see if it's working.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.domains.content_ingestion.models import Document
from app.domains.content_ingestion.providers.ocr_providers import TesseractOCRProvider
import asyncio

DOCUMENT_ID = "34ee0763-88fa-47d4-b696-ad15e4f9bb9b"

async def test_ocr_direct():
    """Test OCR directly on the document."""
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == DOCUMENT_ID).first()
        if not doc:
            print(f"[FAIL] Document {DOCUMENT_ID} not found")
            return
        
        print("=" * 80)
        print("DIRECT OCR TEST")
        print("=" * 80)
        print(f"Document: {doc.filename}")
        print(f"File Path: {doc.file_path}")
        print(f"File Exists: {Path(doc.file_path).exists()}")
        print()
        
        # Check OCR provider
        print("[1] Testing OCR Provider Configuration...")
        ocr_provider = TesseractOCRProvider()
        is_valid = ocr_provider.validate_config()
        print(f"   OCR Provider Valid: {is_valid}")
        if not is_valid:
            print("[FAIL] OCR provider not configured")
            return
        
        # Test OCR on first page only
        print()
        print("[2] Testing OCR on first page (this may take 30-60 seconds)...")
        print("   This will convert PDF to image and run OCR on page 1")
        print()
        
        try:
            # Import pdf2image to test conversion
            from pdf2image import convert_from_path
            import platform
            
            pdf_path = Path(doc.file_path).resolve()
            poppler_path = ocr_provider.poppler_path
            
            print(f"   PDF Path: {pdf_path}")
            print(f"   Poppler Path: {poppler_path}")
            
            # Test PDF to image conversion (first page only)
            print("   Converting first page to image...")
            convert_kwargs = {"dpi": 300, "first_page": 1, "last_page": 1}
            if poppler_path:
                poppler_path_abs = str(Path(poppler_path).resolve())
                convert_kwargs["poppler_path"] = poppler_path_abs
                # Prepend to PATH for DLL resolution
                if platform.system() == "Windows":
                    current_path = os.environ.get("PATH", "")
                    if poppler_path_abs not in current_path:
                        os.environ["PATH"] = f"{poppler_path_abs};{current_path}"
            
            images = convert_from_path(str(pdf_path), **convert_kwargs)
            print(f"   [PASS] PDF conversion successful - got {len(images)} image(s)")
            
            if images:
                print("   Running OCR on first page...")
                import pytesseract
                if ocr_provider.tesseract_cmd:
                    pytesseract.pytesseract.tesseract_cmd = ocr_provider.tesseract_cmd
                
                text = pytesseract.image_to_string(images[0], lang="eng")
                char_count = len(text.strip())
                print(f"   [PASS] OCR successful - extracted {char_count} characters")
                print(f"   Sample text (first 200 chars): {text[:200]}...")
                
                if char_count > 0:
                    print()
                    print("[SUCCESS] OCR is working correctly!")
                    print("   The issue might be:")
                    print("   1. OCR is processing but very slowly (193 pages)")
                    print("   2. OCR text is being processed but not committed to DB yet")
                    print("   3. There's a timeout or blocking issue in the async processing")
                else:
                    print()
                    print("[WARNING] OCR ran but extracted 0 characters")
                    print("   This might indicate:")
                    print("   1. Page is blank or image quality is poor")
                    print("   2. OCR language settings need adjustment")
            else:
                print("[FAIL] No images converted from PDF")
                
        except Exception as e:
            print(f"[FAIL] Error during OCR test: {e}")
            import traceback
            traceback.print_exc()
            print()
            print("This error might explain why OCR is stuck!")
            
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(test_ocr_direct())
