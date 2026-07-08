"""Admin domain dependencies — super_admin + MFA-verified session."""
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.exceptions import AuthorizationError
from app.core.security import decode_token
from app.db.session import get_db
from app.domains.auth.dependencies import get_current_user, security
from app.domains.auth.models import Role, RoleName, User, UserRole
from app.domains.auth.services.mfa_service import is_super_admin, MfaService


def _get_token_payload(credentials: Optional[HTTPAuthorizationCredentials]) -> dict:
    if not credentials:
        return {}
    try:
        return decode_token(credentials.credentials, token_type="access")
    except Exception:
        return {}


def require_super_admin(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    if not is_super_admin(db, current_user.id):
        raise AuthorizationError("Super admin role required")
    return current_user


def require_super_admin_mfa(
    current_user: User = Depends(get_current_user),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """Require super_admin role and MFA-verified session when MFA is enabled."""
    from app.core.config import settings

    if not is_super_admin(db, current_user.id):
        raise AuthorizationError("Super admin role required")

    if not settings.REQUIRE_SUPER_ADMIN_MFA:
        return current_user

    mfa_service = MfaService(db)
    if mfa_service.mfa_required_for_user(current_user):
        payload = _get_token_payload(credentials)
        if not payload.get("mfa_verified"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "MFA_REQUIRED", "message": "MFA verification required for admin access"},
            )
    return current_user
