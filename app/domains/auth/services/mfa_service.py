"""TOTP MFA service for super_admin accounts."""
import base64
import hashlib
from datetime import datetime, timezone
from typing import Optional, Tuple
from uuid import UUID

import pyotp
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.core.logging import get_logger
from app.domains.auth.models import Role, RoleName, User, UserRole

logger = get_logger(__name__)

MFA_ISSUER = "1ne.ai"


def _get_fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
    return Fernet(key)


def encrypt_mfa_secret(secret: str) -> str:
    return _get_fernet().encrypt(secret.encode()).decode()


def decrypt_mfa_secret(encrypted: str) -> str:
    try:
        return _get_fernet().decrypt(encrypted.encode()).decode()
    except InvalidToken:
        raise AuthenticationError("Invalid MFA configuration")


def is_super_admin(db: Session, user_id: UUID) -> bool:
    return (
        db.query(UserRole)
        .join(Role)
        .filter(
            UserRole.user_id == user_id,
            Role.name == RoleName.SUPER_ADMIN,
        )
        .first()
        is not None
    )


class MfaService:
    """Manage TOTP enrollment and verification for super_admin users."""

    def __init__(self, db: Session):
        self.db = db

    def require_super_admin(self, user: User) -> None:
        if not is_super_admin(self.db, user.id):
            raise AuthorizationError("Super admin role required")

    def start_enrollment(self, user: User) -> Tuple[str, str, str]:
        """Generate a new TOTP secret and store it (not yet enabled)."""
        self.require_super_admin(user)
        secret = pyotp.random_base32()
        user.mfa_secret_encrypted = encrypt_mfa_secret(secret)
        user.mfa_enabled_at = None
        self.db.commit()

        totp = pyotp.TOTP(secret)
        otpauth_url = totp.provisioning_uri(name=user.email, issuer_name=MFA_ISSUER)
        return secret, otpauth_url, f"otpauth://totp/{MFA_ISSUER}:{user.email}?secret={secret}&issuer={MFA_ISSUER}"

    def verify_and_enable(self, user: User, code: str) -> None:
        """Verify TOTP code and enable MFA."""
        self.require_super_admin(user)
        if not user.mfa_secret_encrypted:
            raise AuthenticationError("MFA enrollment not started")

        secret = decrypt_mfa_secret(user.mfa_secret_encrypted)
        totp = pyotp.TOTP(secret)
        if not totp.verify(code, valid_window=1):
            raise AuthenticationError("Invalid MFA code")

        user.mfa_enabled_at = datetime.now(timezone.utc)
        self.db.commit()

    def verify_code(self, user: User, code: str) -> bool:
        if not user.mfa_secret_encrypted or not user.mfa_enabled_at:
            return False
        secret = decrypt_mfa_secret(user.mfa_secret_encrypted)
        return pyotp.TOTP(secret).verify(code, valid_window=1)

    def mfa_required_for_user(self, user: User) -> bool:
        return is_super_admin(self.db, user.id) and user.mfa_enabled_at is not None

    def mfa_enrollment_required(self, user: User) -> bool:
        return is_super_admin(self.db, user.id) and user.mfa_enabled_at is None
