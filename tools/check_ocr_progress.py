"""
Check OCR progress - see if pages are being processed.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.domains.content_ingestion.models import PageText
from sqlalchemy import text

DOCUMENT_ID = "34ee0763-88fa-47d4-b696-ad15e4f9bb9b"

db = SessionLocal()
try:
    # Check page_texts status
    print("=" * 80)
    print("OCR PROGRESS CHECK")
    print("=" * 80)
    print()
    
    # Total pages
    total = db.query(PageText).filter(PageText.document_id == DOCUMENT_ID).count()
    print(f"Total page_texts entries: {total}")
    
    # Pages with text
    with_text = db.execute(
        text("SELECT COUNT(*) FROM page_texts WHERE document_id = :d AND char_count > 0"),
        {"d": DOCUMENT_ID}
    ).scalar_one()
    print(f"Pages with text (char_count > 0): {with_text}")
    
    # Check first few pages
    print()
    print("First 10 pages status:")
    pages = db.query(PageText).filter(
        PageText.document_id == DOCUMENT_ID
    ).order_by(PageText.page_no).limit(10).all()
    
    for page in pages:
        status = "[HAS TEXT]" if page.char_count > 0 else "[NO TEXT]"
        print(f"  Page {page.page_no}: {status} - {page.char_count} chars")
        if page.ocr_engine:
            print(f"    OCR Engine: {page.ocr_engine}")
        if page.ocr_confidence:
            print(f"    OCR Confidence: {page.ocr_confidence:.2f}")
    
    # Check last few pages
    print()
    print("Last 10 pages status:")
    pages = db.query(PageText).filter(
        PageText.document_id == DOCUMENT_ID
    ).order_by(PageText.page_no.desc()).limit(10).all()
    
    for page in reversed(pages):  # Show in order
        status = "[HAS TEXT]" if page.char_count > 0 else "[NO TEXT]"
        print(f"  Page {page.page_no}: {status} - {page.char_count} chars")
    
    # Check if any pages have text at all
    print()
    print("=" * 80)
    if with_text > 0:
        print(f"[PROGRESS] {with_text} pages have text extracted!")
        print(f"OCR is working - {with_text}/{total} pages completed ({with_text/total*100:.1f}%)")
    else:
        print("[WARNING] No pages have text yet")
        print("Possible reasons:")
        print("  1. OCR is still processing (193 pages takes time)")
        print("  2. OCR is stuck or very slow")
        print("  3. OCR text hasn't been committed to database yet")
        print()
        print("Check backend terminal/logs for OCR activity")
    
finally:
    db.close()
