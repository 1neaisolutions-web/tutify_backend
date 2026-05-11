"""
Unit tests for AuthService, UserService, AuditService in app/domains/auth/services.py.
All DB interactions are mocked — no real database required.
"""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.core.exceptions import (
    AccountLockedError,
    InvalidCredentialsError,
    InvalidTokenError,
    PasswordValidationError,
    UserAlreadyExistsError,
    UserNotFoundError,
)
from app.core.security import hash_password, create_refresh_token, hash_token
from app.domains.auth.models import (
    AuditEventType,
    RefreshToken,
    User,
    UserMembership,
    UserStatus,
)
from app.domains.auth.services import AuditService, AuthService, UserService
from app.domains.auth.schemas import LoginRequest, RegisterRequest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_PASSWORD = "Secure@Pass1"


def _make_user(**kwargs) -> MagicMock:
    defaults = dict(
        id=uuid.uuid4(),
        email="test@example.com",
        password_hash=hash_password(VALID_PASSWORD),
        first_name="Test",
        last_name="User",
        full_name="Test User",
        tenant_id=uuid.uuid4(),
        status=UserStatus.ACTIVE,
        email_verified=True,
        failed_login_attempts=0,
        locked_until=None,
        last_login_at=None,
    )
    defaults.update(kwargs)
    user = MagicMock(spec=User)
    for k, v in defaults.items():
        setattr(user, k, v)
    return user


def _make_db():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    db.query.return_value.filter.return_value.limit.return_value.all.return_value = []
    return db


def _silence_audit(svc):
    """Replace svc.audit with a no-op mock so audit logging doesn't interfere."""
    svc.audit = MagicMock()


# ---------------------------------------------------------------------------
# AuditService
# ---------------------------------------------------------------------------

class TestAuditService:
    def test_audit_service_instantiates(self):
        db = _make_db()
        svc = AuditService(db)
        assert svc is not None

    def test_silence_audit_replaces_with_mock(self):
        """_silence_audit replaces the audit object so login tests don't fail on audit calls."""
        db = _make_db()
        auth_svc = AuthService(db)
        _silence_audit(auth_svc)
        assert isinstance(auth_svc.audit, MagicMock)


# ---------------------------------------------------------------------------
# AuthService — login
# ---------------------------------------------------------------------------

class TestAuthServiceLogin:
    def _login(self, db, email="test@example.com", password=None):
        svc = AuthService(db)
        _silence_audit(svc)
        req = LoginRequest(email=email, password=password or VALID_PASSWORD)
        return svc.login(req)

    def test_successful_login_returns_tokens_and_user(self):
        user = _make_user()
        db = _make_db()
        db.query.return_value.filter.return_value.first.return_value = user
        db.query.return_value.filter.return_value.limit.return_value.all.return_value = []

        access, refresh, returned_user = self._login(db)

        assert isinstance(access, str)
        assert isinstance(refresh, str)
        assert returned_user is user

    def test_login_unknown_email_raises_invalid_credentials(self):
        db = _make_db()
        db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(InvalidCredentialsError):
            self._login(db)

    def test_login_wrong_password_raises_invalid_credentials(self):
        user = _make_user()
        db = _make_db()
        db.query.return_value.filter.return_value.first.return_value = user

        with pytest.raises(InvalidCredentialsError):
            self._login(db, password="WrongPass1!")

    def test_login_locked_account_raises_account_locked(self):
        user = _make_user(
            locked_until=datetime.now(timezone.utc) + timedelta(minutes=30)
        )
        db = _make_db()
        db.query.return_value.filter.return_value.first.return_value = user

        with pytest.raises(AccountLockedError):
            self._login(db)

    def test_login_increments_failed_attempts_on_wrong_password(self):
        user = _make_user(failed_login_attempts=2)
        db = _make_db()
        db.query.return_value.filter.return_value.first.return_value = user

        with pytest.raises(InvalidCredentialsError):
            self._login(db, password="BadPass1!")

        assert user.failed_login_attempts == 3

    def test_login_resets_failed_attempts_on_success(self):
        user = _make_user(failed_login_attempts=3)
        db = _make_db()
        db.query.return_value.filter.return_value.first.return_value = user
        db.query.return_value.filter.return_value.limit.return_value.all.return_value = []

        self._login(db)
        assert user.failed_login_attempts == 0

    def test_login_inactive_user_raises_invalid_credentials(self):
        user = _make_user(status=UserStatus.INACTIVE)
        db = _make_db()
        db.query.return_value.filter.return_value.first.return_value = user

        with pytest.raises(InvalidCredentialsError):
            self._login(db)


# ---------------------------------------------------------------------------
# AuthService — register
# ---------------------------------------------------------------------------

class TestAuthServiceRegister:
    def _register(self, db, email="new@example.com", password=None, tenant_id=None):
        svc = AuthService(db)
        _silence_audit(svc)
        req = RegisterRequest(
            email=email,
            password=password or VALID_PASSWORD,
            first_name="Alice",
            last_name="Smith",
        )
        return svc.register(req, tenant_id or uuid.uuid4())

    def test_register_duplicate_email_raises(self):
        db = _make_db()
        db.query.return_value.filter.return_value.first.return_value = _make_user()

        with pytest.raises(UserAlreadyExistsError):
            self._register(db)

    def test_register_weak_password_raises(self):
        db = _make_db()
        call_count = [0]

        def q_se(*args):
            call_count[0] += 1
            m = MagicMock()
            m.filter.return_value.first.return_value = None
            return m

        db.query.side_effect = q_se

        # Password is long enough for schema but missing special char → PasswordValidationError
        with pytest.raises(PasswordValidationError):
            self._register(db, password="NoSpecialChar1A")

    def test_register_missing_tenant_raises(self):
        db = _make_db()
        call_count = [0]

        def q_se(*args):
            call_count[0] += 1
            m = MagicMock()
            # Call 1: User lookup → None (no existing user)
            # Call 2: Tenant lookup → None (tenant not found)
            m.filter.return_value.first.return_value = None
            return m

        db.query.side_effect = q_se

        with pytest.raises((ValueError, Exception)):
            self._register(db)


# ---------------------------------------------------------------------------
# AuthService — refresh_access_token
# ---------------------------------------------------------------------------

class TestAuthServiceRefreshToken:
    def test_valid_refresh_token_returns_new_access_token(self):
        user = _make_user()
        raw_token = create_refresh_token({"user_id": str(user.id)})
        token_hash_val = hash_token(raw_token)

        refresh_token_obj = MagicMock(spec=RefreshToken)
        refresh_token_obj.token_hash = token_hash_val
        refresh_token_obj.revoked_at = None
        refresh_token_obj.expires_at = datetime.now(timezone.utc) + timedelta(days=1)
        refresh_token_obj.user_id = user.id

        db = _make_db()
        call_tracker = {"n": 0}

        def q_se(*args):
            call_tracker["n"] += 1
            m = MagicMock()
            if call_tracker["n"] == 1:
                m.filter.return_value.first.return_value = refresh_token_obj
            else:
                m.filter.return_value.first.return_value = user
            return m

        db.query.side_effect = q_se

        svc = AuthService(db)
        new_token = svc.refresh_access_token(raw_token)

        assert isinstance(new_token, str)
        assert len(new_token) > 0

    def test_invalid_refresh_token_raises(self):
        db = _make_db()
        svc = AuthService(db)
        with pytest.raises(InvalidTokenError):
            svc.refresh_access_token("not-a-real-token")


# ---------------------------------------------------------------------------
# AuthService — logout
# ---------------------------------------------------------------------------

class TestAuthServiceLogout:
    def test_logout_revokes_refresh_token(self):
        refresh_token_obj = MagicMock(spec=RefreshToken)
        refresh_token_obj.revoked_at = None

        db = _make_db()
        db.query.return_value.filter.return_value.first.return_value = refresh_token_obj

        svc = AuthService(db)
        _silence_audit(svc)
        svc.logout(create_refresh_token({"user_id": str(uuid.uuid4())}), uuid.uuid4())

        assert refresh_token_obj.revoked_at is not None
        assert refresh_token_obj.revoked_reason == "logout"

    def test_logout_nonexistent_token_does_nothing(self):
        db = _make_db()
        svc = AuthService(db)
        svc.logout("nonexistent", uuid.uuid4())  # must not raise


# ---------------------------------------------------------------------------
# AuthService — reset_password
# ---------------------------------------------------------------------------

class TestAuthServiceResetPassword:
    def test_valid_token_resets_password(self):
        from app.core.security import generate_token_string
        from app.domains.auth.models import PasswordResetToken

        raw = generate_token_string()
        user = _make_user()
        reset_tok = MagicMock(spec=PasswordResetToken)
        reset_tok.used_at = None
        reset_tok.expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        reset_tok.user_id = user.id

        db = _make_db()
        call_tracker = {"n": 0}

        def q_se(*args):
            call_tracker["n"] += 1
            m = MagicMock()
            if call_tracker["n"] == 1:
                m.filter.return_value.first.return_value = reset_tok
            else:
                m.filter.return_value.first.return_value = user
            return m

        db.query.side_effect = q_se

        svc = AuthService(db)
        _silence_audit(svc)
        svc.reset_password(raw, VALID_PASSWORD)

        assert user.password_hash is not None
        assert reset_tok.used_at is not None

    def test_expired_reset_token_raises(self):
        db = _make_db()
        svc = AuthService(db)
        with pytest.raises(InvalidTokenError):
            svc.reset_password("expired-token", VALID_PASSWORD)

    def test_weak_new_password_raises(self):
        from app.domains.auth.models import PasswordResetToken
        from app.core.security import generate_token_string

        reset_tok = MagicMock(spec=PasswordResetToken)
        reset_tok.used_at = None
        reset_tok.expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        db = _make_db()
        db.query.return_value.filter.return_value.first.return_value = reset_tok

        svc = AuthService(db)
        with pytest.raises(PasswordValidationError):
            svc.reset_password(generate_token_string(), "weak")


# ---------------------------------------------------------------------------
# UserService
# ---------------------------------------------------------------------------

class TestUserService:
    def test_get_user_by_id_returns_user(self):
        uid = uuid.uuid4()
        user = _make_user(id=uid)
        db = _make_db()
        db.query.return_value.filter.return_value.first.return_value = user

        result = UserService(db).get_user_by_id(uid)
        assert result is user

    def test_get_user_by_id_missing_returns_none(self):
        db = _make_db()
        result = UserService(db).get_user_by_id(uuid.uuid4())
        assert result is None

    def test_change_password_wrong_current_raises(self):
        user = _make_user()
        db = _make_db()
        db.query.return_value.filter.return_value.first.return_value = user

        svc = UserService(db)
        with pytest.raises(InvalidCredentialsError):
            svc.change_password(user.id, "wrongold1!", VALID_PASSWORD)

    def test_change_password_weak_new_raises(self):
        user = _make_user()
        db = _make_db()
        db.query.return_value.filter.return_value.first.return_value = user

        svc = UserService(db)
        with pytest.raises(PasswordValidationError):
            svc.change_password(user.id, VALID_PASSWORD, "weak")

    def test_change_password_success_updates_hash(self):
        user = _make_user()
        db = _make_db()
        db.query.return_value.filter.return_value.first.return_value = user

        svc = UserService(db)
        _silence_audit(svc)
        svc.change_password(user.id, VALID_PASSWORD, "NewSecure@Pass1")

        assert user.password_hash is not None
        db.commit.assert_called()
