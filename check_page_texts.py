"""Check page texts content."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from app.db.session import SessionLocal
from app.domains.content_ingestion.models import Document, PageText

db = SessionLocal()
try:
    doc = db.query(Document).filter(Document.filename.like('%Mathematics%')).order_by(Document.created_at.desc()).first()
    if doc:
        pts = db.query(PageText).filter(PageText.document_id == doc.id).limit(5).all()
        print(f'Sample page texts for document {doc.id}:')
        for pt in pts:
            text_preview = pt.text[:50] if pt.text else "EMPTY"
            print(f'  Page {pt.page_no}: chars={pt.char_count}, text_len={len(pt.text) if pt.text else 0}, preview="{text_preview}"')
        
        total = db.query(PageText).filter(PageText.document_id == doc.id).count()
        with_text = db.query(PageText).filter(PageText.document_id == doc.id, PageText.char_count > 0).count()
        print(f'\nTotal page texts: {total}')
        print(f'Page texts with content: {with_text}')
        print(f'Empty page texts: {total - with_text}')
    else:
        print("No document found")
finally:
    db.close()
