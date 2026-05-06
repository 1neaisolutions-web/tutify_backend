"""
Diagnose why OCR is stuck - check memory, process, and conversion.
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
import time

DOCUMENT_ID = "34ee0763-88fa-47d4-b696-ad15e4f9bb9b"

print("=" * 80)
print("OCR ISSUE DIAGNOSIS")
print("=" * 80)
print()

db = SessionLocal()
try:
    doc = db.query(Document).filter(Document.id == DOCUMENT_ID).first()
    if not doc:
        print("[FAIL] Document not found")
        sys.exit(1)
    
    print(f"Document: {doc.filename}")
    print(f"Total Pages: {doc.total_pages}")
    print(f"File Size: {doc.file_size / 1024 / 1024:.2f} MB")
    print(f"File Path: {doc.file_path}")
    print()
    
    # Check file exists
    pdf_path = Path(doc.file_path)
    if not pdf_path.exists():
        print("[FAIL] PDF file not found at path")
        sys.exit(1)
    
    print("[INFO] PDF file exists")
    print()
    
    # Test PDF to image conversion (this is likely where it's stuck)
    print("[DIAGNOSIS] Testing PDF to image conversion...")
    print("   This is likely where OCR is stuck - converting 193 pages to images")
    print("   at 300 DPI requires significant memory and time")
    print()
    
    try:
        from pdf2image import convert_from_path
        import platform
        
        # Check Poppler
        poppler_path = os.getenv("POPPLER_PATH")
        if not poppler_path:
            # Try auto-discovery
            user_home = os.path.expanduser("~")
            poppler_paths = [
                r"C:\poppler\poppler-25.12.0\Library\bin",
                r"C:\poppler\Library\bin",
                os.path.join(user_home, r"Downloads\Release-25.12.0-0 (1)\poppler-25.12.0\Library\bin"),
            ]
            for pp in poppler_paths:
                if Path(pp).exists():
                    poppler_path = pp
                    break
        
        print(f"   Poppler Path: {poppler_path or 'NOT SET'}")
        print()
        print("   [TEST 1] Converting first page only (should be fast)...")
        print("   This tests if Poppler/pdf2image works at all")
        
        convert_kwargs = {"dpi": 300, "first_page": 1, "last_page": 1}
        if poppler_path:
            poppler_path_abs = str(Path(poppler_path).resolve())
            convert_kwargs["poppler_path"] = poppler_path_abs
            if platform.system() == "Windows":
                current_path = os.environ.get("PATH", "")
                if poppler_path_abs not in current_path:
                    os.environ["PATH"] = f"{poppler_path_abs};{current_path}"
        
        start_time = time.time()
        images = convert_from_path(str(pdf_path.resolve()), **convert_kwargs)
        elapsed = time.time() - start_time
        
        print(f"   [PASS] First page converted in {elapsed:.2f} seconds")
        print(f"   Got {len(images)} image(s)")
        print()
        
        # Estimate time for all pages
        time_per_page = elapsed
        estimated_total = time_per_page * doc.total_pages
        print(f"   [ESTIMATE] Time per page: ~{time_per_page:.2f} seconds")
        print(f"   [ESTIMATE] Estimated time for {doc.total_pages} pages: {estimated_total/60:.1f} minutes")
        print()
        
        if estimated_total > 1800:  # More than 30 minutes
            print("   [WARNING] Estimated time exceeds 30 minutes!")
            print("   This explains why OCR appears stuck")
            print()
            print("   [ISSUE IDENTIFIED]")
            print("   Problem: Converting 193 pages sequentially is very slow")
            print("   Solution: OCR is working, but needs more time")
            print("   OR: Implement batch processing to convert pages in chunks")
        else:
            print("   [INFO] Estimated time is reasonable")
            print("   If OCR is stuck, check:")
            print("   1. Backend process is actually running OCR")
            print("   2. Memory is sufficient (193 pages × 300 DPI = ~1.3GB)")
            print("   3. No errors in backend logs")
        
    except Exception as e:
        print(f"   [FAIL] Error during conversion test: {e}")
        import traceback
        traceback.print_exc()
        print()
        print("   [ISSUE IDENTIFIED]")
        print("   PDF to image conversion is failing!")
        print("   This is why OCR is stuck")
        
finally:
    db.close()

print()
print("=" * 80)
