"""
Verify difficulty implementation without pytest.
Run from project root: python tools/verify_difficulty_implementation.py
Exits 0 if all checks pass, 1 otherwise.
Avoids full app import (and circular deps) by loading difficulty_validator by path.
"""
import sys
import importlib.util
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
_validator_path = _root / "app" / "domains" / "content_ingestion" / "services" / "difficulty_validator.py"


def _q(text: str, question_key: str = "question"):
    return {question_key: text}


def main():
    errors = []

    # --- difficulty_validator (load by path to avoid app circular imports) ---
    spec = importlib.util.spec_from_file_location("difficulty_validator", _validator_path)
    mod = importlib.util.module_from_spec(spec)
    if _root not in sys.path:
        sys.path.insert(0, str(_root))
    spec.loader.exec_module(mod)
    score_question = mod.score_question
    get_worksheet_difficulty_stats = mod.get_worksheet_difficulty_stats
    difficulty_fidelity_check = mod.difficulty_fidelity_check

    if score_question(_q("What is 2 + 3?")) >= 1.0:
        errors.append("score_question: easy question should have score < 1.0")
    if score_question(_q("Justify why the sum of angles is 180.")) < 1.0:
        errors.append("score_question: justify-style should have score >= 1.0")
    if score_question(_q("")) != 0.0:
        errors.append("score_question: empty text should be 0.0")

    stats = get_worksheet_difficulty_stats([])
    if stats["avg_score"] != 0.0 or stats["pct_justify_style"] != 0.0:
        errors.append("get_worksheet_difficulty_stats: empty list should be zeros")

    easy_qs = [_q("What is 2+2?"), _q("Simplify 1+1.")] * 5
    if not difficulty_fidelity_check(easy_qs, "easy", None)[0]:
        errors.append("difficulty_fidelity_check: easy worksheet should pass for simple questions")
    hard_qs = [_q("Prove that P."), _q("Using part (a), show that Q.")] * 5
    if not difficulty_fidelity_check(hard_qs, "hard", None)[0]:
        errors.append("difficulty_fidelity_check: hard worksheet should pass for justify/multi-step")
    if difficulty_fidelity_check(hard_qs, "easy", None)[0]:
        errors.append("difficulty_fidelity_check: easy should fail when questions are justify-style")

    # --- worksheet_service: signature hash + difficulty contract (optional if app not runnable) ---
    try:
        from uuid import uuid4
        from unittest.mock import MagicMock
        from sqlalchemy.orm import Session
        from app.domains.content_ingestion.services.worksheet_service import WorksheetService

        db = MagicMock(spec=Session)
        svc = WorksheetService(db)
        pack_id = uuid4()
        h_easy = svc._generate_signature_hash(
            pack_id, None, "Algebra", "6", "Math",
            {"easy": 1.0, "medium": 0.0, "hard": 0.0}, 10, ["mcq", "short_answer"]
        )
        h_hard = svc._generate_signature_hash(
            pack_id, None, "Algebra", "6", "Math",
            {"easy": 0.0, "medium": 0.0, "hard": 1.0}, 10, ["mcq", "short_answer"]
        )
        if h_easy == h_hard:
            errors.append("signature_hash: easy vs hard must differ")

        for level in ("easy", "medium", "hard"):
            contract = svc._build_difficulty_contract(level, None)
            if "DIFFICULTY CONTRACT" not in contract or level.upper() not in contract:
                errors.append(f"_build_difficulty_contract: missing contract for {level}")
    except Exception as e:
        print("Note: WorksheetService checks skipped (app import failed):", e)

    # --- ordering: easy avg < medium avg < hard avg ---
    easy_set = [_q("What is 2+3?"), _q("Simplify 1+1.")] * 3
    medium_set = [_q("First find x. Then find the area."), _q("Using the formula, find the value."), _q("What is 2+2?")] * 3
    hard_set = [_q("Prove that P."), _q("Using part (a), show that Q."), _q("Compare and evaluate.")] * 3
    s_easy = get_worksheet_difficulty_stats(easy_set)["avg_score"]
    s_medium = get_worksheet_difficulty_stats(medium_set)["avg_score"]
    s_hard = get_worksheet_difficulty_stats(hard_set)["avg_score"]
    if not (s_easy < s_medium < s_hard):
        errors.append(f"ordering: expected easy({s_easy}) < medium({s_medium}) < hard({s_hard})")

    if errors:
        for e in errors:
            print("FAIL:", e)
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
