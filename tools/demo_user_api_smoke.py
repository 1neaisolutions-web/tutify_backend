"""
Demo API smoke: login + learning hub + personalization (no secrets in file).
Usage: set DEMO_TEST_EMAIL and DEMO_TEST_PASSWORD, then:
  python tools/demo_user_api_smoke.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("DEMO_API_BASE", "http://127.0.0.1:8000")


def req(method: str, path: str, body: dict | None = None, token: str | None = None) -> tuple[int, dict]:
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=120) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw) if raw else {"detail": e.reason}
        except json.JSONDecodeError:
            return e.code, {"detail": raw or str(e.reason)}


def main() -> int:
    email = os.environ.get("DEMO_TEST_EMAIL")
    password = os.environ.get("DEMO_TEST_PASSWORD")
    if not email or not password:
        print("Set DEMO_TEST_EMAIL and DEMO_TEST_PASSWORD", file=sys.stderr)
        return 2

    code, login = req("POST", "/api/v1/auth/login", {"email": email, "password": password})
    if code != 200:
        print("LOGIN_FAIL", code, login)
        return 1
    token = login.get("access_token")
    if not token:
        print("LOGIN_NO_TOKEN", login)
        return 1
    print("LOGIN_OK")

    code, home = req("GET", "/api/v1/learning-hub/home", token=token)
    if code != 200:
        print("HOME_FAIL", code, home)
        return 1
    has_pc = "profile_completeness" in home
    pc = home.get("profile_completeness")
    mode = home.get("mode")
    sections = home.get("sections")
    print("HOME_OK", "mode=", mode, "profile_completeness=", "yes" if has_pc else "NO", "score=", (pc or {}).get("score"))
    if not has_pc:
        print("WARN: profile_completeness missing from home (demo UX may show gaps)")
    if sections is not None and isinstance(sections, dict):
        print("SECTIONS_KEYS", list(sections.keys())[:8])

    code, st = req("GET", "/api/v1/personalization/state", token=token)
    if code != 200:
        print("PERSONALIZATION_STATE_FAIL", code, st)
        return 1
    print("PERSONALIZATION_STATE_OK", "version=", st.get("personalization_version"), "status=", st.get("status"))

    print("SMOKE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
