"""Quick check of document statuses."""
import os
import sys
from pathlib import Path

os.environ["EMBEDDING_PROVIDER"] = "fake"
os.environ["FAKE_EMBEDDING_DIM"] = "384"

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal
from app.domains.content_ingestion.models import Document

db = SessionLocal()
try:
    hybrid = db.query(Document).filter(Document.filename == "math_ocr_test_pack.pdf").order_by(Document.created_at.desc()).first()
    scanned = db.query(Document).filter(Document.filename == "math_ocr_test_pack_scanned.pdf").order_by(Document.created_at.desc()).first()
    
    print("HYBRID PDF:")
    if hybrid:
        print(f"  ID: {hybrid.id}")
        print(f"  Status: {hybrid.status}")
    else:
        print("  NOT FOUND")
    
    print("\nSCANNED PDF:")
    if scanned:
        print(f"  ID: {scanned.id}")
        print(f"  Status: {scanned.status}")
    else:
        print("  NOT FOUND")
finally:
    db.close()
