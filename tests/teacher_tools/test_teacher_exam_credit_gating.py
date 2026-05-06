"""Credit gating for teacher_exam generate (402 smoke)."""
import pytest

from app.domains.subscriptions.feature_keys import EXAM_GENERATE

from tests.teacher_tools._credit_gating_fixtures import seed_feature_cost, teacher_client_and_user


@pytest.fixture
def client_with_auth(teacher_client_and_user):
    client, _user, _db = teacher_client_and_user
    return client


@pytest.fixture
def db_session(teacher_client_and_user):
    _c, _u, db = teacher_client_and_user
    return db


def _create_exam(client):
    r = client.post(
        "/api/v1/teacher-tools/exams/",
        json={
            "title": "Exam",
            "subject": "Science",
            "grade": "Year 7",
            "classes": ["y7"],
            "generateWithoutSources": True,
            "sourceBookIds": [],
            "scopeTopics": ["Cells"],
            "paper": {
                "objCount": 5,
                "objMarksPer": 1,
                "shortCount": 2,
                "shortMarksPer": 3,
                "longCount": 1,
                "longMarksPer": 5,
                "longSubparts": 2,
            },
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_generate_exam_402_when_no_credits(client_with_auth, db_session):
    seed_feature_cost(db_session, EXAM_GENERATE, 10)
    eid = _create_exam(client_with_auth)
    r = client_with_auth.post(
        f"/api/v1/teacher-tools/exams/{eid}/generate",
        json={"regenerateScope": "all"},
    )
    assert r.status_code == 402, r.text
    assert r.json()["detail"]["required"] == 10
