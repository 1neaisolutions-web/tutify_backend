"""
Directly trigger document reprocessing using the ingestion service.
"""
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from app.db.session import SessionLocal
from app.domains.content_ingestion.jobs import run_ingestion_job_sync
from uuid import UUID

DOCUMENT_ID = "4eb16c21-4470-4ac4-bb6e-f5f1b247e860"

def main():
    db = SessionLocal()
    try:
        print(f"Starting reprocessing for document: {DOCUMENT_ID}")
        document_uuid = UUID(DOCUMENT_ID)
        run_ingestion_job_sync(document_uuid)
        print("Reprocessing completed!")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    main()
