import pytest
from uuid import uuid4
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app
from app.db.session import get_db
from app.domains.auth.dependencies import get_current_user
from app.domains.auth.models import Tenant, TenantType, User, UserStatus, Role, RoleName, RoleScope, UserRole
from app.domains.subscriptions.services.credit_service import CreditService


@pytest.fixture
def client_with_auth(db):
    """
    TestClient with DB + auth overridden. Inserts a teacher user + role rows so
    require_any_role('teacher', ...) passes.
    """
    tenant = Tenant(
        id=uuid4(),
        name="T",
        slug="t",
        type=TenantType.ORGANIZATION,
        parent_tenant_id=None,
        hierarchy_path="/t/",
        settings=None,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(tenant)

    user = User(
        id=uuid4(),
        tenant_id=tenant.id,
        email="teacher@example.com",
        password_hash="x",
        first_name="T",
        last_name="E",
        full_name="Teacher",
        status=UserStatus.ACTIVE,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(user)

    role = Role(
        id=uuid4(),
        name=RoleName.TEACHER,
        scope=RoleScope.ORGANIZATION,
        description="Teacher",
        is_system_role=True,
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(role)

    ur = UserRole(
        id=uuid4(),
        user_id=user.id,
        role_id=role.id,
        tenant_id=tenant.id,
        granted_by=None,
        granted_at=datetime.now(timezone.utc),
    )
    db.add(ur)

    db.commit()

    # Generate routes require credits; give enough for patched LLM tests.
    CreditService(db).top_up(user.id, 500, expires_at=None, source_description="pytest")

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_quiz_crud_happy_path(client_with_auth, monkeypatch):
    client = client_with_auth

    # Create
    create_payload = {
        "title": "Topic check quiz",
        "subject": "Mathematics",
        "grade": "Grade 8",
        "classes": ["g8c"],
        "timeLimitMinutes": 30,
        "status": "draft",
        "sourceBookIds": [],
        "scopeTopics": [],
        "generateWithoutSources": True,
    }
    r = client.post("/api/v1/teacher-tools/quizzes", json=create_payload)
    assert r.status_code == 201, r.text
    q = r.json()
    assert q["title"] == "Topic check quiz"
    quiz_id = q["id"]

    # List
    r = client.get("/api/v1/teacher-tools/quizzes")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 1

    # Patch
    r = client.patch(f"/api/v1/teacher-tools/quizzes/{quiz_id}", json={"status": "published"})
    assert r.status_code == 200
    assert r.json()["status"] == "published"

    # Duplicate
    r = client.post(f"/api/v1/teacher-tools/quizzes/{quiz_id}/duplicate")
    assert r.status_code == 200
    dup_id = r.json()["id"]
    assert dup_id != quiz_id

    # Delete duplicate
    r = client.delete(f"/api/v1/teacher-tools/quizzes/{dup_id}")
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_quiz_generate_uses_service_layer(client_with_auth, monkeypatch):
    client = client_with_auth

    # Create quiz
    r = client.post(
        "/api/v1/teacher-tools/quizzes",
        json={
            "title": "Gen quiz",
            "subject": "Science",
            "grade": "Year 7",
            "classes": ["y7blue"],
            "generateWithoutSources": True,
            "sourceBookIds": [],
            "scopeTopics": ["Cells"],
        },
    )
    quiz_id = r.json()["id"]

    # Patch generator to avoid outbound LLM calls.
    from app.domains.teacher_quiz.generation import GeneratedQuestion

    async def fake_generate_questions(self, **kwargs):
        qs = [
            GeneratedQuestion(qid="q1", qtype="mcq", prompt="Q1?", points=2.0, options=["A", "B", "C", "D"]),
            GeneratedQuestion(qid="q2", qtype="tf", prompt="Q2?", points=1.0, options=None),
        ]
        return qs, ["fake"], {"model_used": "test", "provider": "test"}

    from app.domains.teacher_quiz.generation import QuizGenerationService

    monkeypatch.setattr(QuizGenerationService, "generate_questions", fake_generate_questions, raising=True)

    r = client.post(f"/api/v1/teacher-tools/quizzes/{quiz_id}/generate", json={"questionCount": 2})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True
    assert data["quiz"]["questions"] == 2
    assert len(data["quiz"]["questionStubs"]) == 2

