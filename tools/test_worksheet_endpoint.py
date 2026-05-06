"""
Test worksheet generation endpoint.
Uses the pack_id from E2E tests that has published documents with embeddings.
"""
import os
import sys
import io
import requests
from pathlib import Path

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.domains.content_ingestion.models import ContentPack, Document
from app.domains.auth.models import User

BASE_URL = "http://127.0.0.1:8000"

def get_test_pack_id(db: Session) -> str:
    """Get a pack_id that has published documents."""
    # Find a pack with published documents
    pack = db.query(ContentPack).join(Document).filter(
        Document.status == "published"
    ).first()
    
    if pack:
        return str(pack.id)
    
    # Fallback: get any pack
    pack = db.query(ContentPack).first()
    if pack:
        return str(pack.id)
    
    return None

def check_backend_running() -> bool:
    """Check if backend server is running."""
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        return response.status_code == 200
    except:
        try:
            response = requests.get(f"{BASE_URL}/api/v1/health", timeout=5)
            return response.status_code == 200
        except:
            return False

def get_test_user_token() -> str:
    """Get authentication token for test user."""
    # Try common test credentials
    test_credentials = [
        {"email": "test1@gmail.com", "password": "123456789aA!"},
        {"email": "admin@1ne.ai", "password": "Admin123!@#"},
    ]
    
    for creds in test_credentials:
        try:
            response = requests.post(
                f"{BASE_URL}/api/v1/auth/login",
                json=creds,
                timeout=10
            )
            if response.status_code == 200:
                return response.json()["access_token"]
        except Exception:
            continue
    
    return None

def test_worksheet_generation():
    """Test worksheet generation endpoint."""
    print("=" * 80)
    print("WORKSHEET GENERATION ENDPOINT TEST")
    print("=" * 80)
    print()
    
    # Step 0: Check if backend is running
    print("[0] Checking if backend server is running...")
    if not check_backend_running():
        print("   [FAIL] Backend server is not running!")
        print()
        print("   To start the backend server:")
        print("   1. Open a new terminal")
        print("   2. Navigate to the project directory")
        print("   3. Activate virtual environment:")
        print("      venv\\Scripts\\activate")
        print("   4. Start the server:")
        print("      python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000")
        print()
        print("   Or use the provided script:")
        print("      .\\start_backend_now.ps1")
        print()
        return False
    print("   [PASS] Backend server is running")
    print()
    
    # Step 1: Get authentication token
    print("[1] Authenticating...")
    token = get_test_user_token()
    if not token:
        print("   [FAIL] Could not authenticate")
        print("   Please ensure:")
        print("   - Backend is running")
        print("   - Test user exists (test1@gmail.com or admin@1ne.ai)")
        print("   - Database is accessible")
        return False
    print("   [PASS] Authentication successful")
    print()
    
    # Step 2: Get pack_id with published documents
    print("[2] Finding content pack with published documents...")
    db = SessionLocal()
    try:
        pack_id = get_test_pack_id(db)
        if not pack_id:
            print("   [FAIL] No content packs found")
            print("   Please ensure documents are ingested and published")
            return False
        
        pack = db.query(ContentPack).filter(ContentPack.id == pack_id).first()
        print(f"   [PASS] Found pack: {pack.name if pack else 'Unknown'} (ID: {pack_id})")
        
        # Check if pack has published documents
        doc_count = db.query(Document).filter(
            Document.pack_id == pack_id,
            Document.status == "published"
        ).count()
        print(f"   Published documents in pack: {doc_count}")
        
        if doc_count == 0:
            print("   [WARN] Pack has no published documents")
            print("   Worksheet generation may fail if no content is available")
    finally:
        db.close()
    print()
    
    # Step 3: Test worksheet generation
    print("[3] Testing worksheet generation endpoint...")
    print(f"   URL: {BASE_URL}/api/v1/worksheets/generate")
    print(f"   Method: POST")
    print()
    
    # New API: single difficulty, num_questions 1-20, question_types (mcq/short_answer/long_answer)
    request_data = {
        "pack_id": pack_id,
        "topic_text": "Introduction to fractions and basic math",
        "grade": "6",
        "subject": "Mathematics",
        "num_questions": 3,  # Small number for faster testing (max 20)
        "difficulty": "medium",
        "question_types": ["mcq", "short_answer"]
    }
    
    print("   Request payload (professional overhaul API):")
    print(f"   - Pack ID: {request_data['pack_id']}")
    print(f"   - Topic: {request_data['topic_text']}")
    print(f"   - Grade: {request_data['grade']}")
    print(f"   - Subject: {request_data['subject']}")
    print(f"   - Number of questions: {request_data['num_questions']}")
    print(f"   - Difficulty: {request_data['difficulty']}")
    print(f"   - Question types: {request_data['question_types']}")
    print()
    
    try:
        print("   Sending request (this may take 30-60 seconds)...")
        response = requests.post(
            f"{BASE_URL}/api/v1/worksheets/generate",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            },
            json=request_data,
            timeout=90  # Longer timeout for LLM generation
        )
        
        print(f"   Status Code: {response.status_code}")
        print()
        
        if response.status_code == 200:
            worksheet = response.json()
            print("   [PASS] SUCCESS! Worksheet generated!")
            print()
            print("   Worksheet Details:")
            print(f"   - Worksheet ID: {worksheet.get('id')}")
            print(f"   - Topic: {worksheet.get('topic_text')}")
            print(f"   - Grade: {worksheet.get('grade')}")
            print(f"   - Subject: {worksheet.get('subject')}")
            print(f"   - Number of questions: {len(worksheet.get('questions', []))}")
            print()
            
            # Show sample questions
            questions = worksheet.get('questions', [])
            if questions:
                print("   Sample Questions:")
                for i, q in enumerate(questions[:2], 1):  # Show first 2
                    print(f"   {i}. [{q.get('type', 'unknown')}] {q.get('question', '')[:80]}...")
                    print(f"      Difficulty: {q.get('difficulty', 'unknown')}, Points: {q.get('points', 0)}")
                if len(questions) > 2:
                    print(f"   ... and {len(questions) - 2} more questions")
            
            # Show answer key
            answer_key = worksheet.get('answer_key', {})
            if answer_key:
                print()
                print(f"   Answer Key: {len(answer_key)} answers provided")
            
            # Show citations
            citations = worksheet.get('citations')
            if citations:
                print(f"   Citations: {len(citations)} source chunks used")
            
            return True
            
        elif response.status_code == 400:
            print("   [FAIL] BAD REQUEST")
            print(f"   Response: {response.text[:500]}")
            print()
            print("   Possible issues:")
            print("   - Invalid pack_id")
            print("   - No content found for the topic")
            print("   - Missing required fields")
            return False
            
        elif response.status_code == 401:
            print("   [FAIL] UNAUTHORIZED")
            print("   Authentication token expired or invalid")
            return False
            
        elif response.status_code == 403:
            print("   [FAIL] FORBIDDEN")
            print("   User does not have permission to generate worksheets")
            return False
            
        elif response.status_code == 404:
            print("   [FAIL] NOT FOUND")
            print("   Pack not found or no content available")
            return False
            
        elif response.status_code == 500:
            print("   [FAIL] INTERNAL SERVER ERROR")
            print(f"   Response: {response.text[:500]}")
            print()
            print("   Possible issues:")
            print("   - OpenAI API key not configured")
            print("   - LLM service unavailable")
            print("   - Database error")
            print("   - Vector retrieval failed")
            return False
            
        else:
            print(f"   [FAIL] UNEXPECTED STATUS CODE: {response.status_code}")
            print(f"   Response: {response.text[:500]}")
            return False
            
    except requests.exceptions.Timeout:
        print("   [TIMEOUT] REQUEST TIMED OUT")
        print("   Worksheet generation is taking longer than expected")
        print("   This might indicate:")
        print("   - LLM API is slow or unavailable")
        print("   - Network issues")
        print("   - Backend processing delay")
        return False
        
    except requests.exceptions.ConnectionError:
        print("   [FAIL] CONNECTION ERROR")
        print("   Cannot connect to backend server")
        print(f"   Ensure backend is running at {BASE_URL}")
        return False
        
    except Exception as e:
        print(f"   [FAIL] ERROR: {type(e).__name__}: {str(e)}")
        return False

if __name__ == "__main__":
    success = test_worksheet_generation()
    print()
    print("=" * 80)
    if success:
        print("TEST RESULT: [PASS] PASSED")
    else:
        print("TEST RESULT: [FAIL] FAILED")
    print("=" * 80)
    sys.exit(0 if success else 1)
