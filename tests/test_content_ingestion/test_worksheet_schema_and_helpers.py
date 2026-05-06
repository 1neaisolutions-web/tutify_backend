"""
Unit tests for worksheet schema (num_questions 1-20, difficulty, skip_cache_write,
WorksheetResponse created_at optional) and worksheet service helpers.
"""
import pytest
from uuid import uuid4
from datetime import datetime, timezone
from pydantic import ValidationError

from app.domains.content_ingestion.schemas import (
    WorksheetGenerateRequest,
    WorksheetResponse,
    WorksheetQuestion,
)
from app.domains.content_ingestion.services.worksheet_service import WorksheetService


class TestWorksheetGenerateRequestSchema:
    """Worksheet generate request: difficulty, num_questions 1-20, skip_cache_write."""

    def test_num_questions_max_20(self):
        req = WorksheetGenerateRequest(pack_id=uuid4(), topic_text="x", num_questions=20)
        assert req.num_questions == 20

    def test_num_questions_over_20_invalid(self):
        with pytest.raises(ValidationError):
            WorksheetGenerateRequest(pack_id=uuid4(), topic_text="x", num_questions=21)

    def test_num_questions_min_1(self):
        req = WorksheetGenerateRequest(pack_id=uuid4(), topic_text="x", num_questions=1)
        assert req.num_questions == 1

    def test_difficulty_optional(self):
        req = WorksheetGenerateRequest(
            pack_id=uuid4(),
            topic_text="x",
            difficulty="medium",
        )
        assert req.difficulty == "medium"

    def test_skip_cache_write_optional(self):
        req = WorksheetGenerateRequest(
            pack_id=uuid4(),
            topic_text="x",
            skip_cache_write=True,
        )
        assert req.skip_cache_write is True


class TestWorksheetResponseSchema:
    """WorksheetResponse must accept created_at=None (no-DB / cache-disabled phase)."""

    def test_created_at_optional_none(self):
        """Response with created_at=None must validate (e.g. when worksheet not persisted)."""
        pid = uuid4()
        resp = WorksheetResponse(
            id=uuid4(),
            pack_id=pid,
            topic_id=None,
            topic_text="Algebra",
            grade="6",
            subject="Mathematics",
            questions=[
                WorksheetQuestion(
                    id="q1",
                    type="mcq",
                    question="What is 2+2?",
                    correct_answer="4",
                    points=1,
                    difficulty="easy",
                    math_content=False,
                )
            ],
            answer_key={"q1": "4"},
            marking_scheme={"q1": {"points": 1, "criteria": "Correct."}},
            citations=None,
            created_at=None,
        )
        assert resp.created_at is None

    def test_created_at_optional_datetime(self):
        """Response with created_at set must validate and serialize."""
        pid = uuid4()
        now = datetime.now(timezone.utc)
        resp = WorksheetResponse(
            id=uuid4(),
            pack_id=pid,
            topic_id=None,
            topic_text="Algebra",
            grade="6",
            subject="Mathematics",
            questions=[
                WorksheetQuestion(
                    id="q1",
                    type="short_answer",
                    question="Simplify x+x.",
                    correct_answer="2x",
                    points=2,
                    difficulty="medium",
                    math_content=True,
                )
            ],
            answer_key={"q1": "2x"},
            marking_scheme={"q1": {"points": 2, "criteria": "Correct."}},
            citations=None,
            created_at=now,
        )
        assert resp.created_at == now
        # Round-trip: model_dump -> JSON-friendly
        d = resp.model_dump()
        assert d["created_at"] is not None


class TestWorksheetServiceHelpers:
    """Test service helper methods without DB/LLM."""

    def test_resolve_difficulty_mix_single_easy(self):
        # Need a session; we only call _resolve_difficulty_mix which doesn't use db
        from sqlalchemy.orm import Session
        from unittest.mock import MagicMock
        db = MagicMock(spec=Session)
        svc = WorksheetService(db)
        mix = svc._resolve_difficulty_mix("easy", None)
        assert mix == {"easy": 1.0, "medium": 0.0, "hard": 0.0}

    def test_resolve_difficulty_mix_single_medium(self):
        from unittest.mock import MagicMock
        from sqlalchemy.orm import Session
        db = MagicMock(spec=Session)
        svc = WorksheetService(db)
        mix = svc._resolve_difficulty_mix("medium", None)
        assert mix == {"easy": 0.0, "medium": 1.0, "hard": 0.0}

    def test_resolve_difficulty_mix_fallback(self):
        from unittest.mock import MagicMock
        from sqlalchemy.orm import Session
        db = MagicMock(spec=Session)
        svc = WorksheetService(db)
        mix = svc._resolve_difficulty_mix(None, {"easy": 0.2, "medium": 0.5, "hard": 0.3})
        assert mix["easy"] == 0.2 and mix["medium"] == 0.5 and mix["hard"] == 0.3

    def test_resolve_difficulty_mix_default_when_none(self):
        from unittest.mock import MagicMock
        from sqlalchemy.orm import Session
        db = MagicMock(spec=Session)
        svc = WorksheetService(db)
        mix = svc._resolve_difficulty_mix(None, None)
        assert mix["easy"] == 0.3 and mix["medium"] == 0.5 and mix["hard"] == 0.2

    def test_strip_option_letter_prefix(self):
        from unittest.mock import MagicMock
        from sqlalchemy.orm import Session
        db = MagicMock(spec=Session)
        svc = WorksheetService(db)
        assert svc._strip_option_letter_prefix("A) First option") == "First option"
        assert svc._strip_option_letter_prefix("B. Second option") == "Second option"
        assert svc._strip_option_letter_prefix("No prefix") == "No prefix"
        assert svc._strip_option_letter_prefix("") == ""

    def test_signature_hash_includes_difficulty(self):
        """Cache signature must differ by difficulty so easy/hard do not return same cached worksheet."""
        from unittest.mock import MagicMock
        from sqlalchemy.orm import Session
        db = MagicMock(spec=Session)
        svc = WorksheetService(db)
        pack_id = uuid4()
        base = {"pack_id": pack_id, "topic_id": None, "topic_text": "Algebra", "grade": "6", "subject": "Math", "num_questions": 10, "question_types": ["mcq", "short_answer"]}
        h_easy = svc._generate_signature_hash(
            pack_id, None, "Algebra", "6", "Math", {"easy": 1.0, "medium": 0.0, "hard": 0.0},
            base["num_questions"], base["question_types"],
        )
        h_hard = svc._generate_signature_hash(
            pack_id, None, "Algebra", "6", "Math", {"easy": 0.0, "medium": 0.0, "hard": 1.0},
            base["num_questions"], base["question_types"],
        )
        assert h_easy != h_hard

    def test_build_difficulty_contract_easy_medium_hard(self):
        """Difficulty contract section is non-empty for easy/medium/hard."""
        from unittest.mock import MagicMock
        from sqlalchemy.orm import Session
        db = MagicMock(spec=Session)
        svc = WorksheetService(db)
        for level in ("easy", "medium", "hard"):
            contract = svc._build_difficulty_contract(level, None)
            assert "DIFFICULTY CONTRACT" in contract
            assert level.upper() in contract
        # No strict constraint when mix is default
        contract_none = svc._build_difficulty_contract(None, {"easy": 0.3, "medium": 0.5, "hard": 0.2})
        assert contract_none == ""
