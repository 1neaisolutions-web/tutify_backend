"""
Worksheet generation performance test script.
Reproducible scenarios with explicit timeouts. Never hangs.

Scenarios (each run 3 times; with WORKSHEET_CACHE_ENABLED=false, no cache hits):
  1) 10 MCQ, medium
  2) 10 mixed (mcq + short_answer + long_answer), medium
  3) 20 long_answer, hard

Per-request client timeout: 200s by default (backend uses WORKSHEET_GENERATION_TIMEOUT_SECONDS=180).
Output: total_ms, total_sec, status, cache_hit (X-Worksheet-Cache header when cache enabled), request_id.

Usage:
  1. Start backend: python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
  2. Set WORKSHEET_CACHE_ENABLED=false (default) for no DB worksheet_cache reads/writes.
  3. Run: python tools/worksheet_performance_test.py

  Optional env: BASE_URL=http://127.0.0.1:8000 WORKSHEET_TEST_TIMEOUT=200
"""
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import requests

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8000")
PER_REQUEST_TIMEOUT_SEC = float(os.environ.get("WORKSHEET_TEST_TIMEOUT", "200"))
# Optional: limit for quick smoke test (e.g. RUNS=1 SCENARIOS=1)
MAX_RUNS_PER_SCENARIO = int(os.environ.get("RUNS", "3"))
MAX_SCENARIOS = int(os.environ.get("SCENARIOS", "3"))  # 1 = first scenario only

# Test credentials (same as other tools)
TEST_CREDENTIALS = [
    {"email": "test1@gmail.com", "password": "123456789aA!"},
    {"email": "admin@1ne.ai", "password": "Admin123!@#"},
]


def get_token():
    for creds in TEST_CREDENTIALS:
        try:
            r = requests.post(
                f"{BASE_URL}/api/v1/auth/login",
                json=creds,
                timeout=10,
            )
            if r.status_code == 200:
                return r.json().get("access_token")
        except Exception:
            continue
    return None


def get_pack_id(token):
    try:
        r = requests.get(
            f"{BASE_URL}/api/v1/admin/content-packs",
            headers={"Authorization": f"Bearer {token}"},
            params={"is_active": True},
            timeout=10,
        )
    except requests.exceptions.Timeout:
        print("[FAIL] Timeout getting content packs (10s). Backend may be slow or stuck.")
        return None
    except requests.exceptions.ConnectionError:
        print("[FAIL] Connection error. Is the backend running at", BASE_URL, "?")
        return None
    if r.status_code != 200:
        return None
    data = r.json()
    if isinstance(data, list) and data:
        return data[0].get("id")
    return None


def run_one(
    token: str,
    pack_id: str,
    num_questions: int,
    question_types: list,
    difficulty: str,
    topic_text: str = "Introduction to fractions and basic math",
):
    payload = {
        "pack_id": pack_id,
        "topic_text": topic_text,
        "grade": "6",
        "subject": "Mathematics",
        "num_questions": num_questions,
        "question_types": question_types,
        "difficulty": difficulty,
    }
    start = time.monotonic()
    try:
        r = requests.post(
            f"{BASE_URL}/api/v1/worksheets/generate",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload,
            timeout=PER_REQUEST_TIMEOUT_SEC,
        )
        elapsed = time.monotonic() - start
        total_ms = int(elapsed * 1000)
        total_sec = round(elapsed, 2)
        status = r.status_code
        request_id = None
        cache_hit = None
        llm_ms = None
        if status == 200:
            data = r.json()
            nq = len(data.get("questions", []))
            cache_hit = (r.headers.get("X-Worksheet-Cache") or "").strip().lower() == "hit"
            request_id = r.headers.get("X-Request-Id") or request_id
            return {
                "total_ms": total_ms,
                "total_sec": total_sec,
                "status": status,
                "cache_hit": cache_hit,
                "request_id": request_id,
                "n_questions": nq,
            }
        if status == 504:
            try:
                detail = r.json()
                if isinstance(detail, dict):
                    d = detail.get("detail")
                    if isinstance(d, dict):
                        request_id = d.get("request_id")
                    else:
                        request_id = detail.get("request_id")
            except Exception:
                pass
        return {
            "total_ms": total_ms,
            "total_sec": total_sec,
            "status": status,
            "cache_hit": cache_hit,
            "request_id": request_id,
            "n_questions": None,
        }
    except requests.exceptions.Timeout:
        elapsed = time.monotonic() - start
        return {
            "total_ms": int(elapsed * 1000),
            "total_sec": round(elapsed, 2),
            "status": "timeout",
            "cache_hit": None,
            "request_id": None,
            "n_questions": None,
        }
    except Exception as e:
        elapsed = time.monotonic() - start
        return {
            "total_ms": int(elapsed * 1000),
            "total_sec": round(elapsed, 2),
            "status": f"error:{type(e).__name__}",
            "cache_hit": None,
            "request_id": None,
            "n_questions": None,
        }


def main():
    print("=" * 70)
    print("WORKSHEET PERFORMANCE TEST")
    print("=" * 70)
    print(f"BASE_URL={BASE_URL}  PER_REQUEST_TIMEOUT={PER_REQUEST_TIMEOUT_SEC}s")
    print()

    token = get_token()
    if not token:
        print("[FAIL] Could not get auth token. Check backend and credentials.")
        sys.exit(1)
    pack_id = get_pack_id(token)
    if not pack_id:
        print("[FAIL] No content pack found or request timed out.")
        sys.exit(1)
    print(f"[INFO] Using pack_id={pack_id[:8]}...")
    print()

    scenarios = [
        ("10 MCQ, medium", 10, ["mcq"], "medium"),
        ("10 mixed (mcq+short+long), medium", 10, ["mcq", "short_answer", "long_answer"], "medium"),
        ("20 long_answer, hard", 20, ["long_answer"], "hard"),
    ][:MAX_SCENARIOS]

    all_results = []

    for label, num_q, qtypes, diff in scenarios:
        print(f"--- {label} ---")
        for run in range(MAX_RUNS_PER_SCENARIO):
            result = run_one(token, pack_id, num_q, qtypes, diff)
            all_results.append((label, run + 1, result))
            r = result
            cache_tag = " (likely cache hit)" if r.get("cache_hit") else ""
            print(
                f"  Run {run + 1}: total={r['total_ms']} ms ({r['total_sec']} s) status={r['status']}"
                f" n_questions={r.get('n_questions')}{cache_tag}"
            )
            print(f"    request_id={r.get('request_id')} status_code={r['status']} total_ms={r['total_ms']}")
            if r.get("status") == 504 or r.get("status") == "timeout":
                print(f"    TIMEOUT/504 request_id={r.get('request_id')}")
        print()

    # Summary table
    print("=" * 70)
    print("TIMING REPORT (ms and seconds)")
    print("=" * 70)
    print(f"{'Scenario':<45} {'Run':<4} {'total_ms':<10} {'total_sec':<10} {'status':<8} {'cache_hit':<10}")
    print("-" * 70)
    for label, run, r in all_results:
        print(
            f"{label[:44]:<45} {run:<4} {r['total_ms']:<10} {r['total_sec']:<10} "
            f"{str(r['status']):<8} {str(r.get('cache_hit')):<10}"
        )
    print()
    print("Note: Phase timings (signature_hash, cache_lookup, retrieval, llm_call, cache_write)")
    print("      are logged server-side with request_id. Check backend logs for details.")
    print("=" * 70)
    sys.exit(0)


if __name__ == "__main__":
    main()
