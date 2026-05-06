"""Quick status report."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from app.db.session import SessionLocal
from app.domains.content_ingestion.models import Document, PageText, Chunk

db = SessionLocal()
try:
    doc = db.query(Document).filter(Document.filename.like('%Mathematics%')).order_by(Document.created_at.desc()).first()
    if doc:
        chunks = db.query(Chunk).filter(Chunk.document_id == doc.id).count()
        chunks_emb = db.query(Chunk).filter(Chunk.document_id == doc.id, Chunk.embedding.isnot(None)).count()
        pages = db.query(PageText).filter(PageText.document_id == doc.id).count()
        print(f"REPORT: Doc={doc.id} | Status={doc.status} | Pages={doc.total_pages or 0} | PageTexts={pages} | Chunks={chunks} | ChunksWithEmb={chunks_emb}")
    else:
        print("REPORT: No document found")
finally:
    db.close()
