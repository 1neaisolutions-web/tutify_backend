"""Check page text content."""
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.domains.content_ingestion.models import Document, PageText
from uuid import UUID

DOCUMENT_ID = "05086659-475c-4755-a2d0-59bebbc3440c"

db: Session = SessionLocal()
try:
    doc = db.query(Document).filter(Document.id == UUID(DOCUMENT_ID)).first()
    if doc:
        print(f"Document: {doc.filename}")
        print(f"Total Pages: {doc.total_pages}")
        print()
        
        # Get first 10 pages
        pages = db.query(PageText).filter(
            PageText.document_id == doc.id
        ).order_by(PageText.page_no).limit(10).all()
        
        print(f"Sample pages (first 10):")
        for page in pages:
            text_preview = page.text[:100] if page.text else "(empty)"
            print(f"  Page {page.page_no}: {len(page.text)} chars - '{text_preview}...'")
        
        # Count pages with text
        pages_with_text = db.query(PageText).filter(
            PageText.document_id == doc.id,
            PageText.text.isnot(None),
            PageText.text != ''
        ).count()
        
        print()
        print(f"Pages with text: {pages_with_text} / {doc.total_pages}")
        
        if pages_with_text == 0:
            print()
            print("⚠️  All pages are empty!")
            print("   This document likely needs OCR.")
            print("   The document was published but has no extractable text.")
finally:
    db.close()
