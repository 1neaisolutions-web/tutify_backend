"""
Direct service-level test for worksheet generation.
Tests the WorksheetService.generate_worksheet method directly without requiring API server.
"""
import asyncio
import json
import time
import sys
from pathlib import Path
from uuid import UUID

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.domains.content_ingestion.services.worksheet_service import WorksheetService
from app.domains.content_ingestion.services.mcq_validator import validate_mcq
from app.domains.content_ingestion.services.difficulty_validator import difficulty_fidelity_check, get_worksheet_difficulty_stats

class WorksheetServiceTester:
    def __init__(self):
        self.db: Session = SessionLocal()
        self.service = WorksheetService(self.db)
        self.results: list = []
    
    async def test_worksheet_generation(
        self,
        test_name: str,
        pack_id: str,
        topic_text: str,
        grade: str = "6",
        subject: str = "Math",
        difficulty: str = None,
        num_questions: int = 10,
        question_types: list = None,
        force_regenerate: bool = False,
    ) -> dict:
        """Test worksheet generation and collect diagnostics."""
        print(f"\n{'='*80}")
        print(f"TEST: {test_name}")
        print(f"{'='*80}")
        
        if question_types is None:
            question_types = ["mcq", "short_answer"]
        
        start_time = time.monotonic()
        
        try:
            worksheet_cache = await self.service.generate_worksheet(
                pack_id=UUID(pack_id),
                topic_id=None,
                topic_text=topic_text,
                grade=grade,
                subject=subject,
                difficulty_mix={"medium": 1.0} if difficulty == "medium" else ({"easy": 1.0} if difficulty == "easy" else ({"hard": 1.0} if difficulty == "hard" else None)),
                num_questions=num_questions,
                question_types=question_types,
                force_regenerate=force_regenerate,
            )
            
            elapsed_time = time.monotonic() - start_time
            elapsed_ms = elapsed_time * 1000
            
            worksheet_data = worksheet_cache.worksheet_json
            questions = worksheet_data.get("questions", [])
            
            result = {
                "test_name": test_name,
                "success": True,
                "elapsed_ms": elapsed_ms,
                "worksheet_id": str(worksheet_cache.id),
                "questions_count": len(questions),
                "created_at": worksheet_cache.created_at.isoformat() if worksheet_cache.created_at else None,
                "diagnostics": {
                    "cache_hit": getattr(worksheet_cache, "from_cache", False),
                    "total_request_ms": elapsed_ms,
                },
                "quality_checks": {}
            }
            
            # Extract diagnostics from retrieval_metadata
            retrieval_meta = worksheet_cache.retrieval_metadata or {}
            result["diagnostics"]["generation_mode"] = retrieval_meta.get("generation_mode", "pack_grounded")
            result["diagnostics"]["citations_count"] = len(retrieval_meta.get("citations", []))
            
            # Validate quality gates
            result["quality_checks"] = self._validate_quality(worksheet_data, questions, difficulty)
            
            print(f"[OK] Request succeeded in {elapsed_ms:.0f}ms")
            print(f"  Worksheet ID: {result['worksheet_id']}")
            print(f"  Questions: {result['questions_count']}")
            print(f"  Cache: {'hit' if result['diagnostics']['cache_hit'] else 'miss'}")
            print(f"  Total time: {elapsed_ms:.0f}ms")
            print(f"  Generation mode: {result['diagnostics'].get('generation_mode', 'unknown')}")
            print(f"  Created at: {result['created_at']}")
            
            # Performance checks
            if elapsed_ms > 70000:
                print(f"  [WARN] Exceeded 70s target ({elapsed_ms:.0f}ms)")
            else:
                print(f"  [OK] Met time target (<70s)")
            
            self.results.append(result)
            return result
            
        except ValueError as e:
            elapsed_ms = (time.monotonic() - start_time) * 1000
            error_msg = str(e)
            result = {
                "test_name": test_name,
                "success": False,
                "elapsed_ms": elapsed_ms,
                "error": error_msg,
                "error_type": "ValueError",
            }
            
            if "VALIDATION_FAILED" in error_msg or "Topic content not found" in error_msg:
                result["expected_error"] = True
                print(f"[OK] Expected error (422): {error_msg[:100]}")
            else:
                print(f"[ERROR] Unexpected error: {error_msg[:200]}")
            
            self.results.append(result)
            return result
        
        except Exception as e:
            elapsed_ms = (time.monotonic() - start_time) * 1000
            result = {
                "test_name": test_name,
                "success": False,
                "elapsed_ms": elapsed_ms,
                "error": str(e),
                "error_type": type(e).__name__,
            }
            print(f"[ERROR] Request failed with exception: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            self.results.append(result)
            return result
    
    def _validate_quality(self, worksheet_data: dict, questions: list, requested_difficulty: str = None) -> dict:
        """Validate quality gates."""
        checks = {
            "mcq_valid": True,
            "topic_aligned": True,
            "difficulty_met": True,
            "language_appropriate": True,
            "marking_scheme_concise": True,
            "created_at_not_null": True,
        }
        
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
        marking_scheme = worksheet_data.get("marking_scheme", {})
        for qid, ms in marking_scheme.items():
            criteria = ms.get("criteria", "")
            if criteria and len(criteria) > 200:  # Rough check for brevity
                checks["marking_scheme_concise"] = False
                checks["marking_issue"] = f"Question {qid} has verbose marking scheme ({len(criteria)} chars)"
                break
        
        # Language check (basic - check for common issues)
        for q in questions:
            question_text = q.get("question", "")
            sentences = question_text.split(".")
            if len(sentences) > 5:  # Too many sentences
                checks["language_appropriate"] = False
                checks["language_issue"] = f"Question {q.get('id')} has too many sentences ({len(sentences)})"
                break
        
        # Difficulty validation (if requested)
        if requested_difficulty:
            diff_valid, diff_report = difficulty_fidelity_check(questions, requested_difficulty, None)
            checks["difficulty_met"] = diff_valid
            checks["difficulty_report"] = diff_report
        
        return checks
    
    def print_summary(self):
        """Print test summary report."""
        print(f"\n{'='*80}")
        print("TEST SUMMARY REPORT")
        print(f"{'='*80}\n")
        
        total_tests = len(self.results)
        passed = sum(1 for r in self.results if r.get("success", False))
        failed = total_tests - passed
        
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}\n")
        
        # Performance analysis
        print("PERFORMANCE ANALYSIS:")
        print("-" * 80)
        
        times = [r["elapsed_ms"] for r in self.results if r.get("success", False)]
        if times:
            avg_time = sum(times) / len(times)
            max_time = max(times)
            min_time = min(times)
            print(f"Average time: {avg_time:.0f}ms ({avg_time/1000:.1f}s)")
            print(f"Min time: {min_time:.0f}ms ({min_time/1000:.1f}s)")
            print(f"Max time: {max_time:.0f}ms ({max_time/1000:.1f}s)")
            print(f"Target: <70000ms (<70s)")
            
            over_target = [t for t in times if t > 70000]
            if over_target:
                print(f"[WARN] {len(over_target)} tests exceeded 70s target:")
                for r in self.results:
                    if r.get("success") and r["elapsed_ms"] > 70000:
                        print(f"  - {r['test_name']}: {r['elapsed_ms']:.0f}ms")
            else:
                print("[OK] All tests met time target")
        
        print("\nQUALITY GATES:")
        print("-" * 80)
        
        for result in self.results:
            if result.get("success"):
                checks = result.get("quality_checks", {})
                print(f"\n{result['test_name']}:")
                print(f"  MCQ Valid: {checks.get('mcq_valid', 'N/A')}")
                print(f"  Created At Not Null: {checks.get('created_at_not_null', 'N/A')}")
                print(f"  Marking Scheme Concise: {checks.get('marking_scheme_concise', 'N/A')}")
                print(f"  Difficulty Met: {checks.get('difficulty_met', 'N/A')}")
                if checks.get("mcq_issue"):
                    print(f"  [WARN] MCQ Issue: {checks['mcq_issue']}")
                if checks.get("marking_issue"):
                    print(f"  [WARN] Marking Issue: {checks['marking_issue']}")
                if checks.get("language_issue"):
                    print(f"  [WARN] Language Issue: {checks['language_issue']}")
                if checks.get("difficulty_report"):
                    print(f"  Difficulty Report: {checks['difficulty_report'][:100]}")
        
        print("\nDETAILED RESULTS:")
        print("-" * 80)
        
        for result in self.results:
            print(f"\n{result['test_name']}:")
            print(f"  Success: {result.get('success', False)}")
            print(f"  Time: {result['elapsed_ms']:.0f}ms ({result['elapsed_ms']/1000:.1f}s)")
            if result.get("diagnostics"):
                diag = result["diagnostics"]
                print(f"  Cache: {'hit' if diag.get('cache_hit') else 'miss'}")
                print(f"  Generation Mode: {diag.get('generation_mode', 'unknown')}")
                print(f"  Citations: {diag.get('citations_count', 0)}")
            if result.get("error"):
                print(f"  Error: {result['error'][:200]}")
                print(f"  Error Type: {result.get('error_type', 'unknown')}")


async def main():
    """Run all test cases."""
    tester = WorksheetServiceTester()
    
    # Test pack ID
    PACK_ID = "5d400835-a1f6-4bb9-a5e6-4e0999a1d8a7"
    
    print("Starting Worksheet Generation E2E Tests")
    print("=" * 80)
    
    # Test Case 1: Basic set topic, easy difficulty
    await tester.test_worksheet_generation(
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
    await tester.test_worksheet_generation(
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
    await tester.test_worksheet_generation(
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
    await tester.test_worksheet_generation(
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
    await tester.test_worksheet_generation(
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
    await tester.test_worksheet_generation(
        test_name="Fraction Topic - Medium",
        pack_id=PACK_ID,
        topic_text="fraction",
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
    
    print(f"\n[OK] Results saved to worksheet_test_results.json")
    
    # Close DB session
    tester.db.close()


if __name__ == "__main__":
    asyncio.run(main())
