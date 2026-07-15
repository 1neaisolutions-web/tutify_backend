"""
Authentication and authorization business logic services.
"""
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from uuid import UUID

from fastapi import UploadFile, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from email_validator import validate_email, EmailNotValidError

from app.core.config import settings
from app.core.security import (
    hash_password,
    verify_password,
    validate_password_strength,
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_token_string,
)
from app.core.exceptions import (
    InvalidCredentialsError,
    AccountLockedError,
    UserNotFoundError,
    UserAlreadyExistsError,
    EmailNotVerifiedError,
    InvalidTokenError,
    PasswordValidationError,
)
from app.core.logging import get_logger
from app.domains.auth.models import (
    User,
    Tenant,
    Role,
    Permission,
    RolePermission,
    UserRole,
    UserMembership,
    RefreshToken,
    PasswordResetToken,
    EmailVerificationToken,
    ParentStudentLink,
    AuditLog,
    UserStatus,
    RoleName,
    RoleScope,
    TenantType,
    ScopeType,
    AuditEventType,
)
from app.domains.auth.schemas import (
    RegisterRequest,
    LoginRequest,
    UserCreate,
    UserUpdate,
    CreateOrganizationRequest,
    CreateSchoolRequest,
    CreateUserRequest,
    TeacherSignupRequest,
    StudentSignupRequest,
    ParentSignupRequest,
)
from app.utils.email import (
    send_email,
    create_verification_email_template,
    create_password_reset_email_template,
    create_invitation_email_template,
)
from app.utils.file_storage import file_storage_service

logger = get_logger(__name__)


def hash_token(token: str) -> str:
    """Hash a token for storage."""
    return hashlib.sha256(token.encode()).hexdigest()


class AuditService:
    """Service for audit logging."""
    
    @staticmethod
    def log_event(
        db: Session,
        event_type: AuditEventType,
        description: str,
        actor_user_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
        target_user_id: Optional[UUID] = None,
        target_type: Optional[str] = None,
        event_metadata: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> AuditLog:
        """Log an audit event."""
        audit_log = AuditLog(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            actor_type="user" if actor_user_id else "system",
            target_user_id=target_user_id,
            target_type=target_type,
            event_type=event_type,
            description=description,
            event_metadata=event_metadata or {},
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
        )
        db.add(audit_log)
        db.commit()
        db.refresh(audit_log)
        return audit_log


class AuthService:
    """Service for authentication operations."""
    
    def __init__(self, db: Session):
        self.db = db
        self.audit = AuditService()
    
    def register(self, request: RegisterRequest, tenant_id: UUID) -> tuple[User, str]:
        """
        Register a new user.
        
        Returns:
            Tuple of (user, verification_token)
        """
        # Check if user already exists
        existing_user = self.db.query(User).filter(User.email == request.email.lower()).first()
        if existing_user:
            raise UserAlreadyExistsError("User with this email already exists")
        
        # Validate password
        is_valid, error_msg = validate_password_strength(request.password)
        if not is_valid:
            raise PasswordValidationError(error_msg)
        
        # Get tenant
        tenant = self.db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            raise ValueError(f"Tenant {tenant_id} not found")
        
        # Create user
        full_name = f"{request.first_name} {request.last_name}".strip()
        # Auto-verify in dev/staging mode for easier testing
        auto_verify = settings.ENVIRONMENT != "prod"
        user = User(
            email=request.email.lower(),
            password_hash=hash_password(request.password),
            first_name=request.first_name,
            last_name=request.last_name,
            full_name=full_name,
            phone=request.phone,
            tenant_id=tenant_id,
            status=UserStatus.ACTIVE if auto_verify else UserStatus.PENDING_VERIFICATION,
            email_verified=auto_verify,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        
        # Create verification token only if not auto-verified
        token_string = None
        if not auto_verify:
            token_string = generate_token_string()
            token_hash = hash_token(token_string)
            expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES)
            
            verification_token = EmailVerificationToken(
                user_id=user.id,
                token_hash=token_hash,
                expires_at=expires_at,
            )
            self.db.add(verification_token)
            self.db.commit()
            
            # Send verification email (truly non-blocking - don't fail registration if email fails)
            # Email sending is moved to background task to prevent blocking
            try:
                subject, html_content, text_content = create_verification_email_template(user.email, token_string)
                # Log that email should be sent, but don't actually send it here to avoid blocking
                # In production, this should be handled by a background task queue (Celery, etc.)
                # For now, just log - the email template is ready but sending is deferred
                logger.info(f"Verification email prepared for {user.email} (sending deferred to background task)")
            except Exception as e:
                logger.warning(f"Failed to prepare verification email for {user.email}: {str(e)}")
                # Don't fail registration if email preparation fails
        else:
            logger.info(f"User {user.email} auto-verified (dev mode)")
        
        # Log event (don't fail registration if audit logging fails)
        # Use try-except with timeout protection
        try:
            # Use a separate session for audit to avoid blocking
            self.audit.log_event(
                self.db,
                AuditEventType.USER_CREATED,
                f"User registered: {user.email}",
                actor_user_id=user.id,
                tenant_id=tenant_id,
                target_user_id=user.id,
                target_type="user",
            )
            self.db.commit()  # Commit audit log
        except Exception as e:
            logger.warning(f"Failed to log audit event for user registration: {str(e)}")
            self.db.rollback()  # Rollback only audit log, user is already committed
            # Don't fail registration if audit logging fails
        
        logger.info(f"User registered: {user.email}")
        return user, token_string
    
    def login(
        self,
        request: LoginRequest,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> tuple[str, str, User]:
        """
        Authenticate user and return tokens (step 1 of login).
        
        This method now supports challenge-based login:
        - If user has multiple memberships → returns challenge response
        - If user has single membership → returns tokens directly
        
        Returns:
            Tuple of (access_token, refresh_token, user) OR raises challenge
        """
        # Step 1: Authenticate email + password
        if not request.email or not request.password:
            raise ValueError("Email and password are required for step 1")
        
        # Find user - use index on email for fast lookup
        logger.debug(f"Looking up user with email: {request.email.lower()}")
        user = self.db.query(User).filter(User.email == request.email.lower()).first()
        if not user:
            # Log failed attempt (non-blocking - don't let audit logging slow down response)
            try:
                self.audit.log_event(
                    self.db,
                    AuditEventType.LOGIN_FAILURE,
                    f"Login attempt failed: {request.email} (user not found)",
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
                self.db.commit()
            except Exception as audit_error:
                logger.warning(f"Audit logging failed (non-critical): {audit_error}")
                self.db.rollback()
            raise InvalidCredentialsError()
        
        # Check if account is locked
        if user.locked_until and user.locked_until > datetime.now(timezone.utc):
            raise AccountLockedError(f"Account is locked until {user.locked_until}")
        
        # Verify password
        if not verify_password(request.password, user.password_hash):
            # Increment failed attempts
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= settings.MAX_LOGIN_ATTEMPTS:
                user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=settings.LOCKOUT_DURATION_MINUTES)
                self.audit.log_event(
                    self.db,
                    AuditEventType.ACCOUNT_LOCKED,
                    f"Account locked due to too many failed login attempts: {user.email}",
                    target_user_id=user.id,
                    tenant_id=user.tenant_id,
                    ip_address=ip_address,
                )
            
            self.db.commit()
            
            # Log failed attempt (non-blocking)
            try:
                self.audit.log_event(
                    self.db,
                    AuditEventType.LOGIN_FAILURE,
                    f"Login attempt failed: {user.email} (invalid password)",
                    actor_user_id=user.id,
                    tenant_id=user.tenant_id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
                self.db.commit()
            except Exception:
                self.db.rollback()
            raise InvalidCredentialsError()
        
        # Check email verification (optional in dev mode for testing)
        if not user.email_verified and settings.ENVIRONMENT == "prod":
            raise EmailNotVerifiedError()
        elif not user.email_verified:
            # In dev/staging, auto-verify for testing purposes
            user.email_verified = True
            self.db.commit()
        
        # Check status - allow PENDING_VERIFICATION in dev mode
        if user.status == UserStatus.INACTIVE:
            raise InvalidCredentialsError(f"Account is inactive")
        elif user.status == UserStatus.PENDING_VERIFICATION and settings.ENVIRONMENT == "prod":
            raise InvalidCredentialsError(f"Account requires verification")
        elif user.status == UserStatus.PENDING_VERIFICATION:
            # Auto-activate in dev/staging mode for testing
            user.status = UserStatus.ACTIVE
            self.db.commit()
        
        # Reset failed attempts
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login_at = datetime.now(timezone.utc)
        self.db.commit()
        
        # Check user memberships - use direct query for speed
        logger.debug(f"Checking memberships for user: {user.id}")
        try:
            # Direct query is faster than service layer
            from app.domains.auth.models import UserMembership
            memberships = self.db.query(UserMembership).filter(
                UserMembership.user_id == user.id,
                UserMembership.is_active == True
            ).limit(10).all()  # Limit to prevent slow queries
        except Exception as membership_error:
            logger.error(f"Error fetching memberships: {membership_error}")
            # Rollback transaction if it failed, then continue with empty memberships list
            try:
                self.db.rollback()
            except Exception:
                pass  # Ignore rollback errors
            memberships = []
        
        # If multiple memberships, we need to return challenge
        # Store this info in user object temporarily (route will handle challenge response)
        # For now, we'll proceed with single membership logic
        # The route will check memberships and return challenge if needed
        
        # Single membership or no membership - proceed with login
        active_membership_id = None
        if len(memberships) == 1:
            active_membership_id = memberships[0].id
        
        # Create tokens
        access_token = create_access_token({
            "user_id": str(user.id),
            "email": user.email,
            "tenant_id": str(user.tenant_id),
            "membership_id": str(active_membership_id) if active_membership_id else None,
        })
        
        refresh_token_string = create_refresh_token({"user_id": str(user.id)})
        refresh_token_hash = hash_token(refresh_token_string)
        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        
        refresh_token = RefreshToken(
            user_id=user.id,
            token_hash=refresh_token_hash,
            device_info={"ip_address": ip_address, "user_agent": user_agent} if ip_address or user_agent else None,
            expires_at=expires_at,
            active_membership_id=active_membership_id,
        )
        try:
            self.db.add(refresh_token)
            self.db.commit()
        except Exception as token_error:
            # If commit fails, rollback and re-raise
            logger.error(f"Error saving refresh token: {token_error}")
            self.db.rollback()
            raise
        
        # Log success (non-blocking)
        try:
            self.audit.log_event(
                self.db,
                AuditEventType.LOGIN_SUCCESS,
                f"User logged in: {user.email}",
                actor_user_id=user.id,
                tenant_id=user.tenant_id,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
        
        logger.info(f"User logged in: {user.email}")
        return access_token, refresh_token_string, user
    
    def complete_login_challenge(
        self,
        login_token: str,
        selected_membership_id: UUID,
        scope_type: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> tuple[str, str, User]:
        """
        Complete login challenge (step 2) - handle tenant selection.
        
        Args:
            login_token: Short-lived token from step 1
            selected_membership_id: Selected membership ID
            scope_type: Scope type of selected membership
            ip_address: Client IP address
            user_agent: Client user agent
            
        Returns:
            Tuple of (access_token, refresh_token, user)
        """
        # For now, we'll use a simple approach: decode login_token to get user_id
        # In production, you might want to use Redis or similar for short-lived tokens
        try:
            token_data = decode_token(login_token)
            user_id = UUID(token_data.get("user_id"))
        except Exception:
            raise InvalidTokenError("Invalid login token")
        
        # Get user
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise InvalidCredentialsError()
        
        # Verify membership belongs to user
        membership = self.db.query(UserMembership).filter(
            UserMembership.id == selected_membership_id,
            UserMembership.user_id == user.id,
            UserMembership.is_active == True,
            UserMembership.scope_type == scope_type,
        ).first()
        
        if not membership:
            raise ValueError("Invalid membership selection")
        
        # Create tokens with membership context
        access_token = create_access_token({
            "user_id": str(user.id),
            "email": user.email,
            "tenant_id": str(user.tenant_id),
            "membership_id": str(membership.id),
        })
        
        refresh_token_string = create_refresh_token({"user_id": str(user.id)})
        refresh_token_hash = hash_token(refresh_token_string)
        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        
        refresh_token = RefreshToken(
            user_id=user.id,
            token_hash=refresh_token_hash,
            device_info={"ip_address": ip_address, "user_agent": user_agent} if ip_address or user_agent else None,
            expires_at=expires_at,
            active_membership_id=membership.id,
        )
        self.db.add(refresh_token)
        self.db.commit()
        
        # Log success
        try:
            self.audit.log_event(
                self.db,
                AuditEventType.LOGIN_SUCCESS,
                f"User logged in (tenant selected): {user.email}",
                actor_user_id=user.id,
                tenant_id=user.tenant_id,
                ip_address=ip_address,
                user_agent=user_agent,
                event_metadata={
                    "membership_id": str(membership.id),
                    "scope_type": scope_type,
                },
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
        
        return access_token, refresh_token_string, user
    
    def get_login_challenge_data(
        self,
        user: User,
    ) -> tuple[str, List[UserMembership]]:
        """
        Get challenge data for login (when user has multiple memberships).
        
        Args:
            user: Authenticated user
            
        Returns:
            Tuple of (login_token, memberships list)
        """
        from app.domains.auth.services.membership_service import MembershipService
        membership_service = MembershipService(self.db)
        memberships = membership_service.get_user_memberships(user.id, active_only=True)
        
        if len(memberships) <= 1:
            raise ValueError("User does not have multiple memberships")
        
        # Generate short-lived login token (5 minutes)
        login_token = create_access_token(
            {"user_id": str(user.id), "purpose": "login_challenge"},
            expires_delta=timedelta(minutes=5)
        )
        
        return login_token, memberships

    def create_mfa_login_token(self, user: User) -> str:
        """Short-lived token for MFA enrollment/verification during login."""
        return create_access_token(
            {"user_id": str(user.id), "purpose": "mfa_challenge"},
            expires_delta=timedelta(minutes=10),
        )

    def complete_mfa_login(
        self,
        login_token: str,
        code: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        enroll: bool = False,
    ) -> tuple[str, str, User]:
        """Complete MFA challenge and issue tokens with mfa_verified claim."""
        from app.domains.auth.services.mfa_service import MfaService

        try:
            token_data = decode_token(login_token)
            if token_data.get("purpose") not in ("mfa_challenge", "login_challenge"):
                raise InvalidTokenError("Invalid login token")
            user_id = UUID(token_data.get("user_id"))
        except Exception:
            raise InvalidTokenError("Invalid login token")

        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise InvalidCredentialsError()

        mfa = MfaService(self.db)
        if enroll:
            mfa.verify_and_enable(user, code)
        elif not mfa.verify_code(user, code):
            raise InvalidCredentialsError("Invalid MFA code")

        access_token = create_access_token({
            "user_id": str(user.id),
            "email": user.email,
            "tenant_id": str(user.tenant_id),
            "mfa_verified": True,
        })
        refresh_token_string = create_refresh_token({"user_id": str(user.id)})
        refresh_token_hash = hash_token(refresh_token_string)
        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        refresh_token = RefreshToken(
            user_id=user.id,
            token_hash=refresh_token_hash,
            device_info={"ip_address": ip_address, "user_agent": user_agent} if ip_address or user_agent else None,
            expires_at=expires_at,
        )
        self.db.add(refresh_token)
        self.db.commit()

        try:
            self.audit.log_event(
                self.db,
                AuditEventType.LOGIN_SUCCESS,
                f"Super admin logged in with MFA: {user.email}",
                actor_user_id=user.id,
                tenant_id=user.tenant_id,
                ip_address=ip_address,
                user_agent=user_agent,
                event_metadata={"mfa_verified": True},
            )
            self.db.commit()
        except Exception:
            self.db.rollback()

        return access_token, refresh_token_string, user
    
    def refresh_access_token(self, refresh_token_string: str) -> str:
        """Refresh access token using refresh token."""
        # Hash the token
        token_hash = hash_token(refresh_token_string)
        
        # Find refresh token
        refresh_token = self.db.query(RefreshToken).filter(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > datetime.now(timezone.utc),
        ).first()
        
        if not refresh_token:
            raise InvalidTokenError("Invalid or expired refresh token")
        
        # Get user
        user = self.db.query(User).filter(User.id == refresh_token.user_id).first()
        if not user or user.status != UserStatus.ACTIVE:
            raise InvalidTokenError("User not found or inactive")
        
        # Update last used
        refresh_token.last_used_at = datetime.now(timezone.utc)
        self.db.commit()
        
        # Create new access token
        access_token = create_access_token({
            "user_id": str(user.id),
            "email": user.email,
            "tenant_id": str(user.tenant_id),
        })
        
        return access_token
    
    def logout(self, refresh_token_string: str, user_id: UUID) -> None:
        """Logout user by revoking refresh token."""
        token_hash = hash_token(refresh_token_string)
        
        refresh_token = self.db.query(RefreshToken).filter(
            RefreshToken.token_hash == token_hash,
            RefreshToken.user_id == user_id,
        ).first()
        
        if refresh_token:
            refresh_token.revoked_at = datetime.now(timezone.utc)
            refresh_token.revoked_reason = "logout"
            self.db.commit()
            
            self.audit.log_event(
                self.db,
                AuditEventType.LOGOUT,
                "User logged out",
                actor_user_id=user_id,
            )
    
    def forgot_password(self, email: str, ip_address: Optional[str] = None) -> Optional[tuple[str, str, str, str]]:
        """
        Initiate password reset.
        
        Returns:
            Tuple of (user_email, subject, html_content, text_content) if user exists, None otherwise.
            This allows the route to send the email asynchronously.
        """
        user = self.db.query(User).filter(User.email == email.lower()).first()
        if not user:
            # Don't reveal if user exists
            return None
        
        # Create reset token
        token_string = generate_token_string()
        token_hash = hash_token(token_string)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES)
        
        reset_token = PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
            ip_address=ip_address,
        )
        self.db.add(reset_token)
        self.db.commit()
        
        # Prepare password reset email
        try:
            subject, html_content, text_content = create_password_reset_email_template(user.email, token_string)
            email_data = (user.email, subject, html_content, text_content)
            logger.info(f"Password reset email prepared for {user.email}")
        except Exception as e:
            logger.warning(f"Failed to prepare password reset email for {user.email}: {str(e)}")
            email_data = None
        
        self.audit.log_event(
            self.db,
            AuditEventType.PASSWORD_RESET_REQUESTED,
            f"Password reset requested: {user.email}",
            actor_user_id=user.id,
            tenant_id=user.tenant_id,
            ip_address=ip_address,
        )
        
        return email_data
    
    def reset_password(self, token_string: str, new_password: str) -> None:
        """Reset password using token."""
        token_hash = hash_token(token_string)
        
        reset_token = self.db.query(PasswordResetToken).filter(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > datetime.now(timezone.utc),
        ).first()
        
        if not reset_token:
            raise InvalidTokenError("Invalid or expired reset token")
        
        # Validate password
        is_valid, error_msg = validate_password_strength(new_password)
        if not is_valid:
            raise PasswordValidationError(error_msg)
        
        # Update password
        user = self.db.query(User).filter(User.id == reset_token.user_id).first()
        if not user:
            raise UserNotFoundError()
        
        user.password_hash = hash_password(new_password)
        user.last_password_change_at = datetime.now(timezone.utc)
        user.failed_login_attempts = 0
        user.locked_until = None
        
        reset_token.used_at = datetime.now(timezone.utc)
        self.db.commit()
        
        self.audit.log_event(
            self.db,
            AuditEventType.PASSWORD_CHANGED,
            f"Password reset completed: {user.email}",
            actor_user_id=user.id,
            tenant_id=user.tenant_id,
        )
    
    def verify_email(self, token_string: str) -> User:
        """Verify user email."""
        token_hash = hash_token(token_string)
        
        verification_token = self.db.query(EmailVerificationToken).filter(
            EmailVerificationToken.token_hash == token_hash,
            EmailVerificationToken.verified_at.is_(None),
            EmailVerificationToken.expires_at > datetime.now(timezone.utc),
        ).first()
        
        if not verification_token:
            raise InvalidTokenError("Invalid or expired verification token")
        
        user = self.db.query(User).filter(User.id == verification_token.user_id).first()
        if not user:
            raise UserNotFoundError()
        
        user.email_verified = True
        user.status = UserStatus.ACTIVE
        verification_token.verified_at = datetime.now(timezone.utc)
        self.db.commit()
        
        self.audit.log_event(
            self.db,
            AuditEventType.EMAIL_VERIFIED,
            f"Email verified: {user.email}",
            actor_user_id=user.id,
            tenant_id=user.tenant_id,
        )
        
        return user
    
    def resend_verification(self, email: str) -> None:
        """Resend verification email."""
        user = self.db.query(User).filter(User.email == email.lower()).first()
        if not user:
            return  # Don't reveal if user exists
        
        if user.email_verified:
            return  # Already verified
        
        # Create new verification token
        token_string = generate_token_string()
        token_hash = hash_token(token_string)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES)
        
        verification_token = EmailVerificationToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self.db.add(verification_token)
        self.db.commit()
        
        # Send email (truly non-blocking - deferred to background task)
        try:
            subject, html_content, text_content = create_verification_email_template(user.email, token_string)
            # Log that email should be sent, but don't actually send it here to avoid blocking
            logger.info(f"Verification email prepared for {user.email} (sending deferred to background task)")
        except Exception as e:
            logger.warning(f"Failed to prepare verification email for {user.email}: {str(e)}")
            # Don't fail the request if email preparation fails


class UserService:
    """Service for user management operations."""
    
    def __init__(self, db: Session):
        self.db = db
        self.audit = AuditService()
    
    def create_user(self, request: CreateUserRequest, tenant_id: UUID, created_by: Optional[UUID]) -> User:
        """Create a new user (admin operation)."""
        # Check if user already exists
        existing_user = self.db.query(User).filter(User.email == request.email.lower()).first()
        if existing_user:
            raise UserAlreadyExistsError()
        
        # Validate password
        is_valid, error_msg = validate_password_strength(request.password)
        if not is_valid:
            raise PasswordValidationError(error_msg)
        
        # Create user
        full_name = f"{request.first_name} {request.last_name}".strip()
        user = User(
            email=request.email.lower(),
            password_hash=hash_password(request.password),
            first_name=request.first_name,
            last_name=request.last_name,
            full_name=full_name,
            phone=request.phone,
            username=request.username,
            tenant_id=tenant_id,
            status=UserStatus.ACTIVE,  # Admin-created users are active immediately
            email_verified=True,  # Admin-created users don't need email verification
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        
        # Assign role
        role = self.db.query(Role).filter(Role.name == request.role_name).first()
        if role:
            user_role = UserRole(
                user_id=user.id,
                role_id=role.id,
                tenant_id=tenant_id,
                granted_by=created_by,  # Can be None for first admin
            )
            self.db.add(user_role)
            self.db.commit()
        
        self.audit.log_event(
            self.db,
            AuditEventType.USER_CREATED,
            f"User created by admin: {user.email}",
            actor_user_id=created_by,  # Can be None for first admin
            tenant_id=tenant_id,
            target_user_id=user.id,
            target_type="user",
        )
        
        return user
    
    async def update_user(
        self,
        user_id: UUID,
        request: Optional[UserUpdate] = None,
        updated_by: Optional[UUID] = None,
        profile_picture_file: Optional[UploadFile] = None,
        remove_profile_picture: bool = False,
        **kwargs
    ) -> User:
        # Track email change for token generation
        self._email_changed = False
        self._new_access_token = None
        """
        Update user profile with all fields and optional profile picture.
        
        Args:
            user_id: User ID to update
            request: UserUpdate schema with profile fields (optional, can use kwargs instead)
            updated_by: User ID performing the update
            profile_picture_file: Optional UploadFile for profile picture
            remove_profile_picture: If True, remove existing profile picture
            **kwargs: Additional fields (first_name, last_name, email, phone, username)
        """
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise UserNotFoundError()
        
        # Extract fields from request or kwargs
        # For optional fields like phone and username, check if they're in kwargs explicitly
        # because empty string is falsy and would be lost with 'or' operator
        first_name = kwargs.get('first_name') if 'first_name' in kwargs else (request.first_name if request else None)
        last_name = kwargs.get('last_name') if 'last_name' in kwargs else (request.last_name if request else None)
        email = kwargs.get('email') if 'email' in kwargs else (request.email if request else None)
        phone = kwargs.get('phone') if 'phone' in kwargs else (request.phone if request else None)
        username = kwargs.get('username') if 'username' in kwargs else (request.username if request else None)
        
        # Validate and update first_name
        if first_name is not None:
            first_name = first_name.strip()
            if len(first_name) < 1 or len(first_name) > 100:
                raise ValueError("First name must be between 1 and 100 characters")
            user.first_name = first_name
        
        # Validate and update last_name
        if last_name is not None:
            last_name = last_name.strip()
            if len(last_name) < 1 or len(last_name) > 100:
                raise ValueError("Last name must be between 1 and 100 characters")
            user.last_name = last_name
        
        # Validate and update email
        if email is not None:
            email = email.strip().lower()
            try:
                validate_email(email, check_deliverability=False)
            except EmailNotValidError as e:
                raise ValueError(f"Invalid email format: {str(e)}")
            
            # Check email uniqueness if changed
            if email != user.email:
                existing_user = self.db.query(User).filter(
                    User.email == email,
                    User.id != user_id
                ).first()
                if existing_user:
                    raise UserAlreadyExistsError("Email already in use")
                
                # Store old email for verification email
                old_email = user.email
                self._email_changed = True
                
                # Update email and mark as unverified
                user.email = email
                user.email_verified = False  # Require re-verification
                
                # Send verification email to new address
                try:
                    # Create verification token
                    token_string = generate_token_string()
                    token_hash = hash_token(token_string)
                    expires_at = datetime.now(timezone.utc) + timedelta(
                        minutes=settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES
                    )
                    
                    # Delete old verification tokens for this user
                    self.db.query(EmailVerificationToken).filter(
                        EmailVerificationToken.user_id == user.id
                    ).delete()
                    
                    # Create new verification token
                    verification_token = EmailVerificationToken(
                        user_id=user.id,
                        token_hash=token_hash,
                        expires_at=expires_at,
                    )
                    self.db.add(verification_token)
                    # Note: commit will happen later with other changes
                    
                    # Send verification email (non-blocking - don't fail update if email fails)
                    try:
                        subject, html_content, text_content = create_verification_email_template(
                            user.email, token_string
                        )
                        # Send email asynchronously (don't block the response)
                        # Use create_task to run in background
                        import asyncio
                        try:
                            loop = asyncio.get_event_loop()
                            if loop.is_running():
                                # Schedule as background task
                                asyncio.create_task(send_email(user.email, subject, html_content, text_content))
                            else:
                                # Run directly if no loop is running
                                await send_email(user.email, subject, html_content, text_content)
                        except RuntimeError:
                            # Create new event loop if needed
                            asyncio.run(send_email(user.email, subject, html_content, text_content))
                        logger.info(f"Verification email queued for new email: {user.email}")
                    except Exception as email_send_error:
                        logger.warning(f"Failed to queue verification email: {email_send_error}")
                        # Don't fail the update if email sending fails
                except Exception as email_error:
                    logger.warning(f"Failed to prepare verification email: {email_error}")
                    # Don't fail the update if email preparation fails
        
        # Validate and update phone
        if phone is not None:
            phone = phone.strip() if phone else None
            if phone:
                if len(phone) > 20:
                    raise ValueError("Phone number must be 20 characters or less")
                user.phone = phone
            else:
                # Remove phone if empty string is sent
                user.phone = None
        
        # Validate and update username
        if username is not None:
            # Handle empty string explicitly - strip and check if it's actually empty
            if isinstance(username, str):
                username = username.strip()
            else:
                username = None
            
            # Check if username is empty after stripping
            is_empty = not username or len(username) == 0
            
            if not is_empty:
                # Username has value - validate it
                if len(username) < 3 or len(username) > 100:
                    raise ValueError("Username must be between 3 and 100 characters")
                if not username.replace('_', '').replace('-', '').isalnum():
                    raise ValueError("Username can only contain letters, numbers, underscores, and hyphens")
                
                # Check username uniqueness if changed
                if username != user.username:
                    existing_user = self.db.query(User).filter(
                        User.username == username,
                        User.id != user_id
                    ).first()
                    if existing_user:
                        raise UserAlreadyExistsError("Username already in use")
                user.username = username
                logger.info(f"Username updated to '{username}' for user {user_id}")
            else:
                # Remove username if empty string is sent
                user.username = None
                logger.info(f"Username removed (set to None) for user {user_id}")
        
        # Update full name automatically
        user.full_name = f"{user.first_name} {user.last_name}".strip()
        
        # Handle profile picture
        old_profile_picture_url = user.profile_picture_url
        logger.info(f"Profile picture handling - remove: {remove_profile_picture}, file provided: {profile_picture_file is not None}, old_url: {old_profile_picture_url}")
        
        if remove_profile_picture:
            # Remove profile picture
            if old_profile_picture_url:
                file_storage_service.delete_profile_picture(old_profile_picture_url)
                user.profile_picture_url = None
                logger.info("Profile picture removed")
        elif profile_picture_file:
            # Upload new profile picture
            try:
                logger.info(f"Starting profile picture upload for user {user_id}, file: {getattr(profile_picture_file, 'filename', 'unknown')}")
                filename = await file_storage_service.save_profile_picture(
                    profile_picture_file,
                    old_file_url=old_profile_picture_url
                )
                logger.info(f"Profile picture saved successfully with filename: {filename}")
                user.profile_picture_url = filename
                logger.info(f"Set user.profile_picture_url to: {filename}, user.profile_picture_url is now: {user.profile_picture_url}")
            except HTTPException as e:
                logger.error(f"HTTPException during profile picture upload: {e.detail}")
                raise
            except Exception as e:
                logger.error(f"Error handling profile picture upload: {e}", exc_info=True)
                raise ValueError(f"Failed to upload profile picture: {str(e)}")
        else:
            logger.info("No profile picture file provided and remove flag is False, skipping profile picture update")
        
        try:
            logger.info(f"Before commit - user.profile_picture_url: {user.profile_picture_url}")
            self.db.commit()
            logger.info(f"After commit - user.profile_picture_url: {user.profile_picture_url}")
            self.db.refresh(user)
            logger.info(f"After refresh - user.profile_picture_url: {user.profile_picture_url}")
            
            # Double-check by querying from database to ensure we have latest data
            # User is already imported at top of file, so use it directly
            db_user = self.db.query(User).filter(User.id == user.id).first()
            if db_user:
                logger.info(f"Database query - db_user.profile_picture_url: {db_user.profile_picture_url}")
                # Ensure we're using the latest data from database
                user.profile_picture_url = db_user.profile_picture_url
                logger.info(f"Updated user.profile_picture_url from database: {user.profile_picture_url}")
        except Exception as e:
            self.db.rollback()
            logger.error(f"Database error updating user: {e}", exc_info=True)
            raise ValueError(f"Failed to update profile: {str(e)}")
        
        # If email was changed, generate new access token
        if hasattr(self, '_email_changed') and self._email_changed:
            from app.core.security import create_access_token
            try:
                self._new_access_token = create_access_token({
                    "user_id": str(user.id),
                    "email": user.email,  # Updated email
                    "tenant_id": str(user.tenant_id),
                })
                logger.info(f"New access token generated for user {user.id} after email change")
            except Exception as token_error:
                logger.warning(f"Failed to generate new access token: {token_error}")
                # Don't fail the update if token generation fails
        
        # Audit log
        try:
            self.audit.log_event(
                self.db,
                AuditEventType.USER_UPDATED,
                f"User profile updated: {user.email}" + (" (email changed)" if hasattr(self, '_email_changed') and self._email_changed else ""),
                actor_user_id=updated_by,
                tenant_id=user.tenant_id,
                target_user_id=user.id,
                target_type="user",
            )
        except Exception as e:
            logger.warning(f"Failed to log audit event: {e}")
            # Don't fail the update if audit logging fails
        
        return user
    
    def change_password(self, user_id: UUID, current_password: str, new_password: str) -> None:
        """Change user password."""
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise UserNotFoundError()
        
        # Verify current password
        if not verify_password(current_password, user.password_hash):
            raise InvalidCredentialsError("Current password is incorrect")
        
        # Validate new password
        is_valid, error_msg = validate_password_strength(new_password)
        if not is_valid:
            raise PasswordValidationError(error_msg)
        
        # Update password
        user.password_hash = hash_password(new_password)
        user.last_password_change_at = datetime.now(timezone.utc)
        self.db.commit()
        
        self.audit.log_event(
            self.db,
            AuditEventType.PASSWORD_CHANGED,
            f"Password changed: {user.email}",
            actor_user_id=user_id,
            tenant_id=user.tenant_id,
        )
    
    def get_user_by_id(self, user_id: UUID) -> Optional[User]:
        """Get user by ID."""
        return self.db.query(User).filter(User.id == user_id).first()
    
    def list_users(
        self,
        tenant_id: UUID,
        skip: int = 0,
        limit: int = 100,
        status: Optional[UserStatus] = None,
    ) -> tuple[List[User], int]:
        """List users in tenant."""
        query = self.db.query(User).filter(User.tenant_id == tenant_id)
        
        if status:
            query = query.filter(User.status == status)
        
        total = query.count()
        users = query.offset(skip).limit(limit).all()
        
        return users, total


class TenantService:
    """Service for tenant management operations."""
    
    def __init__(self, db: Session):
        self.db = db
        self.audit = AuditService()
    
    def create_platform_tenant(self) -> Tenant:
        """Create the root platform tenant."""
        # Check if platform tenant already exists
        existing = self.db.query(Tenant).filter(Tenant.type == TenantType.PLATFORM).first()
        if existing:
            return existing
        
        tenant = Tenant(
            name="Platform",
            slug="platform",
            type=TenantType.PLATFORM,
            parent_tenant_id=None,
            hierarchy_path="/",
            is_active=True,
        )
        self.db.add(tenant)
        self.db.commit()
        self.db.refresh(tenant)
        
        return tenant
    
    def create_organization(
        self,
        request: CreateOrganizationRequest,
        created_by: UUID,
    ) -> tuple[Tenant, User]:
        """Create organization and organization admin user."""
        # Get platform tenant
        platform = self.db.query(Tenant).filter(Tenant.type == TenantType.PLATFORM).first()
        if not platform:
            platform = self.create_platform_tenant()
        
        # Create organization
        hierarchy_path = f"/org-{request.slug}/"
        org = Tenant(
            name=request.name,
            slug=request.slug,
            type=TenantType.ORGANIZATION,
            parent_tenant_id=platform.id,
            hierarchy_path=hierarchy_path,
            settings=request.settings,
            is_active=True,
        )
        self.db.add(org)
        self.db.commit()
        self.db.refresh(org)
        
        # Create org admin user
        user_service = UserService(self.db)
        admin_user = user_service.create_user(
            CreateUserRequest(
                email=request.admin_email,
                password=request.admin_password,
                first_name=request.admin_first_name,
                last_name=request.admin_last_name,
                role_name=RoleName.ORG_ADMIN,
            ),
            tenant_id=org.id,
            created_by=created_by,
        )
        
        return org, admin_user
    
    def create_school(
        self,
        request: CreateSchoolRequest,
        created_by: UUID,
    ) -> tuple[Tenant, User]:
        """Create school and school admin user."""
        # Get organization
        org = self.db.query(Tenant).filter(Tenant.id == request.organization_id).first()
        if not org:
            raise ValueError(f"Organization {request.organization_id} not found")
        
        # Create school
        hierarchy_path = f"{org.hierarchy_path}school-{request.slug}/"
        school = Tenant(
            name=request.name,
            slug=request.slug,
            type=TenantType.SCHOOL,
            parent_tenant_id=org.id,
            hierarchy_path=hierarchy_path,
            settings=request.settings,
            is_active=True,
        )
        self.db.add(school)
        self.db.commit()
        self.db.refresh(school)
        
        # Create school admin user
        user_service = UserService(self.db)
        admin_user = user_service.create_user(
            CreateUserRequest(
                email=request.admin_email,
                password=request.admin_password,
                first_name=request.admin_first_name,
                last_name=request.admin_last_name,
                role_name=RoleName.SCHOOL_ADMIN,
            ),
            tenant_id=school.id,
            created_by=created_by,
        )
        
        return school, admin_user


class RBACService:
    """Service for role-based access control operations."""
    
    def __init__(self, db: Session):
        self.db = db
        self.audit = AuditService()
    
    def assign_role(
        self,
        user_id: UUID,
        role_id: UUID,
        tenant_id: UUID,
        granted_by: UUID,
        scope: Optional[Dict[str, Any]] = None,
    ) -> UserRole:
        """Assign role to user."""
        # Check if assignment already exists
        existing = self.db.query(UserRole).filter(
            UserRole.user_id == user_id,
            UserRole.role_id == role_id,
            UserRole.tenant_id == tenant_id,
        ).first()
        
        if existing:
            return existing
        
        user_role = UserRole(
            user_id=user_id,
            role_id=role_id,
            tenant_id=tenant_id,
            granted_by=granted_by,
            scope=scope,
        )
        self.db.add(user_role)
        self.db.commit()
        self.db.refresh(user_role)
        
        self.audit.log_event(
            self.db,
            AuditEventType.ROLE_ASSIGNED,
            f"Role assigned to user",
            actor_user_id=granted_by,
            tenant_id=tenant_id,
            target_user_id=user_id,
            target_type="user",
            event_metadata={"role_id": str(role_id)},
        )
        
        return user_role
    
    def revoke_role(self, user_role_id: UUID, revoked_by: UUID) -> None:
        """Revoke role from user."""
        user_role = self.db.query(UserRole).filter(UserRole.id == user_role_id).first()
        if not user_role:
            raise ValueError("User role not found")
        
        self.db.delete(user_role)
        self.db.commit()
        
        self.audit.log_event(
            self.db,
            AuditEventType.ROLE_REVOKED,
            f"Role revoked from user",
            actor_user_id=revoked_by,
            tenant_id=user_role.tenant_id,
            target_user_id=user_role.user_id,
            target_type="user",
            event_metadata={"role_id": str(user_role.role_id)},
        )
    
    def check_permission(self, user_id: UUID, permission_name: str, tenant_id: UUID) -> bool:
        """Check if user has a specific permission."""
        # Get user roles in tenant
        user_roles = self.db.query(UserRole).filter(
            UserRole.user_id == user_id,
            UserRole.tenant_id == tenant_id,
        ).all()
        
        if not user_roles:
            return False
        
        role_ids = [ur.role_id for ur in user_roles]
        
        # Check if any role has the permission
        permission = self.db.query(Permission).filter(Permission.name == permission_name).first()
        if not permission:
            return False
        
        has_permission = self.db.query(RolePermission).filter(
            RolePermission.role_id.in_(role_ids),
            RolePermission.permission_id == permission.id,
        ).first()
        
        return has_permission is not None
    
    def get_user_permissions(self, user_id: UUID, tenant_id: UUID) -> List[Permission]:
        """Get all permissions for a user in a tenant."""
        user_roles = self.db.query(UserRole).filter(
            UserRole.user_id == user_id,
            UserRole.tenant_id == tenant_id,
        ).all()
        
        if not user_roles:
            return []
        
        role_ids = [ur.role_id for ur in user_roles]
        
        permissions = self.db.query(Permission).join(RolePermission).filter(
            RolePermission.role_id.in_(role_ids)
        ).distinct().all()
        
        return permissions


class SelfRegistrationService:
    """Service for self-registration flows."""
    
    def __init__(self, db: Session):
        self.db = db
        self.audit = AuditService()
        self.auth_service = AuthService(db)
    
    def teacher_signup(self, request: TeacherSignupRequest) -> User:
        """Teacher self-signup (pending approval)."""
        # Determine tenant: use school if school_code provided, otherwise use platform tenant for individual account
        if request.school_code:
            # Find school by code (assuming code is stored in tenant settings or slug)
            # For now, we'll use slug as code - this can be customized
            school = self.db.query(Tenant).filter(
                Tenant.type == TenantType.SCHOOL,
                Tenant.slug == request.school_code,
                Tenant.is_active == True,
            ).first()
            
            if not school:
                raise ValueError(f"School with code {request.school_code} not found")
            tenant_id = school.id
            status = UserStatus.PENDING_APPROVAL  # Requires school admin approval
        else:
            # Individual account - use platform tenant
            platform = self.db.query(Tenant).filter(
                Tenant.type == TenantType.PLATFORM,
                Tenant.is_active == True
            ).first()
            if not platform:
                raise ValueError("Platform tenant not found. Please run: python -m app.seed.cli --auth")
            tenant_id = platform.id
            status = UserStatus.ACTIVE  # Individual accounts are active immediately
        
        # Check if user already exists
        existing_user = self.db.query(User).filter(User.email == request.email.lower()).first()
        if existing_user:
            raise UserAlreadyExistsError()
        
        # Validate password
        is_valid, error_msg = validate_password_strength(request.password)
        if not is_valid:
            raise PasswordValidationError(error_msg)
        
        # Create user
        full_name = f"{request.first_name} {request.last_name}".strip()
        user = User(
            email=request.email.lower(),
            password_hash=hash_password(request.password),
            first_name=request.first_name,
            last_name=request.last_name,
            full_name=full_name,
            phone=request.phone,
            tenant_id=tenant_id,
            status=status,
            email_verified=status == UserStatus.ACTIVE,  # Individual accounts are auto-verified
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        
        # Assign teacher role
        teacher_role = self.db.query(Role).filter(Role.name == RoleName.TEACHER).first()
        if teacher_role:
            user_role = UserRole(
                user_id=user.id,
                role_id=teacher_role.id,
                tenant_id=tenant_id,
                granted_by=None,  # Self-signup
            )
            self.db.add(user_role)
            self.db.commit()
        
        account_type = "individual account" if not request.school_code else "school account (pending approval)"
        self.audit.log_event(
            self.db,
            AuditEventType.USER_CREATED,
            f"Teacher self-signup ({account_type}): {user.email}",
            actor_user_id=user.id,
            tenant_id=tenant_id,
            target_user_id=user.id,
            target_type="user",
        )
        
        logger.info(f"Teacher signup request: {user.email}")
        return user
    
    def student_signup(self, request: StudentSignupRequest) -> User:
        """Student self-signup (pending verification)."""
        # Determine tenant: use school if school_code provided, otherwise use platform tenant for individual account
        if request.school_code:
            # Find school by code
            school = self.db.query(Tenant).filter(
                Tenant.type == TenantType.SCHOOL,
                Tenant.slug == request.school_code,
                Tenant.is_active == True,
            ).first()
            
            if not school:
                raise ValueError(f"School with code {request.school_code} not found")
            tenant_id = school.id
            status = UserStatus.PENDING_VERIFICATION  # Requires email verification
        else:
            # Individual account - use platform tenant
            platform = self.db.query(Tenant).filter(
                Tenant.type == TenantType.PLATFORM,
                Tenant.is_active == True
            ).first()
            if not platform:
                raise ValueError("Platform tenant not found. Please run: python -m app.seed.cli --auth")
            tenant_id = platform.id
            status = UserStatus.ACTIVE  # Individual accounts are active immediately
        
        # Check if user already exists
        existing_user = self.db.query(User).filter(User.email == request.email.lower()).first()
        if existing_user:
            raise UserAlreadyExistsError()
        
        # Validate password
        is_valid, error_msg = validate_password_strength(request.password)
        if not is_valid:
            raise PasswordValidationError(error_msg)
        
        # Create user
        full_name = f"{request.first_name} {request.last_name}".strip()
        user = User(
            email=request.email.lower(),
            password_hash=hash_password(request.password),
            first_name=request.first_name,
            last_name=request.last_name,
            full_name=full_name,
            phone=request.phone,
            tenant_id=tenant_id,
            status=status,
            email_verified=status == UserStatus.ACTIVE,  # Individual accounts are auto-verified
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        
        # Assign student role
        student_role = self.db.query(Role).filter(Role.name == RoleName.STUDENT).first()
        if student_role:
            user_role = UserRole(
                user_id=user.id,
                role_id=student_role.id,
                tenant_id=tenant_id,
            )
            self.db.add(user_role)
            self.db.commit()
        
        # Link parent if provided (only for school accounts)
        if request.parent_email and request.school_code:
            parent = self.db.query(User).filter(User.email == request.parent_email.lower()).first()
            if parent:
                link = ParentStudentLink(
                    parent_id=parent.id,
                    student_id=user.id,
                    is_verified=False,
                )
                self.db.add(link)
                self.db.commit()
        
        account_type = "individual account" if not request.school_code else "school account (pending verification)"
        self.audit.log_event(
            self.db,
            AuditEventType.USER_CREATED,
            f"Student self-signup ({account_type}): {user.email}",
            actor_user_id=user.id,
            tenant_id=tenant_id,
            target_user_id=user.id,
            target_type="user",
        )
        
        return user
    
    def parent_signup(self, request: ParentSignupRequest) -> User:
        """Parent self-signup."""
        # Find student by code (assuming student code is email or student ID)
        student = self.db.query(User).join(UserRole).join(Role).filter(
            Role.name == RoleName.STUDENT,
            or_(
                User.email == request.student_code.lower(),
                User.username == request.student_code,
            )
        ).first()
        
        if not student:
            raise ValueError(f"Student with code {request.student_code} not found")
        
        # Check if parent already exists
        existing_user = self.db.query(User).filter(User.email == request.email.lower()).first()
        if existing_user:
            raise UserAlreadyExistsError()
        
        # Validate password
        is_valid, error_msg = validate_password_strength(request.password)
        if not is_valid:
            raise PasswordValidationError(error_msg)
        
        # Create parent user
        full_name = f"{request.first_name} {request.last_name}".strip()
        user = User(
            email=request.email.lower(),
            password_hash=hash_password(request.password),
            first_name=request.first_name,
            last_name=request.last_name,
            full_name=full_name,
            phone=request.phone,
            tenant_id=student.tenant_id,
            status=UserStatus.PENDING_VERIFICATION,
            email_verified=False,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        
        # Assign parent role
        parent_role = self.db.query(Role).filter(Role.name == RoleName.PARENT).first()
        if parent_role:
            user_role = UserRole(
                user_id=user.id,
                role_id=parent_role.id,
                tenant_id=student.tenant_id,
            )
            self.db.add(user_role)
            self.db.commit()
        
        # Create parent-student link
        link = ParentStudentLink(
            parent_id=user.id,
            student_id=student.id,
            is_verified=False,
        )
        self.db.add(link)
        self.db.commit()
        
        self.audit.log_event(
            self.db,
            AuditEventType.USER_CREATED,
            f"Parent self-signup: {user.email}",
            actor_user_id=user.id,
            tenant_id=student.tenant_id,
            target_user_id=user.id,
            target_type="user",
        )
        
        return user
    
    def approve_signup(self, user_id: UUID, approved_by: UUID) -> User:
        """Approve pending signup request."""
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise UserNotFoundError()
        
        if user.status != UserStatus.PENDING_APPROVAL:
            raise ValueError("User is not pending approval")
        
        user.status = UserStatus.ACTIVE
        user.email_verified = True  # Auto-verify on approval
        self.db.commit()
        self.db.refresh(user)
        
        # Get tenant name
        tenant = self.db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
        tenant_name = tenant.name if tenant else "Organization"
        
        # Send welcome email/invitation (truly non-blocking - deferred to background task)
        try:
            subject, html_content, text_content = create_invitation_email_template(
                user.email,
                "Administrator",
                tenant_name,
            )
            # Log that email should be sent, but don't actually send it here to avoid blocking
            logger.info(f"Invitation email prepared for {user.email} (sending deferred to background task)")
        except Exception as e:
            logger.warning(f"Failed to prepare invitation email for {user.email}: {str(e)}")
            # Don't fail the request if email preparation fails
        
        self.audit.log_event(
            self.db,
            AuditEventType.USER_UPDATED,
            f"Signup approved: {user.email}",
            actor_user_id=approved_by,
            tenant_id=user.tenant_id,
            target_user_id=user.id,
            target_type="user",
        )
        
        return user
    
    def reject_signup(self, user_id: UUID, rejected_by: UUID, reason: Optional[str] = None) -> None:
        """Reject pending signup request (delete user)."""
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise UserNotFoundError()
        
        tenant_id = user.tenant_id
        email = user.email
        
        self.db.delete(user)
        self.db.commit()
        
        self.audit.log_event(
            self.db,
            AuditEventType.USER_DELETED,
            f"Signup rejected: {email}",
            actor_user_id=rejected_by,
            tenant_id=tenant_id,
            event_metadata={"reason": reason} if reason else None,
        )


class SuperAdminService:
    """Service for super admin management operations."""
    
    def __init__(self, db: Session):
        self.db = db
        self.audit = AuditService()
        self.user_service = UserService(db)
        self.rbac_service = RBACService(db)
    
    def create_super_admin(
        self,
        email: str,
        password: str,
        first_name: str,
        last_name: str,
        created_by: Optional[UUID],
        phone: Optional[str] = None,
    ) -> User:
        """
        Create a new super admin user.
        
        Args:
            email: Admin email
            password: Admin password (will be validated and hashed)
            first_name: First name
            last_name: Last name
            phone: Optional phone number
            created_by: ID of user creating this admin (None for first admin)
            
        Returns:
            Created User with super_admin role
            
        Raises:
            UserAlreadyExistsError: If user already exists
            PasswordValidationError: If password doesn't meet requirements
        """
        # Get platform tenant
        platform = self.db.query(Tenant).filter(Tenant.type == TenantType.PLATFORM).first()
        if not platform:
            raise ValueError("Platform tenant not found")
        
        # Get super_admin role
        super_admin_role = self.db.query(Role).filter(Role.name == RoleName.SUPER_ADMIN).first()
        if not super_admin_role:
            raise ValueError("Super admin role not found")
        
        # Check if user already exists
        existing_user = self.db.query(User).filter(User.email == email.lower()).first()
        
        if existing_user:
            # Check if user already has super_admin role
            existing_role = (
                self.db.query(UserRole)
                .filter(
                    UserRole.user_id == existing_user.id,
                    UserRole.role_id == super_admin_role.id,
                )
                .first()
            )
            
            if existing_role:
                # User already has super_admin role
                return existing_user
            else:
                # User exists but doesn't have super_admin role - assign it
                user_role = UserRole(
                    user_id=existing_user.id,
                    role_id=super_admin_role.id,
                    tenant_id=platform.id,
                    granted_by=created_by,
                )
                self.db.add(user_role)
                self.db.commit()
                
                # Update user info if provided
                if first_name:
                    existing_user.first_name = first_name
                if last_name:
                    existing_user.last_name = last_name
                    existing_user.full_name = f"{first_name} {last_name}".strip()
                if phone:
                    existing_user.phone = phone
                if password:
                    # Update password if provided
                    is_valid, error_msg = validate_password_strength(password)
                    if not is_valid:
                        raise PasswordValidationError(error_msg)
                    existing_user.password_hash = hash_password(password)
                
                self.db.commit()
                self.db.refresh(existing_user)
                
                # Audit log
                self.audit.log_event(
                    self.db,
                    AuditEventType.ROLE_ASSIGNED,
                    f"Super admin role assigned to existing user: {existing_user.email}",
                    actor_user_id=created_by,
                    tenant_id=platform.id,
                    target_user_id=existing_user.id,
                    target_type="super_admin",
                    event_metadata={
                        "is_super_admin": True,
                        "role": "super_admin",
                    },
                )
                
                return existing_user
        
        # Create new user using application service
        user = self.user_service.create_user(
            CreateUserRequest(
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                role_name=RoleName.SUPER_ADMIN,
            ),
            tenant_id=platform.id,
            created_by=created_by,
        )
        
        # Audit log with super admin flag
        self.audit.log_event(
            self.db,
            AuditEventType.USER_CREATED,
            f"Super admin created: {user.email}",
            actor_user_id=created_by,
            tenant_id=platform.id,
            target_user_id=user.id,
            target_type="super_admin",
            event_metadata={
                "is_super_admin": True,
                "role": "super_admin",
            },
        )
        
        return user
    
    def list_super_admins(
        self,
        skip: int = 0,
        limit: int = 100,
        include_inactive: bool = False,
    ) -> tuple[List[User], int]:
        """
        List all super admin users.
        
        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return
            include_inactive: Include inactive super admins
            
        Returns:
            Tuple of (users list, total count)
        """
        super_admin_role = self.db.query(Role).filter(Role.name == RoleName.SUPER_ADMIN).first()
        if not super_admin_role:
            return [], 0
        
        query = (
            self.db.query(User)
            .join(UserRole, UserRole.user_id == User.id)
            .filter(UserRole.role_id == super_admin_role.id)
        )
        
        if not include_inactive:
            query = query.filter(User.status == UserStatus.ACTIVE)
        
        total = query.count()
        users = query.offset(skip).limit(limit).all()
        
        return users, total
    
    def get_super_admin(self, user_id: UUID) -> Optional[User]:
        """Get super admin by user ID."""
        super_admin_role = self.db.query(Role).filter(Role.name == RoleName.SUPER_ADMIN).first()
        if not super_admin_role:
            return None
        
        user = (
            self.db.query(User)
            .join(UserRole, UserRole.user_id == User.id)
            .filter(
                User.id == user_id,
                UserRole.role_id == super_admin_role.id,
            )
            .first()
        )
        
        return user
    
    async def update_super_admin(
        self,
        user_id: UUID,
        request: UserUpdate,
        updated_by: UUID,
    ) -> User:
        """
        Update super admin information.
        
        Args:
            user_id: Super admin user ID
            request: Update request
            updated_by: ID of user performing update
            
        Returns:
            Updated User
            
        Raises:
            UserNotFoundError: If super admin not found
        """
        user = self.get_super_admin(user_id)
        if not user:
            raise UserNotFoundError("Super admin not found")
        
        # Use application service for update
        updated_user = await self.user_service.update_user(user_id, request, updated_by)
        
        # Audit log
        self.audit.log_event(
            self.db,
            AuditEventType.USER_UPDATED,
            f"Super admin updated: {updated_user.email}",
            actor_user_id=updated_by,
            tenant_id=updated_user.tenant_id,
            target_user_id=updated_user.id,
            target_type="super_admin",
            event_metadata={
                "is_super_admin": True,
                "updated_fields": request.model_dump(exclude_unset=True),
            },
        )
        
        return updated_user
    
    def change_super_admin_password(
        self,
        user_id: UUID,
        new_password: str,
        changed_by: UUID,
    ) -> None:
        """
        Change super admin password (admin operation).
        
        Args:
            user_id: Super admin user ID
            new_password: New password (will be validated)
            changed_by: ID of admin changing password
            
        Raises:
            UserNotFoundError: If super admin not found
            PasswordValidationError: If password doesn't meet requirements
        """
        user = self.get_super_admin(user_id)
        if not user:
            raise UserNotFoundError("Super admin not found")
        
        # Validate password
        is_valid, error_msg = validate_password_strength(new_password)
        if not is_valid:
            raise PasswordValidationError(error_msg)
        
        # Update password
        user.password_hash = hash_password(new_password)
        user.last_password_change_at = datetime.now(timezone.utc)
        user.must_change_password = True  # Force password change on next login
        self.db.commit()
        
        # Audit log
        self.audit.log_event(
            self.db,
            AuditEventType.PASSWORD_CHANGED,
            f"Super admin password changed: {user.email}",
            actor_user_id=changed_by,
            tenant_id=user.tenant_id,
            target_user_id=user.id,
            target_type="super_admin",
            event_metadata={
                "is_super_admin": True,
                "changed_by_admin": True,
            },
        )
    
    def deactivate_super_admin(
        self,
        user_id: UUID,
        deactivated_by: UUID,
        reason: Optional[str] = None,
    ) -> None:
        """
        Deactivate super admin (soft delete).
        
        Args:
            user_id: Super admin user ID
            deactivated_by: ID of admin performing deactivation
            reason: Optional reason for deactivation
            
        Raises:
            UserNotFoundError: If super admin not found
            ValueError: If trying to deactivate last active super admin
        """
        user = self.get_super_admin(user_id)
        if not user:
            raise UserNotFoundError("Super admin not found")
        
        # Prevent deactivating self
        if user_id == deactivated_by:
            raise ValueError("Cannot deactivate yourself")
        
        # Check if this is the last active super admin
        active_admins, count = self.list_super_admins(include_inactive=False)
        if count <= 1:
            raise ValueError(
                "Cannot deactivate the last active super admin. "
                "Create another super admin first."
            )
        
        # Deactivate user
        user.status = UserStatus.INACTIVE
        self.db.commit()
        
        # Audit log
        self.audit.log_event(
            self.db,
            AuditEventType.USER_DELETED,
            f"Super admin deactivated: {user.email}",
            actor_user_id=deactivated_by,
            tenant_id=user.tenant_id,
            target_user_id=user.id,
            target_type="super_admin",
            event_metadata={
                "is_super_admin": True,
                "reason": reason,
                "action": "deactivated",
            },
        )
    
    def reactivate_super_admin(
        self,
        user_id: UUID,
        reactivated_by: UUID,
    ) -> User:
        """
        Reactivate a deactivated super admin.
        
        Args:
            user_id: Super admin user ID
            reactivated_by: ID of admin performing reactivation
            
        Returns:
            Reactivated User
        """
        user = self.get_super_admin(user_id)
        if not user:
            raise UserNotFoundError("Super admin not found")
        
        user.status = UserStatus.ACTIVE
        self.db.commit()
        self.db.refresh(user)
        
        # Audit log
        self.audit.log_event(
            self.db,
            AuditEventType.USER_UPDATED,
            f"Super admin reactivated: {user.email}",
            actor_user_id=reactivated_by,
            tenant_id=user.tenant_id,
            target_user_id=user.id,
            target_type="super_admin",
            event_metadata={
                "is_super_admin": True,
                "action": "reactivated",
            },
        )
        
        return user
    
    def revoke_super_admin_role(
        self,
        user_id: UUID,
        revoked_by: UUID,
    ) -> None:
        """
        Revoke super admin role from user (hard removal).
        
        Args:
            user_id: User ID
            revoked_by: ID of admin performing revocation
            
        Raises:
            UserNotFoundError: If super admin not found
            ValueError: If trying to revoke from last active super admin
        """
        user = self.get_super_admin(user_id)
        if not user:
            raise UserNotFoundError("Super admin not found")
        
        # Prevent revoking from self
        if user_id == revoked_by:
            raise ValueError("Cannot revoke super admin role from yourself")
        
        # Check if this is the last active super admin
        active_admins, count = self.list_super_admins(include_inactive=False)
        if count <= 1:
            raise ValueError(
                "Cannot revoke super admin role from the last active super admin. "
                "Create another super admin first."
            )
        
        # Get super_admin role
        super_admin_role = self.db.query(Role).filter(Role.name == RoleName.SUPER_ADMIN).first()
        
        # Revoke role
        user_role = (
            self.db.query(UserRole)
            .filter(
                UserRole.user_id == user_id,
                UserRole.role_id == super_admin_role.id,
            )
            .first()
        )
        
        if user_role:
            self.rbac_service.revoke_role(user_role.id, revoked_by)
        
        # Audit log
        self.audit.log_event(
            self.db,
            AuditEventType.ROLE_REVOKED,
            f"Super admin role revoked from: {user.email}",
            actor_user_id=revoked_by,
            tenant_id=user.tenant_id,
            target_user_id=user.id,
            target_type="super_admin",
            event_metadata={
                "role": "super_admin",
                "action": "revoked",
            },
        )

