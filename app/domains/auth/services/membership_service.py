"""
Membership service for managing user memberships.
"""
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.core.exceptions import UserNotFoundError
from app.core.logging import get_logger
from app.domains.auth.models import (
    User,
    UserMembership,
    Role,
    Institution,
    PersonalWorkspace,
    Tenant,
    ScopeType,
    AuditEventType,
)
from app.domains.auth.services import AuditService

logger = get_logger(__name__)


class MembershipService:
    """Service for managing user memberships."""
    
    def __init__(self, db: Session):
        self.db = db
        self.audit = AuditService()
    
    def create_membership(
        self,
        user_id: UUID,
        scope_type: ScopeType,
        scope_id: UUID,
        role_id: UUID,
        granted_by: Optional[UUID] = None,
    ) -> UserMembership:
        """
        Create a new membership for a user.
        
        Args:
            user_id: User ID
            scope_type: Type of scope (INSTITUTION, PERSONAL_WORKSPACE, ORGANIZATION)
            scope_id: ID of the scope entity
            role_id: Role ID for this membership
            granted_by: User ID who granted this membership (optional)
            
        Returns:
            Created UserMembership
        """
        # Verify user exists
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise UserNotFoundError()
        
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
        
        # Check if membership already exists
        existing = self.db.query(UserMembership).filter(
            UserMembership.user_id == user_id,
            UserMembership.scope_type == scope_type,
            UserMembership.scope_id == scope_id,
        ).first()
        
        if existing:
            # Reactivate if revoked
            if not existing.is_active:
                existing.is_active = True
                existing.revoked_at = None
                existing.revoked_by = None
                existing.updated_at = datetime.now(timezone.utc)
                self.db.commit()
                self.db.refresh(existing)
                return existing
            else:
                raise ValueError("Membership already exists and is active")
        
        # Create membership
        membership = UserMembership(
            user_id=user_id,
            scope_type=scope_type,
            scope_id=scope_id,
            role_id=role_id,
            is_active=True,
            granted_by=granted_by,
        )
        self.db.add(membership)
        self.db.commit()
        self.db.refresh(membership)
        
        # Audit log
        self.audit.log_event(
            self.db,
            AuditEventType.ROLE_ASSIGNED,
            f"Membership created: user {user.email} in {scope_type.value} {scope_id}",
            actor_user_id=granted_by,
            target_user_id=user_id,
            event_metadata={
                "scope_type": scope_type.value,
                "scope_id": str(scope_id),
                "role_id": str(role_id),
            },
        )
        
        return membership
    
    def revoke_membership(
        self,
        membership_id: UUID,
        revoked_by: Optional[UUID] = None,
    ) -> None:
        """
        Revoke a membership.
        
        Args:
            membership_id: Membership ID to revoke
            revoked_by: User ID who revoked the membership (optional)
        """
        membership = self.db.query(UserMembership).filter(
            UserMembership.id == membership_id
        ).first()
        
        if not membership:
            raise ValueError(f"Membership with id {membership_id} not found")
        
        if not membership.is_active:
            return  # Already revoked
        
        membership.is_active = False
        membership.revoked_at = datetime.now(timezone.utc)
        membership.revoked_by = revoked_by
        membership.updated_at = datetime.now(timezone.utc)
        
        self.db.commit()
        
        # Audit log
        user = self.db.query(User).filter(User.id == membership.user_id).first()
        self.audit.log_event(
            self.db,
            AuditEventType.ROLE_REVOKED,
            f"Membership revoked: user {user.email if user else 'unknown'} from {membership.scope_type.value} {membership.scope_id}",
            actor_user_id=revoked_by,
            target_user_id=membership.user_id,
            event_metadata={
                "membership_id": str(membership_id),
                "scope_type": membership.scope_type.value,
                "scope_id": str(membership.scope_id),
            },
        )
    
    def get_user_memberships(
        self,
        user_id: UUID,
        active_only: bool = True,
    ) -> List[UserMembership]:
        """
        Get all memberships for a user.
        
        Args:
            user_id: User ID
            active_only: If True, only return active memberships
            
        Returns:
            List of UserMembership objects
        """
        query = self.db.query(UserMembership).filter(
            UserMembership.user_id == user_id
        )
        
        if active_only:
            query = query.filter(UserMembership.is_active == True)
        
        return query.all()
    
    def get_active_membership(
        self,
        user_id: UUID,
    ) -> Optional[UserMembership]:
        """
        Get the currently active membership for a user.
        
        Note: In a multi-membership scenario, this returns the first active membership.
        The actual active membership should be tracked via refresh token or session.
        
        Args:
            user_id: User ID
            
        Returns:
            Active UserMembership or None
        """
        memberships = self.get_user_memberships(user_id, active_only=True)
        return memberships[0] if memberships else None
    
    def switch_active_membership(
        self,
        user_id: UUID,
        membership_id: UUID,
    ) -> UserMembership:
        """
        Switch active membership for a user.
        
        Args:
            user_id: User ID
            membership_id: Membership ID to switch to
            
        Returns:
            The membership that was switched to
        """
        # Verify membership belongs to user
        membership = self.db.query(UserMembership).filter(
            UserMembership.id == membership_id,
            UserMembership.user_id == user_id,
            UserMembership.is_active == True,
        ).first()
        
        if not membership:
            raise ValueError(f"Active membership {membership_id} not found for user {user_id}")
        
        # The actual switching is handled by updating the refresh token's active_membership_id
        # This method just validates the membership exists and is active
        
        return membership
    
    def get_membership_details(
        self,
        membership: UserMembership,
    ) -> dict:
        """
        Get detailed information about a membership including scope name.
        
        Args:
            membership: UserMembership object
            
        Returns:
            Dict with membership details including scope name and type
        """
        role = self.db.query(Role).filter(Role.id == membership.role_id).first()
        
        scope_name = None
        scope_display_name = None
        
        if membership.scope_type == ScopeType.INSTITUTION:
            institution = self.db.query(Institution).filter(
                Institution.id == membership.scope_id
            ).first()
            if institution:
                scope_name = institution.name
                scope_display_name = f"{institution.name} ({institution.institution_type.value})"
        elif membership.scope_type == ScopeType.PERSONAL_WORKSPACE:
            workspace = self.db.query(PersonalWorkspace).filter(
                PersonalWorkspace.id == membership.scope_id
            ).first()
            if workspace:
                scope_name = workspace.name
                scope_display_name = "Personal Workspace"
        elif membership.scope_type == ScopeType.ORGANIZATION:
            org = self.db.query(Tenant).filter(
                Tenant.id == membership.scope_id,
                Tenant.type == "organization"
            ).first()
            if org:
                scope_name = org.name
                scope_display_name = f"{org.name} (Organization)"
        
        return {
            "id": str(membership.id),
            "scope_type": membership.scope_type.value,
            "scope_id": str(membership.scope_id),
            "scope_name": scope_name,
            "scope_display_name": scope_display_name,
            "role": {
                "id": str(role.id) if role else None,
                "name": role.name.value if role else None,
            },
            "is_active": membership.is_active,
            "granted_at": membership.granted_at.isoformat() if membership.granted_at else None,
        }
