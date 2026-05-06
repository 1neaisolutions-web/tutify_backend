"""
End-to-end test script for worksheet generation.
Tests performance, stability, and quality gates.
"""
import asyncio
import json
import time
import requests
from typing import Dict, Any, List
from uuid import UUID

BASE_URL = "http://127.0.0.1:8000"
API_ENDPOINT = f"{BASE_URL}/api/v1/worksheets/generate"

# Test user credentials (adjust if needed)
TEST_EMAIL = "test@example.com"
TEST_PASSWORD = "testpassword123"

class WorksheetTester:
    def __init__(self):
        self.session = requests.Session()
        self.token = None
        self.results: List[Dict[str, Any]] = []
    
    def login(self):
        """Login and get auth token."""
        login_url = f"{BASE_URL}/api/v1/auth/login"
        response = self.session.post(login_url, json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        if response.status_code == 200:
            data = response.json()
            self.token = data.get("access_token")
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
            print(f"✓ Logged in successfully")
            return True
        else:
            print(f"✗ Login failed: {response.status_code} - {response.text}")
            return False
    
    def test_worksheet_generation(
        self,
        test_name: str,
        pack_id: str,
        topic_text: str,
        grade: str = "6",
        subject: str = "Math",
        difficulty: str = None,
        num_questions: int = 10,
        question_types: List[str] = None,
        force_regenerate: bool = False,
        expect_board_fallback: bool = False,
    ) -> Dict[str, Any]:
        """Test worksheet generation and collect diagnostics."""
        print(f"\n{'='*80}")
        print(f"TEST: {test_name}")
        print(f"{'='*80}")
        
        if question_types is None:
            question_types = ["mcq", "short_answer"]
        
        payload = {
            "pack_id": pack_id,
            "topic_text": topic_text,
            "grade": grade,
            "subject": subject,
            "num_questions": num_questions,
            "question_types": question_types,
        }
        
        if difficulty:
            payload["difficulty"] = difficulty
        
        if force_regenerate:
            payload["force_regenerate"] = True
        
        start_time = time.time()
        
        try:
            response = self.session.post(
                API_ENDPOINT,
                json=payload,
                timeout=120  # 120s timeout
            )
            elapsed_time = time.time() - start_time
            elapsed_ms = elapsed_time * 1000
            
            result = {
                "test_name": test_name,
                "status_code": response.status_code,
                "elapsed_ms": elapsed_ms,
                "success": response.status_code == 200,
                "error": None,
                "diagnostics": {}
            }
            
            if response.status_code == 200:
                data = response.json()
                result["diagnostics"] = self._extract_diagnostics(data, response.headers)
                result["worksheet_id"] = data.get("id")
                result["questions_count"] = len(data.get("questions", []))
                result["created_at"] = data.get("created_at")
                
                # Validate quality gates
                result["quality_checks"] = self._validate_quality(data, difficulty)
                
                print(f"✓ Request succeeded in {elapsed_ms:.0f}ms")
                print(f"  Worksheet ID: {result['worksheet_id']}")
                print(f"  Questions: {result['questions_count']}")
                print(f"  Cache: {result['diagnostics'].get('cache_status', 'unknown')}")
                print(f"  Total time: {result['diagnostics'].get('total_request_ms', 'N/A')}ms")
                print(f"  Estimated tokens: {result['diagnostics'].get('estimated_tokens', 'N/A')}")
                
            else:
                result["error"] = response.text
                print(f"✗ Request failed: {response.status_code}")
                print(f"  Error: {response.text[:200]}")
            
            self.results.append(result)
            return result
            
        except requests.exceptions.Timeout:
            elapsed_ms = (time.time() - start_time) * 1000
            result = {
                "test_name": test_name,
                "status_code": 504,
                "elapsed_ms": elapsed_ms,
                "success": False,
                "error": "Request timeout (>120s)",
                "diagnostics": {}
            }
            print(f"✗ Request timed out after {elapsed_ms:.0f}ms")
            self.results.append(result)
            return result
        
        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            result = {
                "test_name": test_name,
                "status_code": 0,
                "elapsed_ms": elapsed_ms,
                "success": False,
                "error": str(e),
                "diagnostics": {}
            }
            print(f"✗ Request failed with exception: {e}")
            self.results.append(result)
            return result
    
    def _extract_diagnostics(self, data: Dict, headers: Dict) -> Dict[str, Any]:
        """Extract diagnostic information from response."""
        diag = {
            "cache_status": headers.get("X-Worksheet-Cache", "unknown"),
            "request_id": headers.get("X-Request-Id", "unknown"),
            "total_request_ms": None,
            "estimated_tokens": None,
            "generation_mode": None,
            "final_difficulty_used": data.get("final_difficulty_used"),
            "attempts_count": data.get("attempts_count"),
            "created_at": data.get("created_at"),
        }
        
        # Try to extract from retrieval_metadata if available
        citations = data.get("citations", [])
        if citations:
            diag["citations_count"] = len(citations)
        
        # Check if created_at is null
        if diag["created_at"] is None:
            diag["created_at_null"] = True
        
        return diag
    
    def _validate_quality(self, data: Dict, requested_difficulty: str = None) -> Dict[str, Any]:
        """Validate quality gates."""
        checks = {
            "mcq_valid": True,
            "topic_aligned": True,
            "difficulty_met": True,
            "language_appropriate": True,
            "marking_scheme_concise": True,
            "created_at_not_null": data.get("created_at") is not None,
        }
        
        questions = data.get("questions", [])
        
        # MCQ validation
        mcq_questions = [q for q in questions if q.get("type") == "mcq"]
        for q in mcq_questions:
            options = q.get("options", [])
            correct = q.get("correct_answer", "")
            
            if len(options) != 4:
                checks["mcq_valid"] = False
                checks["mcq_issue"] = f"Question {q.get('id')} has {len(options)} options (expected 4)"
                break
            
            if correct not in ["A", "B", "C", "D"]:
                checks["mcq_valid"] = False
                checks["mcq_issue"] = f"Question {q.get('id')} has invalid correct_answer: {correct}"
                break
            
            # Check uniqueness
            if len(set(options)) != len(options):
                checks["mcq_valid"] = False
                checks["mcq_issue"] = f"Question {q.get('id')} has duplicate options"
                break
        
        # Marking scheme conciseness
        marking_scheme = data.get("marking_scheme", {})
        for qid, ms in marking_scheme.items():
            criteria = ms.get("criteria", "")
            if criteria and len(criteria) > 200:  # Rough check for brevity
                checks["marking_scheme_concise"] = False
                checks["marking_issue"] = f"Question {qid} has verbose marking scheme ({len(criteria)} chars)"
                break
        
        # Language check (basic - check for common issues)
        for q in questions:
            question_text = q.get("question", "")
            if len(question_text.split(".")) > 5:  # Too many sentences
                checks["language_appropriate"] = False
                break
        
        return checks
    
    def print_summary(self):
        """Print test summary report."""
        print(f"\n{'='*80}")
        print("TEST SUMMARY REPORT")
        print(f"{'='*80}\n")
        
        total_tests = len(self.results)
        passed = sum(1 for r in self.results if r["success"])
        failed = total_tests - passed
        
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}\n")
        
        # Performance analysis
        print("PERFORMANCE ANALYSIS:")
        print("-" * 80)
        
        times = [r["elapsed_ms"] for r in self.results if r["success"]]
        if times:
            avg_time = sum(times) / len(times)
            max_time = max(times)
            min_time = min(times)
            print(f"Average time: {avg_time:.0f}ms")
            print(f"Min time: {min_time:.0f}ms")
            print(f"Max time: {max_time:.0f}ms")
            print(f"Target: <70000ms")
            
            over_target = [t for t in times if t > 70000]
            if over_target:
                print(f"⚠ WARNING: {len(over_target)} tests exceeded 70s target")
            else:
                print("✓ All tests met time target")
        
        print("\nQUALITY GATES:")
        print("-" * 80)
        
        for result in self.results:
            if result["success"]:
                checks = result.get("quality_checks", {})
                print(f"\n{result['test_name']}:")
                print(f"  MCQ Valid: {checks.get('mcq_valid', 'N/A')}")
                print(f"  Created At Not Null: {checks.get('created_at_not_null', 'N/A')}")
                print(f"  Marking Scheme Concise: {checks.get('marking_scheme_concise', 'N/A')}")
                if checks.get("mcq_issue"):
                    print(f"  ⚠ MCQ Issue: {checks['mcq_issue']}")
                if checks.get("marking_issue"):
                    print(f"  ⚠ Marking Issue: {checks['marking_issue']}")
        
        print("\nDETAILED RESULTS:")
        print("-" * 80)
        
        for result in self.results:
            print(f"\n{result['test_name']}:")
            print(f"  Status: {result['status_code']}")
            print(f"  Time: {result['elapsed_ms']:.0f}ms")
            print(f"  Success: {result['success']}")
            if result.get("diagnostics"):
                diag = result["diagnostics"]
                print(f"  Cache: {diag.get('cache_status')}")
                print(f"  Difficulty Used: {diag.get('final_difficulty_used')}")
            if result.get("error"):
                print(f"  Error: {result['error'][:100]}")


def main():
    """Run all test cases."""
    tester = WorksheetTester()
    
    if not tester.login():
        print("Cannot proceed without authentication")
        return
    
    # Test pack ID (you may need to adjust this)
    PACK_ID = "5d400835-a1f6-4bb9-a5e6-4e0999a1d8a7"
    
    # Test Case 1: Basic set topic, easy difficulty
    tester.test_worksheet_generation(
        test_name="Set Topic - Easy",
        pack_id=PACK_ID,
        topic_text="set",
        grade="6",
        subject="Math",
        difficulty="easy",
        num_questions=10,
        question_types=["mcq", "short_answer"],
    )
    
    # Test Case 2: Set topic, medium difficulty (main issue case)
    tester.test_worksheet_generation(
        test_name="Set Topic - Medium",
        pack_id=PACK_ID,
        topic_text="set",
        grade="6",
        subject="Math",
        difficulty="medium",
        num_questions=10,
        question_types=["mcq", "short_answer"],
    )
    
    # Test Case 3: Set topic, hard difficulty
    tester.test_worksheet_generation(
        test_name="Set Topic - Hard",
        pack_id=PACK_ID,
        topic_text="set",
        grade="6",
        subject="Math",
        difficulty="hard",
        num_questions=10,
        question_types=["mcq", "short_answer"],
    )
    
    # Test Case 4: Force regenerate (cache miss)
    tester.test_worksheet_generation(
        test_name="Set Topic - Medium (Force Regenerate)",
        pack_id=PACK_ID,
        topic_text="set",
        grade="6",
        subject="Math",
        difficulty="medium",
        num_questions=10,
        question_types=["mcq", "short_answer"],
        force_regenerate=True,
    )
    
    # Test Case 5: Different topic (should exist in pack)
    tester.test_worksheet_generation(
        test_name="Algebra Topic - Medium",
        pack_id=PACK_ID,
        topic_text="algebra",
        grade="6",
        subject="Math",
        difficulty="medium",
        num_questions=10,
        question_types=["mcq", "short_answer"],
    )
    
    # Test Case 6: Edge case topic (might be weak)
    tester.test_worksheet_generation(
        test_name="Fraction Topic - Medium",
        pack_id=PACK_ID,
        topic_text="fraction",
        grade="6",
        subject="Math",
        difficulty="medium",
        num_questions=10,
        question_types=["mcq", "short_answer"],
    )
    
    # Test Case 7: Likely missing topic (should return 422)
    tester.test_worksheet_generation(
        test_name="Non-existent Topic - Medium",
        pack_id=PACK_ID,
        topic_text="quantum_physics",
        grade="6",
        subject="Math",
        difficulty="medium",
        num_questions=10,
        question_types=["mcq", "short_answer"],
    )
    
    # Print summary
    tester.print_summary()
    
    # Save results to file
    with open("worksheet_test_results.json", "w") as f:
        json.dump(tester.results, f, indent=2, default=str)
    
    print(f"\n✓ Results saved to worksheet_test_results.json")


if __name__ == "__main__":
    main()
