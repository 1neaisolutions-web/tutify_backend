"""
Signup service with strategy pattern for handling different signup types.
"""
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.core.config import settings
from app.core.security import hash_password, validate_password_strength
from app.core.exceptions import (
    UserAlreadyExistsError,
    PasswordValidationError,
    UserNotFoundError,
    InvalidTokenError,
)
from app.core.logging import get_logger
from app.domains.auth.models import (
    User,
    Tenant,
    Role,
    UserRole,
    UserMembership,
    PersonalWorkspace,
    Institution,
    Invite,
    UserStatus,
    RoleName,
    RoleScope,
    TenantType,
    ScopeType,
    InviteStatus,
    InstitutionType,
    AuditEventType,
)
from app.domains.auth.services import AuditService
from app.domains.auth.language_validation import is_valid_language_tag

logger = get_logger(__name__)


def _default_user_preferences(language: Optional[str] = None) -> Dict[str, str]:
    lang = (language or "en-US").strip() or "en-US"
    if not is_valid_language_tag(lang):
        lang = "en-US"
    return {
        "theme": "system",
        "language": lang,
        "timezone": "UTC",
    }


class SignupStrategy(ABC):
    """Base strategy interface for signup operations."""
    
    def __init__(self, db: Session):
        self.db = db
        self.audit = AuditService()
    
    @abstractmethod
    def validate_payload(self, payload: Dict[str, Any]) -> bool:
        """Validate that payload contains required fields for this strategy."""
        pass
    
    @abstractmethod
    def execute(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the signup strategy.
        
        Returns:
            Dict with keys: user, memberships, tokens (optional)
        """
        pass


class OrgAdminSignupStrategy(SignupStrategy):
    """Strategy for Organization Admin signup."""
    
    def validate_payload(self, payload: Dict[str, Any]) -> bool:
        """Validate organization admin signup payload."""
        required = ['email', 'password', 'first_name', 'last_name', 'organization']
        return all(key in payload for key in required)
    
    def execute(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Execute organization admin signup."""
        from app.domains.auth.services import TenantService
        
        # Check if user already exists
        existing_user = self.db.query(User).filter(
            User.email == payload['email'].lower()
        ).first()
        if existing_user:
            raise UserAlreadyExistsError()
        
        # Validate password
        is_valid, error_msg = validate_password_strength(payload['password'])
        if not is_valid:
            raise PasswordValidationError(error_msg)
        
        tenant_service = TenantService(self.db)
        
        # Create organization
        org_data = payload['organization']
        from app.domains.auth.schemas import CreateOrganizationRequest
        
        # Create org tenant directly (we'll create user separately)
        platform = self.db.query(Tenant).filter(
            Tenant.type == TenantType.PLATFORM,
            Tenant.is_active == True
        ).first()
        if not platform:
            platform = tenant_service.create_platform_tenant()
        
        hierarchy_path = f"/org-{org_data.get('slug', org_data['name'].lower().replace(' ', '-'))}/"
        org = Tenant(
            name=org_data['name'],
            slug=org_data.get('slug', org_data['name'].lower().replace(' ', '-')),
            type=TenantType.ORGANIZATION,
            parent_tenant_id=platform.id,
            hierarchy_path=hierarchy_path,
            settings=org_data.get('settings'),
            is_active=True,
        )
        self.db.add(org)
        self.db.flush()
        
        # Create user
        user = User(
            email=payload['email'].lower(),
            password_hash=hash_password(payload['password']),
            first_name=payload['first_name'],
            last_name=payload['last_name'],
            full_name=f"{payload['first_name']} {payload['last_name']}".strip(),
            phone=payload.get('phone'),
            tenant_id=org.id,  # Default tenant for backward compatibility
            status=UserStatus.ACTIVE,
            email_verified=settings.ENVIRONMENT != "prod",  # Auto-verify in dev
            preferences=_default_user_preferences(payload.get("language")),
        )
        self.db.add(user)
        self.db.flush()
        
        # Assign ORG_ADMIN role
        org_admin_role = self.db.query(Role).filter(Role.name == RoleName.ORG_ADMIN).first()
        if org_admin_role:
            # Create membership for organization
            membership = UserMembership(
                user_id=user.id,
                scope_type=ScopeType.ORGANIZATION,
                scope_id=org.id,
                role_id=org_admin_role.id,
                is_active=True,
            )
            self.db.add(membership)
            
            # Also create UserRole for backward compatibility
            user_role = UserRole(
                user_id=user.id,
                role_id=org_admin_role.id,
                tenant_id=org.id,
            )
            self.db.add(user_role)
        
        # Create first institution if provided
        memberships = [membership]
        if 'institution' in payload:
            inst_data = payload['institution']
            institution = Institution(
                name=inst_data['name'],
                slug=inst_data.get('slug', inst_data['name'].lower().replace(' ', '-')),
                institution_type=InstitutionType(inst_data.get('institution_type', 'k12_school')),
                organization_id=org.id,
                settings=inst_data.get('settings'),
            )
            self.db.add(institution)
            self.db.flush()
            
            # If user is also institution admin
            if payload.get('is_institution_admin', False):
                inst_admin_role = self.db.query(Role).filter(
                    Role.name == RoleName.INSTITUTION_ADMIN
                ).first()
                if inst_admin_role:
                    inst_membership = UserMembership(
                        user_id=user.id,
                        scope_type=ScopeType.INSTITUTION,
                        scope_id=institution.id,
                        role_id=inst_admin_role.id,
                        is_active=True,
                    )
                    self.db.add(inst_membership)
                    memberships.append(inst_membership)
        
        self.db.commit()
        self.db.refresh(user)
        
        # Audit log (non-blocking - don't fail signup if audit fails)
        try:
            self.audit.log_event(
                self.db,
                AuditEventType.USER_CREATED,
                f"Organization admin signup: {user.email}",
                actor_user_id=user.id,
                tenant_id=org.id,
                target_user_id=user.id,
            )
        except Exception as audit_error:
            logger.warning(f"Audit logging failed (non-critical): {audit_error}")
        
        return {
            'user': user,
            'memberships': memberships,
        }


class InstitutionAdminSignupStrategy(SignupStrategy):
    """Strategy for Institution Admin signup."""
    
    def validate_payload(self, payload: Dict[str, Any]) -> bool:
        """Validate institution admin signup payload."""
        required = ['email', 'password', 'first_name', 'last_name', 'institution']
        return all(key in payload for key in required)
    
    def execute(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Execute institution admin signup."""
        # Check if user already exists
        existing_user = self.db.query(User).filter(
            User.email == payload['email'].lower()
        ).first()
        if existing_user:
            raise UserAlreadyExistsError()
        
        # Validate password
        is_valid, error_msg = validate_password_strength(payload['password'])
        if not is_valid:
            raise PasswordValidationError(error_msg)
        
        # Create or get organization (solo organization for institution)
        from app.domains.auth.services import TenantService
        tenant_service = TenantService(self.db)
        
        inst_data = payload['institution']
        org_name = inst_data.get('organization_name', f"{inst_data['name']} Organization")
        org_slug = org_name.lower().replace(' ', '-')
        
        # Create organization tenant
        platform = self.db.query(Tenant).filter(
            Tenant.type == TenantType.PLATFORM,
            Tenant.is_active == True
        ).first()
        if not platform:
            platform = tenant_service.create_platform_tenant()
        
        hierarchy_path = f"/org-{org_slug}/"
        org = Tenant(
            name=org_name,
            slug=org_slug,
            type=TenantType.ORGANIZATION,
            parent_tenant_id=platform.id,
            hierarchy_path=hierarchy_path,
            is_active=True,
        )
        self.db.add(org)
        self.db.flush()
        
        # Create institution
        institution = Institution(
            name=inst_data['name'],
            slug=inst_data.get('slug', inst_data['name'].lower().replace(' ', '-')),
            institution_type=InstitutionType(inst_data.get('institution_type', 'k12_school')),
            organization_id=org.id,
            settings=inst_data.get('settings'),
        )
        self.db.add(institution)
        self.db.flush()
        
        # Create user
        user = User(
            email=payload['email'].lower(),
            password_hash=hash_password(payload['password']),
            first_name=payload['first_name'],
            last_name=payload['last_name'],
            full_name=f"{payload['first_name']} {payload['last_name']}".strip(),
            phone=payload.get('phone'),
            tenant_id=org.id,  # User's tenant_id references Tenant (org), not Institution
            status=UserStatus.ACTIVE,
            email_verified=settings.ENVIRONMENT != "prod",
            preferences=_default_user_preferences(payload.get("language")),
        )
        self.db.add(user)
        self.db.flush()
        
        # Assign INSTITUTION_ADMIN role
        inst_admin_role = self.db.query(Role).filter(
            Role.name == RoleName.INSTITUTION_ADMIN
        ).first()
        if inst_admin_role:
            # Create membership for institution
            membership = UserMembership(
                user_id=user.id,
                scope_type=ScopeType.INSTITUTION,
                scope_id=institution.id,
                role_id=inst_admin_role.id,
                is_active=True,
            )
            self.db.add(membership)
            
            # Also create UserRole for backward compatibility
            user_role = UserRole(
                user_id=user.id,
                role_id=inst_admin_role.id,
                tenant_id=org.id,  # Use org tenant for backward compatibility
            )
            self.db.add(user_role)
        
        self.db.commit()
        self.db.refresh(user)
        
        # Audit log (non-blocking - don't fail signup if audit fails)
        try:
            self.audit.log_event(
                self.db,
                AuditEventType.USER_CREATED,
                f"Institution admin signup: {user.email}",
                actor_user_id=user.id,
                tenant_id=org.id,
                target_user_id=user.id,
            )
        except Exception as audit_error:
            logger.warning(f"Audit logging failed (non-critical): {audit_error}")
        
        return {
            'user': user,
            'memberships': [membership],
        }


class TeacherSignupStrategy(SignupStrategy):
    """Strategy for Teacher signup."""
    
    def validate_payload(self, payload: Dict[str, Any]) -> bool:
        """Validate teacher signup payload."""
        required = ['email', 'password', 'first_name', 'last_name']
        return all(key in payload for key in required)
    
    def execute(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Execute teacher signup."""
        # Check if user already exists - use index for fast lookup
        existing_user = self.db.query(User).filter(
            User.email == payload['email'].lower()
        ).first()
        if existing_user:
            raise UserAlreadyExistsError()
        
        # Validate password
        is_valid, error_msg = validate_password_strength(payload['password'])
        if not is_valid:
            raise PasswordValidationError(error_msg)
        
        # Determine scope
        institution_id = None
        personal_workspace = None
        status = UserStatus.ACTIVE
        email_verified = settings.ENVIRONMENT != "prod"
        
        if payload.get('institution_code'):
            # Signup with institution
            institution = self.db.query(Institution).filter(
                Institution.slug == payload['institution_code'],
                Institution.is_active == True,
            ).first()
            
            if not institution:
                raise ValueError(f"Institution with code {payload['institution_code']} not found")
            
            institution_id = institution.id
            status = UserStatus.PENDING_APPROVAL
            email_verified = False
            tenant_id = institution.organization_id  # Use org tenant for backward compatibility
        else:
            # Individual account - create personal workspace
            platform = self.db.query(Tenant).filter(
                Tenant.type == TenantType.PLATFORM,
                Tenant.is_active == True
            ).first()
            if not platform:
                from app.domains.auth.services import TenantService
                platform = TenantService(self.db).create_platform_tenant()
            tenant_id = platform.id
            # Personal workspace will be created after user creation
        
        # Create user
        user = User(
            email=payload['email'].lower(),
            password_hash=hash_password(payload['password']),
            first_name=payload['first_name'],
            last_name=payload['last_name'],
            full_name=f"{payload['first_name']} {payload['last_name']}".strip(),
            phone=payload.get('phone'),
            tenant_id=tenant_id,
            status=status,
            email_verified=email_verified,
            preferences=_default_user_preferences(payload.get("language")),
        )
        self.db.add(user)
        self.db.flush()
        
        # Get teacher role
        teacher_role = self.db.query(Role).filter(Role.name == RoleName.TEACHER).first()
        memberships = []
        
        if teacher_role:
            if institution_id:
                # Create membership for institution
                membership = UserMembership(
                    user_id=user.id,
                    scope_type=ScopeType.INSTITUTION,
                    scope_id=institution_id,
                    role_id=teacher_role.id,
                    is_active=True,
                )
                self.db.add(membership)
                memberships.append(membership)
                
                # Also create UserRole for backward compatibility
                user_role = UserRole(
                    user_id=user.id,
                    role_id=teacher_role.id,
                    tenant_id=tenant_id,
                )
                self.db.add(user_role)
            else:
                # Create personal workspace
                personal_workspace = PersonalWorkspace(
                    user_id=user.id,
                    name="Personal Workspace",
                )
                self.db.add(personal_workspace)
                self.db.flush()

                # Create membership for personal workspace
                membership = UserMembership(
                    user_id=user.id,
                    scope_type=ScopeType.PERSONAL_WORKSPACE,
                    scope_id=personal_workspace.id,
                    role_id=teacher_role.id,
                    is_active=True,
                )
                self.db.add(membership)
                memberships.append(membership)

                # Also create UserRole for backward compatibility (required by require_any_role)
                user_role = UserRole(
                    user_id=user.id,
                    role_id=teacher_role.id,
                    tenant_id=tenant_id,
                )
                self.db.add(user_role)

        if not memberships:
            # If no membership was created, create a default one
            logger.warning(f"No teacher role found or membership creation failed for user {user.email}")
        
        self.db.commit()
        self.db.refresh(user)
        
        # Audit log (non-blocking - don't fail signup if audit fails)
        try:
            account_type = "institution account" if institution_id else "personal workspace"
            self.audit.log_event(
                self.db,
                AuditEventType.USER_CREATED,
                f"Teacher signup ({account_type}): {user.email}",
                actor_user_id=user.id,
                tenant_id=tenant_id,
                target_user_id=user.id,
            )
        except Exception as audit_error:
            logger.warning(f"Audit logging failed (non-critical): {audit_error}")
            # Don't fail signup if audit logging fails
        
        return {
            'user': user,
            'memberships': memberships,
        }


class StudentSignupStrategy(SignupStrategy):
    """Strategy for Student signup."""
    
    def validate_payload(self, payload: Dict[str, Any]) -> bool:
        """Validate student signup payload."""
        required = ['email', 'password', 'first_name', 'last_name']
        return all(key in payload for key in required)
    
    def execute(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Execute student signup."""
        # Similar to teacher signup but with student role
        # Check if user already exists
        existing_user = self.db.query(User).filter(
            User.email == payload['email'].lower()
        ).first()
        if existing_user:
            raise UserAlreadyExistsError()
        
        # Validate password
        is_valid, error_msg = validate_password_strength(payload['password'])
        if not is_valid:
            raise PasswordValidationError(error_msg)
        
        # Determine scope
        institution_id = None
        status = UserStatus.ACTIVE
        email_verified = settings.ENVIRONMENT != "prod"
        
        if payload.get('institution_code'):
            institution = self.db.query(Institution).filter(
                Institution.slug == payload['institution_code'],
                Institution.is_active == True,
            ).first()
            
            if not institution:
                raise ValueError(f"Institution with code {payload['institution_code']} not found")
            
            institution_id = institution.id
            status = UserStatus.PENDING_VERIFICATION
            email_verified = False
            tenant_id = institution.organization_id
        else:
            platform = self.db.query(Tenant).filter(
                Tenant.type == TenantType.PLATFORM,
                Tenant.is_active == True
            ).first()
            if not platform:
                raise ValueError("Platform tenant not found")
            tenant_id = platform.id
        
        # Create user
        user = User(
            email=payload['email'].lower(),
            password_hash=hash_password(payload['password']),
            first_name=payload['first_name'],
            last_name=payload['last_name'],
            full_name=f"{payload['first_name']} {payload['last_name']}".strip(),
            phone=payload.get('phone'),
            tenant_id=tenant_id,
            status=status,
            email_verified=email_verified,
            preferences=_default_user_preferences(payload.get("language")),
        )
        self.db.add(user)
        self.db.flush()
        
        # Get student role
        student_role = self.db.query(Role).filter(Role.name == RoleName.STUDENT).first()
        memberships = []
        
        if student_role:
            if institution_id:
                membership = UserMembership(
                    user_id=user.id,
                    scope_type=ScopeType.INSTITUTION,
                    scope_id=institution_id,
                    role_id=student_role.id,
                    is_active=True,
                )
                self.db.add(membership)
                memberships.append(membership)
                
                user_role = UserRole(
                    user_id=user.id,
                    role_id=student_role.id,
                    tenant_id=tenant_id,
                )
                self.db.add(user_role)
            else:
                personal_workspace = PersonalWorkspace(
                    user_id=user.id,
                    name="Personal Workspace",
                )
                self.db.add(personal_workspace)
                self.db.flush()

                membership = UserMembership(
                    user_id=user.id,
                    scope_type=ScopeType.PERSONAL_WORKSPACE,
                    scope_id=personal_workspace.id,
                    role_id=student_role.id,
                    is_active=True,
                )
                self.db.add(membership)
                memberships.append(membership)

                # Also create UserRole for backward compatibility (required by require_any_role)
                user_role = UserRole(
                    user_id=user.id,
                    role_id=student_role.id,
                    tenant_id=tenant_id,
                )
                self.db.add(user_role)

        self.db.commit()
        self.db.refresh(user)

        # Audit log (non-blocking - don't fail signup if audit fails)
        try:
            account_type = "institution account" if institution_id else "personal workspace"
            self.audit.log_event(
                self.db,
                AuditEventType.USER_CREATED,
                f"Student signup ({account_type}): {user.email}",
                actor_user_id=user.id,
                tenant_id=tenant_id,
                target_user_id=user.id,
            )
        except Exception as audit_error:
            logger.warning(f"Audit logging failed (non-critical): {audit_error}")
        
        return {
            'user': user,
            'memberships': memberships,
        }


class ParentSignupStrategy(SignupStrategy):
    """Strategy for Parent signup."""
    
    def validate_payload(self, payload: Dict[str, Any]) -> bool:
        """Validate parent signup payload."""
        required = ['email', 'password', 'first_name', 'last_name', 'student_code']
        return all(key in payload for key in required)
    
    def execute(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Execute parent signup."""
        # Find student by code
        student = self.db.query(User).join(UserRole).join(Role).filter(
            Role.name == RoleName.STUDENT,
            or_(
                User.email == payload['student_code'].lower(),
                User.username == payload['student_code'],
            )
        ).first()
        
        if not student:
            raise ValueError(f"Student with code {payload['student_code']} not found")
        
        # Check if parent already exists
        existing_user = self.db.query(User).filter(
            User.email == payload['email'].lower()
        ).first()
        if existing_user:
            raise UserAlreadyExistsError()
        
        # Validate password
        is_valid, error_msg = validate_password_strength(payload['password'])
        if not is_valid:
            raise PasswordValidationError(error_msg)
        
        # Create user
        user = User(
            email=payload['email'].lower(),
            password_hash=hash_password(payload['password']),
            first_name=payload['first_name'],
            last_name=payload['last_name'],
            full_name=f"{payload['first_name']} {payload['last_name']}".strip(),
            phone=payload.get('phone'),
            tenant_id=student.tenant_id,
            status=UserStatus.ACTIVE,
            email_verified=settings.ENVIRONMENT != "prod",
            preferences=_default_user_preferences(payload.get("language")),
        )
        self.db.add(user)
        self.db.flush()
        
        # Get parent role
        parent_role = self.db.query(Role).filter(Role.name == RoleName.PARENT).first()
        memberships = []
        
        if parent_role:
            # Get student's membership to determine scope
            student_membership = self.db.query(UserMembership).filter(
                UserMembership.user_id == student.id,
                UserMembership.is_active == True,
            ).first()
            
            if student_membership:
                # Create membership in same scope as student
                membership = UserMembership(
                    user_id=user.id,
                    scope_type=student_membership.scope_type,
                    scope_id=student_membership.scope_id,
                    role_id=parent_role.id,
                    is_active=True,
                )
                self.db.add(membership)
                memberships.append(membership)
            
            # Also create UserRole for backward compatibility
            user_role = UserRole(
                user_id=user.id,
                role_id=parent_role.id,
                tenant_id=student.tenant_id,
            )
            self.db.add(user_role)
        
        # Link parent to student
        from app.domains.auth.models import ParentStudentLink
        link = ParentStudentLink(
            parent_id=user.id,
            student_id=student.id,
            is_verified=False,
        )
        self.db.add(link)
        
        self.db.commit()
        self.db.refresh(user)
        
        # Audit log (non-blocking - don't fail signup if audit fails)
        try:
            self.audit.log_event(
                self.db,
                AuditEventType.USER_CREATED,
                f"Parent signup: {user.email}",
                actor_user_id=user.id,
                tenant_id=student.tenant_id,
                target_user_id=user.id,
            )
        except Exception as audit_error:
            logger.warning(f"Audit logging failed (non-critical): {audit_error}")
        
        return {
            'user': user,
            'memberships': memberships,
        }


class InviteAcceptanceStrategy(SignupStrategy):
    """Strategy for accepting an invite."""
    
    def validate_payload(self, payload: Dict[str, Any]) -> bool:
        """Validate invite acceptance payload."""
        required = ['invite_token', 'password', 'first_name', 'last_name']
        return all(key in payload for key in required)
    
    def execute(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Execute invite acceptance."""
        from app.core.security import hash_token
        
        # Find invite by token
        token_hash = hash_token(payload['invite_token'])
        invite = self.db.query(Invite).filter(
            Invite.token_hash == token_hash,
            Invite.status == InviteStatus.PENDING,
            Invite.expires_at > datetime.now(timezone.utc),
        ).first()
        
        if not invite:
            raise InvalidTokenError("Invalid or expired invite token")
        
        # Check if user already exists
        existing_user = self.db.query(User).filter(
            User.email == invite.email.lower()
        ).first()
        
        if existing_user:
            # User exists - just create membership
            user = existing_user
            is_new_user = False
        else:
            # Create new user
            is_valid, error_msg = validate_password_strength(payload['password'])
            if not is_valid:
                raise PasswordValidationError(error_msg)
            
            # Determine tenant_id based on scope
            if invite.scope_type == ScopeType.INSTITUTION:
                institution = self.db.query(Institution).filter(
                    Institution.id == invite.scope_id
                ).first()
                tenant_id = institution.organization_id if institution else None
            elif invite.scope_type == ScopeType.ORGANIZATION:
                tenant_id = invite.scope_id
            else:
                platform = self.db.query(Tenant).filter(
                    Tenant.type == TenantType.PLATFORM
                ).first()
                tenant_id = platform.id if platform else None
            
            user = User(
                email=invite.email.lower(),
                password_hash=hash_password(payload['password']),
                first_name=payload['first_name'],
                last_name=payload['last_name'],
                full_name=f"{payload['first_name']} {payload['last_name']}".strip(),
                phone=payload.get('phone'),
                tenant_id=tenant_id,
                status=UserStatus.ACTIVE,
                email_verified=True,  # Invites are pre-verified
                preferences=_default_user_preferences(payload.get("language")),
            )
            self.db.add(user)
            self.db.flush()
            is_new_user = True
        
        # Create membership
        membership = UserMembership(
            user_id=user.id,
            scope_type=invite.scope_type,
            scope_id=invite.scope_id,
            role_id=invite.role_id,
            is_active=True,
            granted_by=invite.invited_by,
        )
        self.db.add(membership)
        
        # Also create UserRole for backward compatibility
        user_role = UserRole(
            user_id=user.id,
            role_id=invite.role_id,
            tenant_id=user.tenant_id,
            granted_by=invite.invited_by,
        )
        self.db.add(user_role)
        
        # Update invite
        invite.status = InviteStatus.ACCEPTED
        invite.accepted_at = datetime.now(timezone.utc)
        invite.accepted_by_user_id = user.id
        
        self.db.commit()
        self.db.refresh(user)
        
        # Audit log (non-blocking - don't fail signup if audit fails)
        try:
            action = "Invite accepted (new user)" if is_new_user else "Invite accepted (existing user)"
            self.audit.log_event(
                self.db,
                AuditEventType.USER_CREATED if is_new_user else AuditEventType.ROLE_ASSIGNED,
                f"{action}: {user.email}",
                actor_user_id=user.id,
                target_user_id=user.id,
            )
        except Exception as audit_error:
            logger.warning(f"Audit logging failed (non-critical): {audit_error}")
        
        return {
            'user': user,
            'memberships': [membership],
        }


class SignupService:
    """Service for routing signup requests to appropriate strategies."""
    
    def __init__(self, db: Session):
        self.db = db
        self.strategies = {
            'org_admin': OrgAdminSignupStrategy(db),
            'institution_admin': InstitutionAdminSignupStrategy(db),
            'teacher': TeacherSignupStrategy(db),
            'student': StudentSignupStrategy(db),
            'parent': ParentSignupStrategy(db),
            'invite': InviteAcceptanceStrategy(db),
        }
    
    def route(self, role: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Route signup request to appropriate strategy.
        
        Args:
            role: Signup role (org_admin, institution_admin, teacher, student, parent, invite)
            payload: Signup payload
            
        Returns:
            Dict with user, memberships, and optionally tokens
        """
        # Handle invite acceptance (special case)
        if 'invite_token' in payload:
            strategy = self.strategies['invite']
        else:
            strategy = self.strategies.get(role)
            if not strategy:
                raise ValueError(f"Unknown signup role: {role}")
        
        # Validate payload
        if not strategy.validate_payload(payload):
            raise ValueError(f"Invalid payload for {role} signup")
        
        # Execute strategy
        return strategy.execute(payload)
