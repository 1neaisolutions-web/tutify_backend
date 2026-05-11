"""
Unit tests for InviteService in app/domains/auth/services/invite_service.py.
"""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.core.exceptions import InvalidTokenError
from app.domains.auth.models import InviteStatus, ScopeType
from app.domains.auth.services.invite_service import InviteService


def _make_db():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    return db


def _make_invite(status=InviteStatus.PENDING, expired=False):
    invite = MagicMock()
    invite.status = status
    invite.expires_at = (
        datetime.now(timezone.utc) - timedelta(hours=1)
        if expired
        else datetime.now(timezone.utc) + timedelta(days=7)
    )
    invite.email = "user@example.com"
    invite.id = uuid.uuid4()
    invite.accepted_by_user_id = None
    invite.accepted_at = None
    return invite


def _make_svc(db):
    svc = InviteService(db)
    svc.audit = MagicMock()  # silence audit calls
    return svc


# ---------------------------------------------------------------------------
# create_invite
# ---------------------------------------------------------------------------

class TestCreateInvite:
    def test_creates_invite_when_no_existing_pending(self):
        db = _make_db()
        scope_entity = MagicMock()

        call_tracker = {"n": 0}

        def query_se(*args, **kwargs):
            call_tracker["n"] += 1
            mock = MagicMock()
            if call_tracker["n"] == 1:
                mock.filter.return_value.first.return_value = scope_entity
            else:
                mock.filter.return_value.first.return_value = None
            return mock

        db.query.side_effect = query_se

        svc = _make_svc(db)
        invite, token = svc.create_invite(
            email="new@test.com",
            role_id=uuid.uuid4(),
            scope_type=ScopeType.INSTITUTION,
            scope_id=uuid.uuid4(),
            invited_by=uuid.uuid4(),
        )

        assert isinstance(token, str)
        assert len(token) > 0
        db.add.assert_called_once()

    def test_returns_existing_invite_with_refreshed_token(self):
        db = _make_db()
        existing_invite = _make_invite()
        scope_entity = MagicMock()

        call_tracker = {"n": 0}

        def query_se(*args, **kwargs):
            call_tracker["n"] += 1
            mock = MagicMock()
            if call_tracker["n"] == 1:
                mock.filter.return_value.first.return_value = scope_entity
            else:
                mock.filter.return_value.first.return_value = existing_invite
            return mock

        db.query.side_effect = query_se

        svc = _make_svc(db)
        invite, token = svc.create_invite(
            email=existing_invite.email,
            role_id=uuid.uuid4(),
            scope_type=ScopeType.INSTITUTION,
            scope_id=uuid.uuid4(),
        )

        assert invite is existing_invite
        assert isinstance(token, str)

    def test_missing_institution_scope_raises(self):
        db = _make_db()

        svc = _make_svc(db)
        with pytest.raises(ValueError, match="not found"):
            svc.create_invite(
                email="x@x.com",
                role_id=uuid.uuid4(),
                scope_type=ScopeType.INSTITUTION,
                scope_id=uuid.uuid4(),
            )


# ---------------------------------------------------------------------------
# validate_invite
# ---------------------------------------------------------------------------

class TestValidateInvite:
    def test_valid_token_returns_invite(self):
        invite = _make_invite()
        db = _make_db()
        db.query.return_value.filter.return_value.first.return_value = invite

        svc = _make_svc(db)
        result = svc.validate_invite("some-token")
        assert result is invite

    def test_nonexistent_token_raises_invalid_token(self):
        db = _make_db()
        svc = _make_svc(db)
        with pytest.raises(InvalidTokenError):
            svc.validate_invite("invalid-token")

    def test_expired_invite_raises_invalid_token(self):
        invite = _make_invite(expired=True)
        db = _make_db()
        db.query.return_value.filter.return_value.first.return_value = invite

        svc = _make_svc(db)
        with pytest.raises(InvalidTokenError, match="expired"):
            svc.validate_invite("some-token")
        assert invite.status == InviteStatus.EXPIRED


# ---------------------------------------------------------------------------
# accept_invite
# ---------------------------------------------------------------------------

class TestAcceptInvite:
    def test_accept_valid_invite_sets_accepted_status(self):
        invite = _make_invite()
        db = _make_db()
        db.query.return_value.filter.return_value.first.return_value = invite

        svc = _make_svc(db)
        result = svc.accept_invite("some-token")

        assert result.status == InviteStatus.ACCEPTED
        assert result.accepted_at is not None

    def test_accept_sets_accepted_by_user_id_when_provided(self):
        invite = _make_invite()
        user_id = uuid.uuid4()
        db = _make_db()
        db.query.return_value.filter.return_value.first.return_value = invite

        svc = _make_svc(db)
        svc.accept_invite("some-token", user_id=user_id)
        assert invite.accepted_by_user_id == user_id


# ---------------------------------------------------------------------------
# revoke_invite
# ---------------------------------------------------------------------------

class TestRevokeInvite:
    def test_revoke_pending_invite(self):
        invite = _make_invite()
        db = _make_db()
        db.query.return_value.filter.return_value.first.return_value = invite

        svc = _make_svc(db)
        svc.revoke_invite(invite.id)

        assert invite.status == InviteStatus.REVOKED
        db.commit.assert_called()

    def test_revoke_nonexistent_invite_raises(self):
        db = _make_db()
        svc = _make_svc(db)
        with pytest.raises(ValueError):
            svc.revoke_invite(uuid.uuid4())

    def test_revoke_already_accepted_invite_is_noop(self):
        invite = _make_invite(status=InviteStatus.ACCEPTED)
        db = _make_db()
        db.query.return_value.filter.return_value.first.return_value = invite

        svc = _make_svc(db)
        svc.revoke_invite(invite.id)
        assert invite.status == InviteStatus.ACCEPTED  # unchanged


# ---------------------------------------------------------------------------
# list_invites
# ---------------------------------------------------------------------------

class TestListInvites:
    def test_list_returns_all_when_no_filters(self):
        invites = [_make_invite(), _make_invite()]
        db = _make_db()
        db.query.return_value.order_by.return_value.all.return_value = invites

        svc = _make_svc(db)
        result = svc.list_invites()
        assert len(result) == 2

    def test_list_filters_by_status(self):
        invites = [_make_invite(status=InviteStatus.PENDING)]
        db = _make_db()
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = invites

        svc = _make_svc(db)
        result = svc.list_invites(status=InviteStatus.PENDING)
        assert len(result) == 1
