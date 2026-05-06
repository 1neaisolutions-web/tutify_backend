"""
Comprehensive End-to-End Test Suite
Tests the complete content ingestion and worksheet generation flow.
"""
import requests
import sys
import time
import os
from pathlib import Path
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.domains.content_ingestion.models import Document, Chunk, PageText, DocumentProcessingRun
from app.domains.content_ingestion.enums import DocumentStatus
from app.domains.content_ingestion.providers.ocr_providers import TesseractOCRProvider, EasyOCRProvider
from app.core.config import settings
from uuid import UUID

BASE = "http://127.0.0.1:8000"
EMAIL = "test1@gmail.com"
PASSWORD = "123456789aA!"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'
    BOLD = '\033[1m'

def print_success(msg):
    print(f"{Colors.GREEN}[PASS] {msg}{Colors.END}")

def print_error(msg):
    print(f"{Colors.RED}[FAIL] {msg}{Colors.END}")

def print_warning(msg):
    print(f"{Colors.YELLOW}[WARN] {msg}{Colors.END}")

def print_info(msg):
    print(f"{Colors.BLUE}INFO: {msg}{Colors.END}")

def print_header(msg):
    print(f"\n{Colors.BOLD}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}{msg.center(70)}{Colors.END}")
    print(f"{Colors.BOLD}{'='*70}{Colors.END}\n")

def test_authentication():
    """Test 1: Authentication"""
    print_header("TEST 1: AUTHENTICATION")
    try:
        login_response = requests.post(
            f"{BASE}/api/v1/auth/login",
            json={"email": EMAIL, "password": PASSWORD},
            timeout=10
        )
        if login_response.status_code != 200:
            print_error(f"Login failed: {login_response.status_code}")
            print_error(f"Response: {login_response.text}")
            return None
        
        token = login_response.json()["access_token"]
        print_success("Login successful")
        
        # Verify user roles
        user_response = requests.get(
            f"{BASE}/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        if user_response.status_code == 200:
            user = user_response.json()
            roles = [r.get('name') if isinstance(r, dict) else str(r) for r in user.get('roles', [])]
            print_info(f"User roles: {roles}")
            if 'teacher' not in roles:
                print_warning("Teacher role missing - some tests may fail")
        
        return token
    except Exception as e:
        print_error(f"Authentication error: {e}")
        return None

def test_content_packs_access(token):
    """Test 2: Content Packs Access"""
    print_header("TEST 2: CONTENT PACKS ACCESS")
    try:
        packs_response = requests.get(
            f"{BASE}/api/v1/admin/content-packs?is_active=true",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        
        if packs_response.status_code == 200:
            packs = packs_response.json()
            print_success(f"Access granted! Found {len(packs)} packs")
            if packs:
                pack_id = packs[0].get('id')
                pack_name = packs[0].get('name')
                print_info(f"Using pack: {pack_name} (ID: {pack_id})")
                return pack_id
            else:
                print_warning("No content packs available")
                return None
        else:
            print_error(f"Access denied: {packs_response.status_code}")
            print_error(f"Response: {packs_response.text}")
            return None
    except Exception as e:
        print_error(f"Content packs access error: {e}")
        return None

def test_ocr_providers():
    """Test 3: OCR Providers Configuration"""
    print_header("TEST 3: OCR PROVIDERS CONFIGURATION")
    
    # Test Tesseract
    print_info("Testing Tesseract OCR Provider...")
    tesseract_provider = TesseractOCRProvider()
    tesseract_available = tesseract_provider.validate_config()
    if tesseract_available:
        print_success("Tesseract OCR is configured and available")
    else:
        print_warning("Tesseract OCR is not available (install Tesseract binary)")
    
    # Test EasyOCR
    print_info("Testing EasyOCR Provider...")
    easyocr_provider = EasyOCRProvider()
    easyocr_available = easyocr_provider.validate_config()
    if easyocr_available:
        print_success("EasyOCR is configured and available")
    else:
        print_warning("EasyOCR is not available (install: pip install easyocr)")
    
    # Check current OCR engine setting
    current_engine = settings.OCR_ENGINE
    print_info(f"Current OCR_ENGINE setting: {current_engine}")
    
    if current_engine == "tesseract" and not tesseract_available:
        print_warning("OCR_ENGINE is set to 'tesseract' but Tesseract is not available")
    elif current_engine == "easyocr" and not easyocr_available:
        print_warning("OCR_ENGINE is set to 'easyocr' but EasyOCR is not available")
    
    return tesseract_available, easyocr_available

def test_document_processing(pack_id, token):
    """Test 4: Document Processing Pipeline"""
    print_header("TEST 4: DOCUMENT PROCESSING PIPELINE")
    
    db: Session = SessionLocal()
    try:
        pack_uuid = UUID(pack_id)
        documents = db.query(Document).filter(Document.pack_id == pack_uuid).all()
        
        if not documents:
            print_warning("No documents found in pack")
            return False
        
        print_info(f"Found {len(documents)} documents in pack")
        
        published_docs = [d for d in documents if d.status == 'published']
        print_info(f"Published documents: {len(published_docs)}")
        
        if not published_docs:
            print_warning("No published documents found - cannot test worksheet generation")
            return False
        
        # Check each published document
        total_chunks = 0
        chunks_with_embeddings = 0
        total_pages = 0
        pages_with_text = 0
        
        for doc in published_docs:
            print_info(f"\nDocument: {doc.filename}")
            print_info(f"  Status: {doc.status}")
            print_info(f"  Total pages: {doc.total_pages}")
            
            # Check chunks
            chunks = db.query(Chunk).filter(Chunk.document_id == doc.id).all()
            chunks_with_emb = db.query(Chunk).filter(
                Chunk.document_id == doc.id,
                Chunk.embedding.isnot(None)
            ).count()
            
            total_chunks += len(chunks)
            chunks_with_embeddings += chunks_with_emb
            
            print_info(f"  Chunks: {len(chunks)} (with embeddings: {chunks_with_emb})")
            
            # Check page texts
            pages = db.query(PageText).filter(PageText.document_id == doc.id).all()
            total_pages += len(pages)
            pages_with_text += sum(1 for p in pages if p.text and len(p.text.strip()) > 0)
            
            # Check processing runs
            runs = db.query(DocumentProcessingRun).filter(
                DocumentProcessingRun.document_id == doc.id
            ).order_by(DocumentProcessingRun.started_at.desc()).limit(1).all()
            
            if runs:
                latest_run = runs[0]
                print_info(f"  Latest run status: {latest_run.status}")
                print_info(f"  Progress: {latest_run.progress_percentage}%")
                if latest_run.error_message:
                    print_warning(f"  Error: {latest_run.error_message}")
        
        print_info(f"\nSummary:")
        print_info(f"  Total chunks: {total_chunks}")
        print_info(f"  Chunks with embeddings: {chunks_with_embeddings}")
        print_info(f"  Total pages: {total_pages}")
        print_info(f"  Pages with text: {pages_with_text}")
        
        if chunks_with_embeddings > 0:
            print_success("Documents have embeddings - ready for worksheet generation")
            return True
        else:
            print_warning("No embeddings found - documents may need reprocessing")
            return False
            
    except Exception as e:
        print_error(f"Document processing check error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()

def test_worksheet_generation(pack_id, token):
    """Test 5: Worksheet Generation"""
    print_header("TEST 5: WORKSHEET GENERATION")
    
    try:
        request_data = {
            "pack_id": pack_id,
            "topic_text": "Introduction to fractions",
            "grade": "6",
            "subject": "Mathematics",
            "num_questions": 3,
            "difficulty_mix": {
                "easy": 0.4,
                "medium": 0.4,
                "hard": 0.2
            },
            "question_types": ["mcq", "short_answer"]
        }
        
        print_info("Sending worksheet generation request...")
        generate_response = requests.post(
            f"{BASE}/api/v1/worksheets/generate",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            json=request_data,
            timeout=60
        )
        
        print_info(f"Status Code: {generate_response.status_code}")
        
        if generate_response.status_code == 200:
            worksheet = generate_response.json()
            print_success("Worksheet generated successfully!")
            print_info(f"Worksheet ID: {worksheet.get('id')}")
            print_info(f"Questions: {len(worksheet.get('questions', []))}")
            
            # Display sample question
            questions = worksheet.get('questions', [])
            if questions:
                q1 = questions[0]
                print_info(f"\nSample Question:")
                print_info(f"  Type: {q1.get('type')}")
                print_info(f"  Difficulty: {q1.get('difficulty')}")
                print_info(f"  Question: {q1.get('question', '')[:100]}...")
            
            return True
        elif generate_response.status_code == 400:
            error_detail = generate_response.json().get('detail', '')
            if 'No content found' in error_detail:
                print_warning("No content found - pack may need more documents with embeddings")
            else:
                print_error(f"Bad request: {error_detail}")
            return False
        else:
            print_error(f"Failed: {generate_response.text[:200]}")
            return False
            
    except requests.exceptions.Timeout:
        print_warning("Request timed out (this is normal for worksheet generation)")
        return False
    except Exception as e:
        print_error(f"Worksheet generation error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_backend_health():
    """Test 6: Backend Health"""
    print_header("TEST 6: BACKEND HEALTH")
    
    try:
        health_response = requests.get(f"{BASE}/health", timeout=5)
        if health_response.status_code == 200:
            print_success("Backend is healthy")
            return True
        else:
            print_warning(f"Health check returned: {health_response.status_code}")
            return False
    except Exception as e:
        print_error(f"Health check failed: {e}")
        return False

def main():
    """Run all tests"""
    print_header("END-TO-END TEST SUITE")
    print_info(f"Testing against: {BASE}")
    print_info(f"User: {EMAIL}")
    print()
    
    results = {}
    
    # Test 1: Authentication
    token = test_authentication()
    results['authentication'] = token is not None
    if not token:
        print_error("Authentication failed - cannot continue")
        sys.exit(1)
    
    # Test 2: Content Packs Access
    pack_id = test_content_packs_access(token)
    results['content_packs'] = pack_id is not None
    
    # Test 3: OCR Providers
    tesseract_available, easyocr_available = test_ocr_providers()
    results['ocr_providers'] = tesseract_available or easyocr_available
    
    # Test 4: Document Processing
    if pack_id:
        has_embeddings = test_document_processing(pack_id, token)
        results['document_processing'] = has_embeddings
    else:
        print_warning("Skipping document processing test (no pack)")
        results['document_processing'] = False
    
    # Test 5: Worksheet Generation
    if pack_id:
        worksheet_success = test_worksheet_generation(pack_id, token)
        results['worksheet_generation'] = worksheet_success
    else:
        print_warning("Skipping worksheet generation test (no pack)")
        results['worksheet_generation'] = False
    
    # Test 6: Backend Health
    results['backend_health'] = test_backend_health()
    
    # Summary
    print_header("TEST SUMMARY")
    
    total_tests = len(results)
    passed_tests = sum(1 for v in results.values() if v)
    
    for test_name, passed in results.items():
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status:10} {test_name.replace('_', ' ').title()}")
    
    print()
    print(f"Total Tests: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {total_tests - passed_tests}")
    print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
    
    if passed_tests == total_tests:
        print_success("\nAll tests passed! System is working correctly.")
        return 0
    else:
        print_warning("\nSome tests failed. Review the output above for details.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
