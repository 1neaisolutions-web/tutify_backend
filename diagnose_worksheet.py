"""
Diagnose worksheet generation: login as teacher, call worksheet/generate, inspect response.
Set env BASE to override (e.g. BASE=http://127.0.0.1:8001/api/v1).
"""
import os
import requests
import json

BASE = os.environ.get("BASE", "http://127.0.0.1:8000/api/v1")
EMAIL = "test1@gmail.com"
PASSWORD = "123456789aA!"
PACK_ID = "5d400835-a1f6-4bb9-a5e6-4e0999a1d8a7"

def main():
    print("1. Login...")
    r = requests.post(
        f"{BASE}/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        timeout=10,
    )
    print(f"   Status: {r.status_code}")
    data = r.json()

    if r.status_code != 200:
        print(f"   Response: {data}")
        return

    # Handle challenge (multiple memberships)
    token = None
    if data.get("status") == "SUCCESS" and data.get("access_token"):
        token = data["access_token"]
        print("   Got access_token (single membership)")
    elif data.get("status") == "CHALLENGE" and data.get("login_token") and data.get("memberships"):
        print("   Challenge: selecting first membership...")
        memberships = data["memberships"]
        m = memberships[0]
        r2 = requests.post(
            f"{BASE}/auth/login",
            json={
                "login_token": data["login_token"],
                "selected_membership_id": str(m["id"]),
                "scope_type": m.get("scope_type", "institution"),
            },
            timeout=10,
        )
        if r2.status_code != 200:
            print(f"   Step 2 failed: {r2.status_code} {r2.text}")
            return
        data2 = r2.json()
        token = data2.get("access_token")
        if not token:
            print(f"   No access_token: {data2}")
            return
        print("   Got access_token (after challenge)")
    else:
        print(f"   Unexpected response: {data}")
        return

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    print("\n2. Generate worksheet (topic: PRIME FACTORS)...")
    payload = {
        "pack_id": PACK_ID,
        "topic_text": "PRIME FACTORS",
        "num_questions": 10,
        "question_types": ["mcq", "short_answer"],
        "difficulty_mix": {"easy": 0.3, "medium": 0.5, "hard": 0.2},
        "force_regenerate": True,
    }
    r3 = requests.post(
        f"{BASE}/worksheets/generate",
        headers=headers,
        json=payload,
        timeout=180,
    )
    print(f"   Status: {r3.status_code}")

    if r3.status_code != 200:
        print(f"   Error: {r3.text[:500]}")
        try:
            err_detail = r3.json().get("detail", r3.text)
            print("\n5. Result: FAIL")
            print(f"   - Server returned {r3.status_code}: {err_detail[:300]}")
        except Exception:
            print("\n5. Result: FAIL")
            print(f"   - Server returned {r3.status_code}")
        print("Done.")
        return

    ws = r3.json()
    questions = ws.get("questions", [])
    citations = ws.get("citations") or []
    print(f"   Worksheet id: {ws.get('id')}")
    print(f"   Topic: {ws.get('topic_text')}")
    print(f"   Questions count: {len(questions)}")
    print(f"   Citations count: {len(citations)}")

    print("\n3. Top 3 citations (chunk_id, page_range, document_id):")
    for i, c in enumerate(citations[:3], 1):
        print(f"   [{i}] chunk_id={c.get('chunk_id')}, page_range={c.get('page_range')}, document_id={c.get('document_id')}")

    print("\n4. Diagnosis:")
    if questions:
        q1 = (questions[0].get("question") or "")[:120]
        q2 = (questions[1].get("question") or "")[:120] if len(questions) > 1 else ""
        print(f"   Q1 (first 120 chars): {q1!r}")
        if q2:
            print(f"   Q2 (first 120 chars): {q2!r}")
    front_matter_page_ranges = ("1-3", "1-2", "1", "2-3", "1-4", "1-5", "1-6", "1-7", "1-8", "2-4", "3-5", "4-6", "5-7", "6-8")
    first_citation_page = citations[0].get("page_range") if citations else None
    from_front = first_citation_page in front_matter_page_ranges if first_citation_page else False
    has_generic = any("Based on the content" in (q.get("question") or "") for q in questions) if questions else False
    count_ok = len(questions) >= 10

    passed = count_ok and not has_generic and not from_front
    print("\n5. Result: " + ("PASS" if passed else "FAIL"))
    if not count_ok:
        print(f"   - FAIL: question count {len(questions)} < 10")
    if has_generic:
        print("   - FAIL: questions contain 'Based on the content...' (generic fallback)")
    if from_front:
        print(f"   - FAIL: citations from front matter (page_range={first_citation_page})")
    if passed:
        print("   - Questions are topic-specific, count >= 10, citations from chapter pages.")
    print("Done.")

if __name__ == "__main__":
    main()
