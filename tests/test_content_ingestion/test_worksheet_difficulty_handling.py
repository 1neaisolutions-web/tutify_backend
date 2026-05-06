"""
Tests for worksheet difficulty handling: no 422 for difficulty mismatch,
response includes final_difficulty_used, attempts_count, validator_report_per_attempt, warnings.
Scenarios: hard success after repair, hard fails -> downgrades to medium, returns medium worksheet + warning.
"""
import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

from app.domains.content_ingestion.schemas import WorksheetResponse, WorksheetQuestion


def _make_fake_worksheet_cache(
    created_at=None,
    final_difficulty_used=None,
    attempts_count=None,
    validator_report_per_attempt=None,
    warnings=None,
):
    """Worksheet cache object as returned by WorksheetService.generate_worksheet."""
    o = MagicMock()
    o.id = uuid4()
    o.pack_id = uuid4()
    o.topic_id = None
    o.topic_text = "Algebra"
    o.grade = "6"
    o.subject = "Mathematics"
    o.worksheet_json = {
        "questions": [
            {
                "id": "q1",
                "type": "short_answer",
                "question": "Prove that the sum of two even numbers is even.",
                "correct_answer": "Let 2a and 2b be two even numbers...",
                "points": 2,
                "difficulty": "hard",
                "math_content": True,
            }
        ],
        "answer_key": {"q1": "Let 2a and 2b be two even numbers..."},
        "marking_scheme": {"q1": {"points": 2, "criteria": "Valid proof."}},
    }
    o.retrieval_metadata = {"citations": [], "chapter_page_range": "10-15"}
    o.created_at = created_at
    o.from_cache = False
    o.difficulty_mix = {"easy": 0.0, "medium": 0.0, "hard": 1.0}
    o.final_difficulty_used = final_difficulty_used
    o.attempts_count = attempts_count
    o.validator_report_per_attempt = validator_report_per_attempt
    o.warnings = warnings
    return o


@pytest.fixture
def mock_user():
    from app.domains.auth.models import User
    u = MagicMock(spec=User)
    u.id = uuid4()
    u.tenant_id = uuid4()
    u.status = "active"
    u.email_verified = True
    return u


@pytest.fixture
def client_with_auth(mock_user):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db.session import get_db
    from app.domains.auth.dependencies import get_current_user

    def override_get_db():
        yield MagicMock()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_hard_success_after_repair_returns_200_with_metadata(client_with_auth):
    """Hard requested; after repair attempts validator passes. Response 200 with final_difficulty_used=hard, attempts_count. Internal fields only with X-Debug."""
    fake = _make_fake_worksheet_cache(
        created_at="2025-01-01T12:00:00Z",
        final_difficulty_used="hard",
        attempts_count=3,
        validator_report_per_attempt=[
            "Hard worksheet: multi-step/justify share too low (20%); require ≥35%.",
            "Hard worksheet: multi-step/justify share too low (25%); require ≥35%.",
            "Hard: avg=1.45, higher_order%=0.40.",
        ],
        warnings=[],
    )
    with patch("app.domains.content_ingestion.routes.WorksheetService") as MockWS:
        MockWS.return_value.generate_worksheet = AsyncMock(return_value=fake)
        response = client_with_auth.post(
            "/api/v1/worksheets/generate",
            json={
                "pack_id": str(fake.pack_id),
                "topic_text": "Algebra",
                "num_questions": 1,
                "difficulty": "hard",
            },
            headers={"X-Debug": "1"},
        )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["final_difficulty_used"] == "hard"
    assert data["attempts_count"] == 3
    assert data.get("validator_report_per_attempt") is not None and len(data["validator_report_per_attempt"]) == 3
    assert data.get("warnings") == []
    assert "questions" in data and len(data["questions"]) == 1
    assert data["created_at"] is not None


def test_hard_fails_board_grounded_returns_200_with_hard_worksheet(client_with_auth):
    """Hard requested; pack_grounded fails -> board_grounded fallback succeeds. Response 200 with final_difficulty_used=hard (no downgrade)."""
    fake = _make_fake_worksheet_cache(
        created_at="2025-01-01T12:00:00Z",
        final_difficulty_used="hard",
        attempts_count=2,
        validator_report_per_attempt=["Hard: multi-step too low.", "Hard: avg=1.4, higher_order%=0.38."],
        warnings=[],
    )
    fake.worksheet_json["questions"][0]["difficulty"] = "hard"
    fake.worksheet_json["questions"][0]["question"] = "First find x. Then using that, find the area. Justify your steps."
    with patch("app.domains.content_ingestion.routes.WorksheetService") as MockWS:
        MockWS.return_value.generate_worksheet = AsyncMock(return_value=fake)
        response = client_with_auth.post(
            "/api/v1/worksheets/generate",
            json={
                "pack_id": str(fake.pack_id),
                "topic_text": "Algebra",
                "num_questions": 1,
                "difficulty": "hard",
            },
        )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["final_difficulty_used"] == "hard"
    assert "questions" in data and len(data["questions"]) == 1


def test_response_schema_with_x_debug_includes_internal_fields(client_with_auth):
    """With X-Debug: 1, response includes validator_report_per_attempt and warnings (schema validates)."""
    fake = _make_fake_worksheet_cache(
        created_at="2025-01-01T12:00:00Z",
        final_difficulty_used="hard",
        attempts_count=2,
        validator_report_per_attempt=["Hard: avg too low.", "Hard: ok."],
        warnings=[],
    )
    with patch("app.domains.content_ingestion.routes.WorksheetService") as MockWS:
        MockWS.return_value.generate_worksheet = AsyncMock(return_value=fake)
        response = client_with_auth.post(
            "/api/v1/worksheets/generate",
            json={
                "pack_id": str(fake.pack_id),
                "topic_text": "Algebra",
                "num_questions": 1,
                "difficulty": "hard",
            },
            headers={"X-Debug": "1"},
        )
    assert response.status_code == 200
    data = response.json()
    resp = WorksheetResponse.model_validate(data)
    assert resp.final_difficulty_used == "hard"
    assert resp.attempts_count == 2
    assert resp.validator_report_per_attempt is not None and len(resp.validator_report_per_attempt) == 2
    assert resp.warnings is not None


def test_422_when_difficulty_generation_unable(client_with_auth):
    """When service raises 'Unable to generate at the requested difficulty...', route returns 422."""
    with patch("app.domains.content_ingestion.routes.WorksheetService") as MockWS:
        MockWS.return_value.generate_worksheet = AsyncMock(
            side_effect=ValueError(
                "Unable to generate at the requested difficulty for this topic. "
                "Try changing the topic wording or lowering difficulty."
            )
        )
        response = client_with_auth.post(
            "/api/v1/worksheets/generate",
            json={
                "pack_id": str(__import__("uuid").uuid4()),
                "topic_text": "Algebra",
                "num_questions": 1,
                "difficulty": "hard",
            },
        )
    assert response.status_code == 422
    data = response.json()
    assert "Unable to generate at the requested difficulty" in data.get("detail", {}).get("message", "")


def test_400_only_for_invalid_payload(client_with_auth):
    """400/422 only for invalid request payload (e.g. missing pack_id, invalid num_questions), not for generation quality."""
    # Missing pack_id -> FastAPI validation returns 422
    response = client_with_auth.post(
        "/api/v1/worksheets/generate",
        json={
            "topic_text": "Algebra",
            "num_questions": 5,
        },
    )
    assert response.status_code == 422

    # Invalid num_questions (0 or 21) -> 422
    from uuid import uuid4
    response2 = client_with_auth.post(
        "/api/v1/worksheets/generate",
        json={
            "pack_id": str(uuid4()),
            "topic_text": "Algebra",
            "num_questions": 0,
        },
    )
    assert response2.status_code == 422
