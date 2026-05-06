"""Shared fixtures for teacher-tools credit gating tests."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import get_db
from app.domains.auth.dependencies import get_current_user
from app.domains.auth.models import Tenant, TenantType, User, UserStatus, Role, RoleName, RoleScope, UserRole
from app.domains.subscriptions.models import FeatureCreditCost
from app.domains.subscriptions.services.credit_service import CreditService


@pytest.fixture
def teacher_client_and_user(db):
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

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        yield TestClient(app), user, db
    finally:
        app.dependency_overrides.clear()


def seed_feature_cost(db, feature_key: str, base_credits: int) -> None:
    db.add(
        FeatureCreditCost(
            id=uuid4(),
            feature_key=feature_key,
            display_name=feature_key,
            module_name="Teacher Tools",
            base_credits=base_credits,
            description=None,
            is_active=True,
        )
    )
    db.commit()


def top_up(db, user_id, credits: int) -> None:
    CreditService(db).top_up(user_id, credits, expires_at=None, source_description="test")
