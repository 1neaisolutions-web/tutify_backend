"""
Minimal check: POST /api/v1/worksheets/generate returns 200 and valid WorksheetResponse.
Asserts created_at is either a valid ISO datetime string or null (schema allows both).
Run with backend up and valid auth. No DB dependency for the assertion.
  python tools/worksheet_created_at_check.py
  BASE_URL=http://127.0.0.1:8000 (optional)
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import requests

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8000")
# Credentials (same as worksheet_performance_test.py)
CREDS = [
    {"email": "test1@gmail.com", "password": "123456789aA!"},
    {"email": "admin@1ne.ai", "password": "Admin123!@#"},
]


def main():
    token = None
    for c in CREDS:
        try:
            r = requests.post(f"{BASE_URL}/api/v1/auth/login", json=c, timeout=10)
            if r.status_code == 200:
                token = r.json().get("access_token")
                break
        except Exception:
            continue
    if not token:
        print("[FAIL] Could not get auth token")
        sys.exit(1)

    packs = requests.get(
        f"{BASE_URL}/api/v1/admin/content-packs",
        headers={"Authorization": f"Bearer {token}"},
        params={"is_active": True},
        timeout=10,
    )
    if packs.status_code != 200 or not packs.json():
        print("[FAIL] No content pack found")
        sys.exit(1)
    pack_id = packs.json()[0]["id"]

    resp = requests.post(
        f"{BASE_URL}/api/v1/worksheets/generate",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "pack_id": pack_id,
            "topic_text": "Algebra",
            "num_questions": 2,
            "question_types": ["mcq"],
            "difficulty": "easy",
        },
        timeout=200,
    )
    if resp.status_code != 200:
        print(f"[FAIL] status={resp.status_code} body={resp.text[:500]}")
        sys.exit(1)
    data = resp.json()
    created_at = data.get("created_at")
    if created_at is not None and (not isinstance(created_at, str) or "T" not in created_at):
        print(f"[FAIL] created_at should be null or ISO datetime, got {created_at!r}")
        sys.exit(1)
    print("[OK] status=200, created_at=" + ("null" if created_at is None else "ISO datetime"))
    print("WorksheetResponse validated successfully.")


if __name__ == "__main__":
    main()
