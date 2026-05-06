"""Quick check: how many chunks have page_start_pdf > 5 for the math document."""
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
from app.db.session import SessionLocal
from app.domains.content_ingestion.models import Chunk
from sqlalchemy import text

db = SessionLocal()
doc_id = "d418ee80-60e5-4599-856b-6a9493cdb414"
r = db.execute(text("""
    SELECT page_start_pdf, page_end_pdf, COUNT(*) 
    FROM chunks 
    WHERE document_id = :d 
    GROUP BY page_start_pdf, page_end_pdf 
    ORDER BY page_start_pdf 
    LIMIT 25
"""), {"d": doc_id}).fetchall()
total = db.execute(text("SELECT COUNT(*) FROM chunks WHERE document_id = :d"), {"d": doc_id}).scalar()
after5 = db.execute(text("SELECT COUNT(*) FROM chunks WHERE document_id = :d AND page_start_pdf > 5"), {"d": doc_id}).scalar()
print(f"Document {doc_id}: total chunks={total}, chunks with page_start_pdf > 5 = {after5}")
print("Sample (page_start, page_end, count):", r[:15])
db.close()
