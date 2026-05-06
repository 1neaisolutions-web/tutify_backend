"""Credit gating for teacher_quiz generate + regenerate_question."""
import pytest
from uuid import UUID

from app.domains.subscriptions.feature_keys import QUIZ_GENERATE, QUIZ_REGENERATE_QUESTION
from app.domains.subscriptions.models import UserCreditTransaction
from app.domains.subscriptions.services.credit_service import CreditService
from app.domains.teacher_quiz.generation import GeneratedQuestion, QuizGenerationService
from app.domains.teacher_quiz.service import TeacherQuizService

from tests.teacher_tools._credit_gating_fixtures import seed_feature_cost, teacher_client_and_user, top_up


@pytest.fixture
def client_with_auth(teacher_client_and_user):
    client, _user, _db = teacher_client_and_user
    return client


@pytest.fixture
def auth_user(teacher_client_and_user):
    _client, user, _db = teacher_client_and_user
    return user


@pytest.fixture
def db_session(teacher_client_and_user):
    _client, _user, db = teacher_client_and_user
    return db


def _patch_stub_generate(monkeypatch):
    async def fake_generate_questions(self, **kwargs):
        qs = [
            GeneratedQuestion(qid="q1", qtype="mcq", prompt="Q1?", points=2.0, options=["A", "B", "C", "D"]),
        ]
        return qs, [], {"model_used": "test", "provider": "test"}

    monkeypatch.setattr(QuizGenerationService, "generate_questions", fake_generate_questions, raising=True)


def _create_quiz(client):
    r = client.post(
        "/api/v1/teacher-tools/quizzes",
        json={
            "title": "Credit gate quiz",
            "subject": "Science",
            "grade": "Year 7",
            "classes": ["y7blue"],
            "generateWithoutSources": True,
            "sourceBookIds": [],
            "scopeTopics": ["Cells"],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_generate_quiz_402_when_no_credits(client_with_auth, db_session, monkeypatch):
    seed_feature_cost(db_session, QUIZ_GENERATE, 10)
    _patch_stub_generate(monkeypatch)
    quiz_id = _create_quiz(client_with_auth)
    r = client_with_auth.post(
        f"/api/v1/teacher-tools/quizzes/{quiz_id}/generate",
        json={"questionCount": 1},
    )
    assert r.status_code == 402, r.text
    d = r.json()["detail"]
    assert d["error"] == "insufficient_credits"
    assert d["required"] == 10


@pytest.mark.asyncio
async def test_generate_quiz_debits_and_records_txn(client_with_auth, db_session, auth_user, monkeypatch):
    seed_feature_cost(db_session, QUIZ_GENERATE, 10)
    top_up(db_session, auth_user.id, 50)
    _patch_stub_generate(monkeypatch)
    quiz_id = _create_quiz(client_with_auth)
    r = client_with_auth.post(
        f"/api/v1/teacher-tools/quizzes/{quiz_id}/generate",
        json={"questionCount": 1},
    )
    assert r.status_code == 200, r.text
    bal = CreditService(db_session).get_or_create_balance(auth_user.id)
    assert bal.balance == 40
    txn = (
        db_session.query(UserCreditTransaction)
        .filter(UserCreditTransaction.user_id == auth_user.id, UserCreditTransaction.feature_key == QUIZ_GENERATE)
        .order_by(UserCreditTransaction.created_at.desc())
        .first()
    )
    assert txn is not None
    assert txn.amount == -10


@pytest.mark.asyncio
async def test_generate_quiz_no_charge_when_generation_fails(client_with_auth, db_session, auth_user, monkeypatch):
    seed_feature_cost(db_session, QUIZ_GENERATE, 10)
    top_up(db_session, auth_user.id, 50)

    async def boom(self, **kwargs):
        raise RuntimeError("llm failed")

    monkeypatch.setattr(
        "app.domains.teacher_quiz.generation.QuizGenerationService.generate_questions",
        boom,
        raising=False,
    )
    quiz_id = _create_quiz(client_with_auth)
    r = client_with_auth.post(
        f"/api/v1/teacher-tools/quizzes/{quiz_id}/generate",
        json={"questionCount": 1},
    )
    assert r.status_code in (500, 502)
    bal = CreditService(db_session).get_or_create_balance(auth_user.id)
    assert bal.balance == 50


@pytest.mark.asyncio
async def test_generate_quiz_succeeds_when_charge_raises(client_with_auth, db_session, auth_user, monkeypatch):
    seed_feature_cost(db_session, QUIZ_GENERATE, 10)
    top_up(db_session, auth_user.id, 50)
    _patch_stub_generate(monkeypatch)

    def boom_charge(self, *a, **kw):
        raise RuntimeError("charge boom")

    monkeypatch.setattr(CreditService, "charge", boom_charge, raising=True)
    quiz_id = _create_quiz(client_with_auth)
    r = client_with_auth.post(
        f"/api/v1/teacher-tools/quizzes/{quiz_id}/generate",
        json={"questionCount": 1},
    )
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_regenerate_question_402_when_no_credits(client_with_auth, db_session, auth_user, monkeypatch):
    seed_feature_cost(db_session, QUIZ_GENERATE, 10)
    seed_feature_cost(db_session, QUIZ_REGENERATE_QUESTION, 2)
    top_up(db_session, auth_user.id, 100)
    _patch_stub_generate(monkeypatch)
    quiz_id = _create_quiz(client_with_auth)
    gen = client_with_auth.post(
        f"/api/v1/teacher-tools/quizzes/{quiz_id}/generate",
        json={"questionCount": 1},
    )
    assert gen.status_code == 200, gen.text
    qid = gen.json()["quiz"]["questionStubs"][0]["id"]

    b = CreditService(db_session).get_or_create_balance(auth_user.id)
    b.balance = 0
    db_session.commit()

    r = client_with_auth.post(f"/api/v1/teacher-tools/quizzes/{quiz_id}/questions/{qid}/regenerate")
    assert r.status_code == 402
    assert r.json()["detail"]["required"] == 2


@pytest.mark.asyncio
async def test_regenerate_question_charges_on_success(client_with_auth, db_session, auth_user, monkeypatch):
    seed_feature_cost(db_session, QUIZ_GENERATE, 10)
    seed_feature_cost(db_session, QUIZ_REGENERATE_QUESTION, 2)
    top_up(db_session, auth_user.id, 100)
    _patch_stub_generate(monkeypatch)
    quiz_id = _create_quiz(client_with_auth)
    gen = client_with_auth.post(
        f"/api/v1/teacher-tools/quizzes/{quiz_id}/generate",
        json={"questionCount": 1},
    )
    assert gen.status_code == 200, gen.text
    qid = gen.json()["quiz"]["questionStubs"][0]["id"]

    async def stub_regen(self, current_user, quiz_id, question_id, idempotency_key=None):
        _ = question_id
        q = self.repo.get_quiz(current_user.tenant_id, quiz_id, with_questions=True)
        assert q is not None
        return q

    monkeypatch.setattr(TeacherQuizService, "regenerate_question", stub_regen, raising=True)

    before = CreditService(db_session).get_or_create_balance(auth_user.id).balance
    r = client_with_auth.post(f"/api/v1/teacher-tools/quizzes/{quiz_id}/questions/{qid}/regenerate")
    assert r.status_code == 200, r.text
    after = CreditService(db_session).get_or_create_balance(auth_user.id).balance
    assert after == before - 2
