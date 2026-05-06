"""
Session service for managing user sessions and refresh tokens.
"""
import hashlib
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.core.config import settings
from app.core.security import generate_token_string
from app.core.logging import get_logger
from app.domains.auth.models import (
    User,
    RefreshToken,
    UserMembership,
    AuditEventType,
)
from app.domains.auth.services import AuditService

logger = get_logger(__name__)


def hash_token(token: str) -> str:
    """Hash a token for storage."""
    return hashlib.sha256(token.encode()).hexdigest()


class SessionService:
    """Service for managing user sessions and refresh tokens."""
    
    def __init__(self, db: Session):
        self.db = db
        self.audit = AuditService()
    
    def create_session(
        self,
        user_id: UUID,
        device_info: Optional[dict] = None,
        active_membership_id: Optional[UUID] = None,
        expires_in_days: int = 30,
    ) -> tuple[RefreshToken, str]:
        """
        Create a new session (refresh token).
        
        Args:
            user_id: User ID
            device_info: Device/client information (optional)
            active_membership_id: Active membership ID for this session (optional)
            expires_in_days: Number of days until token expires (default 30)
            
        Returns:
            Tuple of (RefreshToken object, plain token string)
        """
        # Verify user exists
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError(f"User with id {user_id} not found")
        
        # Verify membership if provided
        if active_membership_id:
            membership = self.db.query(UserMembership).filter(
                UserMembership.id == active_membership_id,
                UserMembership.user_id == user_id,
                UserMembership.is_active == True,
            ).first()
            if not membership:
                raise ValueError(f"Active membership {active_membership_id} not found for user {user_id}")
        
        # Generate token
        token = generate_token_string()
        token_hash = hash_token(token)
        
        # Create refresh token
        refresh_token = RefreshToken(
            user_id=user_id,
            token_hash=token_hash,
            device_info=device_info,
            expires_at=datetime.now(timezone.utc) + timedelta(days=expires_in_days),
            active_membership_id=active_membership_id,
        )
        self.db.add(refresh_token)
        self.db.commit()
        self.db.refresh(refresh_token)
        
        return refresh_token, token
    
    def list_sessions(
        self,
        user_id: UUID,
        active_only: bool = True,
    ) -> List[RefreshToken]:
        """
        List all sessions for a user.
        
        Args:
            user_id: User ID
            active_only: If True, only return non-revoked, non-expired sessions
            
        Returns:
            List of RefreshToken objects
        """
        query = self.db.query(RefreshToken).filter(
            RefreshToken.user_id == user_id
        )
        
        if active_only:
            now = datetime.now(timezone.utc)
            query = query.filter(
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > now,
            )
        
        return query.order_by(RefreshToken.created_at.desc()).all()
    
    def revoke_session(
        self,
        token_hash: str,
        reason: Optional[str] = None,
    ) -> None:
        """
        Revoke a session (refresh token).
        
        Args:
            token_hash: Hashed token
            reason: Reason for revocation (optional)
        """
        refresh_token = self.db.query(RefreshToken).filter(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked_at.is_(None),
        ).first()
        
        if not refresh_token:
            return  # Already revoked or doesn't exist
        
        refresh_token.revoked_at = datetime.now(timezone.utc)
        refresh_token.revoked_reason = reason
        
        self.db.commit()
        
        # Audit log
        user = self.db.query(User).filter(User.id == refresh_token.user_id).first()
        self.audit.log_event(
            self.db,
            AuditEventType.LOGOUT,
            f"Session revoked: {user.email if user else 'unknown'}",
            actor_user_id=refresh_token.user_id,
            target_user_id=refresh_token.user_id,
            event_metadata={
                "reason": reason,
                "device_info": refresh_token.device_info,
            },
        )
    
    def revoke_all_sessions(
        self,
        user_id: UUID,
        reason: Optional[str] = None,
    ) -> int:
        """
        Revoke all sessions for a user.
        
        Args:
            user_id: User ID
            reason: Reason for revocation (optional)
            
        Returns:
            Number of sessions revoked
        """
        now = datetime.now(timezone.utc)
        sessions = self.db.query(RefreshToken).filter(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > now,
        ).all()
        
        for session in sessions:
            session.revoked_at = now
            session.revoked_reason = reason or "Revoked all sessions"
        
        self.db.commit()
        
        # Audit log
        user = self.db.query(User).filter(User.id == user_id).first()
        self.audit.log_event(
            self.db,
            AuditEventType.LOGOUT,
            f"All sessions revoked: {user.email if user else 'unknown'}",
            actor_user_id=user_id,
            target_user_id=user_id,
            event_metadata={
                "reason": reason,
                "sessions_revoked": len(sessions),
            },
        )
        
        return len(sessions)
    
    def update_session_membership(
        self,
        token_hash: str,
        active_membership_id: Optional[UUID],
    ) -> RefreshToken:
        """
        Update the active membership for a session.
        
        Args:
            token_hash: Hashed refresh token
            active_membership_id: New active membership ID (None to clear)
            
        Returns:
            Updated RefreshToken
        """
        refresh_token = self.db.query(RefreshToken).filter(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > datetime.now(timezone.utc),
        ).first()
        
        if not refresh_token:
            raise ValueError("Active session not found")
        
        # Verify membership if provided
        if active_membership_id:
            membership = self.db.query(UserMembership).filter(
                UserMembership.id == active_membership_id,
                UserMembership.user_id == refresh_token.user_id,
                UserMembership.is_active == True,
            ).first()
            if not membership:
                raise ValueError(f"Active membership {active_membership_id} not found for user")
        
        refresh_token.active_membership_id = active_membership_id
        refresh_token.last_used_at = datetime.now(timezone.utc)
        
        self.db.commit()
        self.db.refresh(refresh_token)
        
        return refresh_token
    
    def get_session_by_token(
        self,
        token: str,
    ) -> Optional[RefreshToken]:
        """
        Get session by token.
        
        Args:
            token: Plain refresh token
            
        Returns:
            RefreshToken object or None
        """
        token_hash = hash_token(token)
        return self.db.query(RefreshToken).filter(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > datetime.now(timezone.utc),
        ).first()
    
    def rotate_token(
        self,
        old_token_hash: str,
        device_info: Optional[dict] = None,
    ) -> tuple[RefreshToken, str]:
        """
        Rotate a refresh token (create new, revoke old).
        
        Args:
            old_token_hash: Hash of old token
            device_info: Updated device info (optional)
            
        Returns:
            Tuple of (new RefreshToken, plain token string)
        """
        old_token = self.db.query(RefreshToken).filter(
            RefreshToken.token_hash == old_token_hash,
            RefreshToken.revoked_at.is_(None),
        ).first()
        
        if not old_token:
            raise ValueError("Token not found or already revoked")
        
        # Create new token
        new_token, plain_token = self.create_session(
            user_id=old_token.user_id,
            device_info=device_info or old_token.device_info,
            active_membership_id=old_token.active_membership_id,
        )
        
        # Link tokens
        old_token.next_token_id = new_token.id
        new_token.parent_token_id = old_token.id
        
        # Revoke old token
        old_token.revoked_at = datetime.now(timezone.utc)
        old_token.revoked_reason = "Token rotated"
        
        self.db.commit()
        
        return new_token, plain_token
