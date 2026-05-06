"""
Invite service for managing user invitations.
"""
import hashlib
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.core.config import settings
from app.core.security import generate_token_string
from app.core.exceptions import InvalidTokenError, UserNotFoundError
from app.core.logging import get_logger
from app.domains.auth.models import (
    User,
    Invite,
    Role,
    Institution,
    PersonalWorkspace,
    Tenant,
    ScopeType,
    InviteStatus,
    AuditEventType,
)
from app.domains.auth.services import AuditService

logger = get_logger(__name__)


def hash_token(token: str) -> str:
    """Hash a token for storage."""
    return hashlib.sha256(token.encode()).hexdigest()


class InviteService:
    """Service for managing user invitations."""
    
    def __init__(self, db: Session):
        self.db = db
        self.audit = AuditService()
    
    def create_invite(
        self,
        email: str,
        role_id: UUID,
        scope_type: ScopeType,
        scope_id: UUID,
        invited_by: Optional[UUID] = None,
        expires_in_days: int = 7,
    ) -> tuple[Invite, str]:
        """
        Create an invite.
        
        Args:
            email: Email address to invite
            role_id: Role ID for the invite
            scope_type: Type of scope (INSTITUTION, PERSONAL_WORKSPACE, ORGANIZATION)
            scope_id: ID of the scope entity
            invited_by: User ID who created the invite (optional)
            expires_in_days: Number of days until invite expires (default 7)
            
        Returns:
            Tuple of (Invite object, plain token string)
        """
        # Verify scope exists
        if scope_type == ScopeType.INSTITUTION:
            scope_entity = self.db.query(Institution).filter(Institution.id == scope_id).first()
            if not scope_entity:
                raise ValueError(f"Institution with id {scope_id} not found")
        elif scope_type == ScopeType.PERSONAL_WORKSPACE:
            scope_entity = self.db.query(PersonalWorkspace).filter(PersonalWorkspace.id == scope_id).first()
            if not scope_entity:
                raise ValueError(f"Personal workspace with id {scope_id} not found")
        elif scope_type == ScopeType.ORGANIZATION:
            scope_entity = self.db.query(Tenant).filter(
                Tenant.id == scope_id,
                Tenant.type == "organization"
            ).first()
            if not scope_entity:
                raise ValueError(f"Organization with id {scope_id} not found")
        
        # Check for existing pending invite
        existing = self.db.query(Invite).filter(
            Invite.email == email.lower(),
            Invite.scope_type == scope_type,
            Invite.scope_id == scope_id,
            Invite.status == InviteStatus.PENDING,
            Invite.expires_at > datetime.now(timezone.utc),
        ).first()
        
        if existing:
            # Return existing invite (don't create duplicate)
            # Generate a new token for the existing invite
            token = generate_token_string()
            existing.token_hash = hash_token(token)
            existing.expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)
            existing.updated_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(existing)
            return existing, token
        
        # Generate token
        token = generate_token_string()
        token_hash = hash_token(token)
        
        # Create invite
        invite = Invite(
            email=email.lower(),
            role_id=role_id,
            scope_type=scope_type,
            scope_id=scope_id,
            token_hash=token_hash,
            status=InviteStatus.PENDING,
            expires_at=datetime.now(timezone.utc) + timedelta(days=expires_in_days),
            invited_by=invited_by,
        )
        self.db.add(invite)
        self.db.commit()
        self.db.refresh(invite)
        
        # Audit log
        self.audit.log_event(
            self.db,
            AuditEventType.USER_CREATED,  # Using USER_CREATED as invite is user creation
            f"Invite created: {email} for {scope_type.value} {scope_id}",
            actor_user_id=invited_by,
            event_metadata={
                "email": email,
                "scope_type": scope_type.value,
                "scope_id": str(scope_id),
                "role_id": str(role_id),
            },
        )
        
        return invite, token
    
    def validate_invite(
        self,
        token: str,
    ) -> Invite:
        """
        Validate an invite token.
        
        Args:
            token: Invite token
            
        Returns:
            Invite object if valid
            
        Raises:
            InvalidTokenError: If token is invalid or expired
        """
        token_hash = hash_token(token)
        invite = self.db.query(Invite).filter(
            Invite.token_hash == token_hash,
            Invite.status == InviteStatus.PENDING,
        ).first()
        
        if not invite:
            raise InvalidTokenError("Invalid invite token")
        
        if invite.expires_at < datetime.now(timezone.utc):
            invite.status = InviteStatus.EXPIRED
            self.db.commit()
            raise InvalidTokenError("Invite token has expired")
        
        return invite
    
    def accept_invite(
        self,
        token: str,
        user_id: Optional[UUID] = None,
    ) -> Invite:
        """
        Mark an invite as accepted.
        
        Note: This is called after the user has been created/updated and membership added.
        The actual user creation and membership creation is handled by SignupService.
        
        Args:
            token: Invite token
            user_id: User ID who accepted the invite (if user already existed)
            
        Returns:
            Accepted Invite object
        """
        invite = self.validate_invite(token)
        
        # If user_id provided, user already existed
        if user_id:
            invite.accepted_by_user_id = user_id
        
        invite.status = InviteStatus.ACCEPTED
        invite.accepted_at = datetime.now(timezone.utc)
        invite.updated_at = datetime.now(timezone.utc)
        
        self.db.commit()
        self.db.refresh(invite)
        
        return invite
    
    def revoke_invite(
        self,
        invite_id: UUID,
        revoked_by: Optional[UUID] = None,
    ) -> None:
        """
        Revoke an invite.
        
        Args:
            invite_id: Invite ID
            revoked_by: User ID who revoked the invite (optional)
        """
        invite = self.db.query(Invite).filter(Invite.id == invite_id).first()
        
        if not invite:
            raise ValueError(f"Invite with id {invite_id} not found")
        
        if invite.status != InviteStatus.PENDING:
            return  # Already accepted, expired, or revoked
        
        invite.status = InviteStatus.REVOKED
        invite.updated_at = datetime.now(timezone.utc)
        
        self.db.commit()
        
        # Audit log
        self.audit.log_event(
            self.db,
            AuditEventType.ROLE_REVOKED,  # Using ROLE_REVOKED as closest match
            f"Invite revoked: {invite.email}",
            actor_user_id=revoked_by,
            event_metadata={
                "invite_id": str(invite_id),
                "email": invite.email,
            },
        )
    
    def list_invites(
        self,
        scope_type: Optional[ScopeType] = None,
        scope_id: Optional[UUID] = None,
        status: Optional[InviteStatus] = None,
    ) -> List[Invite]:
        """
        List invites with optional filters.
        
        Args:
            scope_type: Filter by scope type (optional)
            scope_id: Filter by scope ID (optional)
            status: Filter by status (optional)
            
        Returns:
            List of Invite objects
        """
        query = self.db.query(Invite)
        
        if scope_type:
            query = query.filter(Invite.scope_type == scope_type)
        
        if scope_id:
            query = query.filter(Invite.scope_id == scope_id)
        
        if status:
            query = query.filter(Invite.status == status)
        
        return query.order_by(Invite.created_at.desc()).all()
    
    def get_invite_by_email(
        self,
        email: str,
        scope_type: ScopeType,
        scope_id: UUID,
    ) -> Optional[Invite]:
        """
        Get pending invite by email and scope.
        
        Args:
            email: Email address
            scope_type: Scope type
            scope_id: Scope ID
            
        Returns:
            Invite object or None
        """
        return self.db.query(Invite).filter(
            Invite.email == email.lower(),
            Invite.scope_type == scope_type,
            Invite.scope_id == scope_id,
            Invite.status == InviteStatus.PENDING,
            Invite.expires_at > datetime.now(timezone.utc),
        ).first()
