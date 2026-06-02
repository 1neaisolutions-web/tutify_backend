"""
Pydantic schemas for authentication and authorization.
"""
from typing import Optional, List, Dict, Any, Literal  # noqa: F401 - Dict, Any used in UserProfile
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field, ConfigDict

from app.domains.auth.models import (
    UserStatus,
    RoleName,
    RoleScope,
    TenantType,
)


# Base schemas
class Token(BaseModel):
    """JWT token response."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Token payload data."""
    user_id: UUID
    email: str
    tenant_id: UUID


# Authentication schemas
class RegisterRequest(BaseModel):
    """User registration request."""
    email: EmailStr
    password: str = Field(..., min_length=10)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    phone: Optional[str] = None


class LoginRequest(BaseModel):
    """User login request (step 1 or step 2)."""
    email: Optional[EmailStr] = None  # Required for step 1
    password: Optional[str] = None  # Required for step 1
    login_token: Optional[str] = None  # Required for step 2
    selected_membership_id: Optional[UUID] = None  # Required for step 2 (tenant selection)
    scope_type: Optional[str] = None  # Required for step 2 (tenant selection)


class LoginChallengeResponse(BaseModel):
    """Login challenge response (when additional steps required)."""
    status: str = "CHALLENGE"
    challenge_type: str  # TENANT_SELECTION_REQUIRED, MFA_REQUIRED, EMAIL_VERIFICATION_REQUIRED
    login_token: str  # Short-lived token for step 2
    message: Optional[str] = None
    memberships: Optional[List["MembershipResponse"]] = None  # For TENANT_SELECTION_REQUIRED


class LoginResponse(BaseModel):
    """User login response (success or challenge)."""
    status: str  # SUCCESS or CHALLENGE
    access_token: Optional[str] = None  # Present if status is SUCCESS
    refresh_token: Optional[str] = None  # Present if status is SUCCESS
    token_type: str = "bearer"
    user: Optional["UserResponse"] = None  # Present if status is SUCCESS
    challenge: Optional[LoginChallengeResponse] = None  # Present if status is CHALLENGE


class TokenRefreshRequest(BaseModel):
    """Token refresh request."""
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    """Forgot password request."""
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Reset password request."""
    token: str
    new_password: str = Field(..., min_length=10)


class VerifyEmailRequest(BaseModel):
    """Email verification request."""
    token: str


class ChangePasswordRequest(BaseModel):
    """Change password request (authenticated)."""
    current_password: str
    new_password: str = Field(..., min_length=10)


class AdminChangePasswordRequest(BaseModel):
    """Request to change password (admin operation)."""
    new_password: str = Field(..., min_length=10)
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "new_password": "NewSecurePassword123!@#"
        }
    })


# User schemas
class UserBase(BaseModel):
    """Base user schema."""
    email: EmailStr
    first_name: str
    last_name: str
    phone: Optional[str] = None


class UserCreate(UserBase):
    """User creation schema."""
    password: str = Field(..., min_length=10)
    tenant_id: UUID
    username: Optional[str] = None
    status: Optional[UserStatus] = UserStatus.PENDING_VERIFICATION


class UserUpdate(BaseModel):
    """User update schema."""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    username: Optional[str] = None


class UserPreferencesUpdate(BaseModel):
    """Partial update of user preferences (all fields optional)."""
    theme: Optional[Literal["light", "dark", "system"]] = None
    language: Optional[str] = Field(None, max_length=20)  # IETF tag (e.g. 'en-US')
    timezone: Optional[str] = Field(None, max_length=60)  # IANA tz (e.g. 'America/Denver')


class UserPreferencesResponse(BaseModel):
    """Full preferences object (defaults applied server-side)."""
    theme: str = "system"
    language: str = "en-US"
    timezone: str = "UTC"


class UserResponse(UserBase):
    """User response schema."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    username: Optional[str]
    tenant_id: UUID
    status: UserStatus
    email_verified: bool
    profile_picture_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    roles: Optional[List["UserRoleInfo"]] = None
    preferences: Optional[Dict[str, Any]] = None


class UserRoleInfo(BaseModel):
    """User role information for login response."""
    id: UUID
    name: RoleName
    scope: RoleScope
    tenant_id: UUID
    granted_at: datetime


class UserProfile(UserResponse):
    """Extended user profile schema (includes teacher context when present)."""
    last_login_at: Optional[datetime] = None
    teacher_context: Optional[Dict[str, Any]] = None
    context_resolution_status: Optional[str] = None
    # profile_picture_url is already included via UserResponse inheritance
    preferences: UserPreferencesResponse = Field(default_factory=UserPreferencesResponse)


# Tenant schemas
class TenantBase(BaseModel):
    """Base tenant schema."""
    name: str = Field(..., min_length=1, max_length=200)
    slug: str = Field(..., min_length=1, max_length=100)


class TenantCreate(TenantBase):
    """Tenant creation schema."""
    type: TenantType
    parent_tenant_id: Optional[UUID] = None
    settings: Optional[Dict[str, Any]] = None


class TenantResponse(TenantBase):
    """Tenant response schema."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    type: TenantType
    parent_tenant_id: Optional[UUID]
    hierarchy_path: str
    settings: Optional[Dict[str, Any]]
    is_active: bool
    created_at: datetime
    updated_at: datetime


# Organization & School schemas
class CreateOrganizationRequest(BaseModel):
    """Create organization request."""
    name: str = Field(..., min_length=1, max_length=200)
    slug: str = Field(..., min_length=1, max_length=100)
    admin_email: EmailStr
    admin_first_name: str
    admin_last_name: str
    admin_password: str = Field(..., min_length=10)
    settings: Optional[Dict[str, Any]] = None


class CreateSchoolRequest(BaseModel):
    """Create school request."""
    name: str = Field(..., min_length=1, max_length=200)
    slug: str = Field(..., min_length=1, max_length=100)
    organization_id: UUID
    admin_email: EmailStr
    admin_first_name: str
    admin_last_name: str
    admin_password: str = Field(..., min_length=10)
    settings: Optional[Dict[str, Any]] = None


# Admin user creation schemas
class CreateUserRequest(BaseModel):
    """Create user request (admin)."""
    email: EmailStr
    password: str = Field(..., min_length=10)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    phone: Optional[str] = None
    username: Optional[str] = None
    role_name: RoleName
    send_invitation: bool = True


# Self-registration schemas
class TeacherSignupRequest(BaseModel):
    """Teacher self-signup request."""
    email: EmailStr
    password: str = Field(..., min_length=10)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    phone: Optional[str] = None
    school_code: Optional[str] = None  # School identifier code (optional for individual accounts)


class StudentSignupRequest(BaseModel):
    """Student self-signup request."""
    email: EmailStr
    password: str = Field(..., min_length=10)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    phone: Optional[str] = None
    school_code: Optional[str] = None  # School identifier code (optional for individual accounts)
    student_id: Optional[str] = None  # Optional student ID for verification
    parent_email: Optional[EmailStr] = None  # Optional parent email


class ParentSignupRequest(BaseModel):
    """Parent self-signup request."""
    email: EmailStr
    password: str = Field(..., min_length=10)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    phone: Optional[str] = None
    student_code: str  # Student identifier code for linking


# Unified signup schemas
class SignupRequest(BaseModel):
    """Unified signup request - handles all signup types."""
    role: str  # org_admin, institution_admin, teacher, student, parent, invite
    
    # Common fields
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    language: Optional[str] = Field("en-US", max_length=20)
    
    # Role-specific payloads
    organization: Optional[Dict[str, Any]] = None  # For org_admin
    institution: Optional[Dict[str, Any]] = None  # For institution_admin, org_admin
    institution_code: Optional[str] = None  # For teacher, student
    student_code: Optional[str] = None  # For parent
    invite_token: Optional[str] = None  # For invite acceptance
    is_institution_admin: Optional[bool] = False  # For org_admin (if also institution admin)


class SignupResponse(BaseModel):
    """Unified signup response."""
    status: str = "SUCCESS"
    user: UserResponse
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    memberships: Optional[List["MembershipResponse"]] = None  # Forward reference


class SignupApprovalResponse(BaseModel):
    """Signup approval response."""
    id: UUID
    email: EmailStr
    first_name: str
    last_name: str
    status: UserStatus
    created_at: datetime
    tenant_id: UUID
    tenant_name: str


class ApproveSignupRequest(BaseModel):
    """Approve signup request."""
    notes: Optional[str] = None


class RejectSignupRequest(BaseModel):
    """Reject signup request."""
    reason: Optional[str] = None


# Role & Permission schemas
class PermissionResponse(BaseModel):
    """Permission response schema."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    name: str
    description: Optional[str]
    resource: str
    action: str
    created_at: datetime


class RoleResponse(BaseModel):
    """Role response schema."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    name: RoleName
    description: Optional[str]
    scope: RoleScope
    is_system_role: bool
    is_active: bool
    created_at: datetime
    permissions: Optional[List[PermissionResponse]] = None


class AssignRoleRequest(BaseModel):
    """Assign role to user request."""
    role_id: UUID
    scope: Optional[Dict[str, Any]] = None  # Optional scope restrictions


class UserRoleResponse(BaseModel):
    """User role response schema."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    user_id: UUID
    role_id: UUID
    tenant_id: UUID
    scope: Optional[Dict[str, Any]]
    granted_at: datetime
    role: Optional[RoleResponse] = None


# Audit log schemas
class AuditLogResponse(BaseModel):
    """Audit log response schema."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    tenant_id: Optional[UUID]
    actor_user_id: Optional[UUID]
    actor_type: str
    target_user_id: Optional[UUID]
    target_type: Optional[str]
    event_type: str
    description: str
    event_metadata: Optional[Dict[str, Any]]
    ip_address: Optional[str]
    user_agent: Optional[str]
    request_id: Optional[str]
    created_at: datetime


# Membership schemas
class MembershipResponse(BaseModel):
    """Membership response schema."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    scope_type: str
    scope_id: UUID
    scope_name: Optional[str] = None
    scope_display_name: Optional[str] = None
    role: Optional[Dict[str, Any]] = None
    is_active: bool
    granted_at: datetime


class MembershipSwitchRequest(BaseModel):
    """Request to switch active membership."""
    membership_id: UUID
    scope_type: str


class MembershipListResponse(BaseModel):
    """Response containing list of memberships."""
    memberships: List[MembershipResponse]
    active_membership_id: Optional[UUID] = None


class MembershipSwitchResponse(BaseModel):
    """Response after switching membership."""
    success: bool
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    active_membership: MembershipResponse


# Update forward references
LoginResponse.model_rebuild()
UserResponse.model_rebuild()
UserRoleInfo.model_rebuild()
LoginChallengeResponse.model_rebuild()

