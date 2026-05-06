"""
Diagnose worksheet generation for topic "algebric expression" (topic drift test).
Expect: 10 questions, at least 8 algebraic-expression related, no HCF/LCM/primes,
citations in a tight page window.
"""
import os
import requests

BASE = os.environ.get("BASE", "http://127.0.0.1:8000/api/v1")
EMAIL = "test1@gmail.com"
PASSWORD = "123456789aA!"
PACK_ID = "5d400835-a1f6-4bb9-a5e6-4e0999a1d8a7"
TOPIC = "algebric expression"

# Drift terms that must NOT appear in algebraic expression questions
DRIFT_TERMS = ["hcf", "lcm", "prime number", "composite", "prime factor", "factorization", "absolute value", "integers"]
# Algebraic terms: at least 8 questions should relate
ALGEBRAIC_TERMS = ["algebraic", "expression", "term", "coefficient", "variable", "simplify", "evaluate", "x", "y", "2x", "3y", "like terms", "constant"]


def main():
    print("1. Login...")
    r = requests.post(
        f"{BASE}/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        timeout=10,
    )
    if r.status_code != 200:
        print(f"   FAIL: {r.status_code} {r.text[:300]}")
        return
    data = r.json()
    token = None
    if data.get("status") == "SUCCESS" and data.get("access_token"):
        token = data["access_token"]
    elif data.get("status") == "CHALLENGE" and data.get("login_token") and data.get("memberships"):
        m = data["memberships"][0]
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
            print(f"   Step 2 FAIL: {r2.status_code}")
            return
        token = r2.json().get("access_token")
    if not token:
        print("   No access_token")
        return
    print("   Got access_token")

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    print(f"\n2. Generate worksheet (topic: {TOPIC!r})...")
    payload = {
        "pack_id": PACK_ID,
        "topic_text": TOPIC,
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
            err = r3.json().get("detail", r3.text)
            print("\nResult: FAIL")
            print(f"   {err[:400]}")
        except Exception:
            print("\nResult: FAIL")
        return

    ws = r3.json()
    questions = ws.get("questions", [])
    citations = ws.get("citations") or []

    print(f"   Worksheet id: {ws.get('id')}")
    print(f"   Topic: {ws.get('topic_text')}")
    print(f"   Questions count: {len(questions)}")
    print(f"   Citations count: {len(citations)}")

    # Chosen chapter page range + relevance (from response)
    chapter_range = ws.get("chapter_page_range") or "N/A"
    relevance_sim = ws.get("relevance_avg_sim")
    relevance_kw = ws.get("relevance_keyword_hits")
    print(f"\n3. Chosen chapter page_range(s): {chapter_range}")
    print(f"   Relevance: avg_sim={relevance_sim}, keyword_hit_count={relevance_kw}")

    print("\n4. Top 3 citations (chunk_id, page_range, document_id):")
    for i, c in enumerate(citations[:3], 1):
        print(f"   [{i}] chunk_id={c.get('chunk_id')}, page_range={c.get('page_range')}, document_id={c.get('document_id')}")

    print("\n5. First 3 question previews:")
    for i, q in enumerate(questions[:3], 1):
        text = (q.get("question") or q.get("question_text") or "")[:120]
        print(f"   Q{i}: {text!r}")

    # Validation
    count_ok = len(questions) >= 10
    algebraic_count = 0
    drift_count = 0
    for q in questions:
        qtext = (q.get("question") or q.get("question_text") or "").lower()
        if any(t in qtext for t in ALGEBRAIC_TERMS):
            algebraic_count += 1
        if any(t in qtext for t in DRIFT_TERMS):
            drift_count += 1

    # Citation spread: page ranges should be in a tight window (e.g. span <= 15 pages)
    page_nums = []
    for c in citations:
        pr = c.get("page_range") or ""
        if "-" in pr:
            a, b = pr.split("-", 1)
            try:
                page_nums.extend([int(a.strip()), int(b.strip())])
            except ValueError:
                pass
        else:
            try:
                page_nums.append(int(pr.strip()))
            except ValueError:
                pass
    span = max(page_nums) - min(page_nums) if page_nums else 0
    tight_window = span <= 20 if page_nums else True

    passed = count_ok and algebraic_count >= 8 and drift_count == 0 and tight_window
    print("\n6. Result: " + ("PASS" if passed else "FAIL"))
    if not count_ok:
        print(f"   - Question count {len(questions)} < 10")
    if algebraic_count < 8:
        print(f"   - Algebraic-expression related: {algebraic_count}/10 (need >= 8)")
    if drift_count > 0:
        print(f"   - Drift (HCF/LCM/primes/etc): {drift_count} questions contain forbidden terms")
    if not tight_window and page_nums:
        print(f"   - Citation spread: {span} pages (should be tight window <= 20)")
    if passed:
        print("   - 10 questions, >= 8 algebraic, no drift, citations in tight window.")
    print("Done.")


if __name__ == "__main__":
    main()
