"""
List recent documents to find the one with Poppler error.
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
from datetime import datetime, timedelta

def list_recent_documents(limit=10):
    """List recent documents."""
    db = SessionLocal()
    try:
        # Get recent documents
        docs = db.query(Document).order_by(Document.created_at.desc()).limit(limit).all()
        
        print("=" * 80)
        print(f"RECENT DOCUMENTS (Last {limit})")
        print("=" * 80)
        print()
        
        for i, doc in enumerate(docs, 1):
            print(f"[{i}] Document ID: {doc.id}")
            print(f"    Filename: {doc.filename}")
            print(f"    Status: {doc.status}")
            print(f"    Created: {doc.created_at}")
            if doc.error_code:
                print(f"    Error Code: {doc.error_code}")
                print(f"    Error Message: {(doc.error_message or '')[:100]}...")
            print()
        
        # Find documents with Poppler errors
        print("=" * 80)
        print("DOCUMENTS WITH POPPLER ERRORS:")
        print("=" * 80)
        print()
        
        all_docs = db.query(Document).all()
        poppler_errors = []
        for doc in all_docs:
            if doc.error_message and "Poppler" in doc.error_message:
                poppler_errors.append(doc)
        
        if poppler_errors:
            for doc in poppler_errors:
                print(f"Document ID: {doc.id}")
                print(f"  Filename: {doc.filename}")
                print(f"  Status: {doc.status}")
                print(f"  Error: {doc.error_code}")
                print(f"  Created: {doc.created_at}")
                print()
        else:
            print("No documents with Poppler errors found.")
        
    finally:
        db.close()

if __name__ == "__main__":
    list_recent_documents(10)
