"""
Authentication and authorization models.
"""
import uuid
import enum
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Column, String, Text, Boolean, Integer, DateTime, ForeignKey, JSON,
    Enum as SQLEnum, Index, UniqueConstraint, and_
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base_class import Base


# Enums
class TenantType(str, enum.Enum):
    """Tenant type enumeration."""
    PLATFORM = "platform"
    ORGANIZATION = "organization"
    SCHOOL = "school"  # Deprecated, use INSTITUTION
    INSTITUTION = "institution"  # Replaces SCHOOL


class UserStatus(str, enum.Enum):
    """User status enumeration."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    LOCKED = "locked"
    PENDING_VERIFICATION = "pending_verification"
    PENDING_APPROVAL = "pending_approval"
    INVITED = "invited"


class RoleName(str, enum.Enum):
    """System role names."""
    SUPER_ADMIN = "super_admin"
    ORG_ADMIN = "org_admin"
    SCHOOL_ADMIN = "school_admin"  # Deprecated, use INSTITUTION_ADMIN
    INSTITUTION_ADMIN = "institution_admin"  # Replaces SCHOOL_ADMIN
    TEACHER = "teacher"
    STUDENT = "student"
    PARENT = "parent"


class RoleScope(str, enum.Enum):
    """Role scope enumeration."""
    PLATFORM = "platform"
    ORGANIZATION = "organization"
    SCHOOL = "school"  # Deprecated, use INSTITUTION
    INSTITUTION = "institution"  # Replaces SCHOOL


class AuditEventType(str, enum.Enum):
    """Audit event type enumeration."""
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILURE = "login_failure"
    LOGOUT = "logout"
    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"
    USER_DELETED = "user_deleted"
    ROLE_ASSIGNED = "role_assigned"
    ROLE_REVOKED = "role_revoked"
    PASSWORD_CHANGED = "password_changed"
    PASSWORD_RESET_REQUESTED = "password_reset_requested"
    EMAIL_VERIFIED = "email_verified"
    ACCOUNT_LOCKED = "account_locked"
    ACCOUNT_UNLOCKED = "account_unlocked"


class InstitutionType(str, enum.Enum):
    """Institution type enumeration."""
    K12_SCHOOL = "k12_school"
    COLLEGE = "college"
    UNIVERSITY = "university"
    TRAINING_CENTER = "training_center"
    OTHER = "other"

class ScopeType(str, enum.Enum):
    """Scope type for memberships."""
    INSTITUTION = "institution"
    PERSONAL_WORKSPACE = "personal_workspace"
    ORGANIZATION = "organization"


class InviteStatus(str, enum.Enum):
    """Invite status enumeration."""
    PENDING = "pending"
    ACCEPTED = "accepted"
    EXPIRED = "expired"
    REVOKED = "revoked"


# Models
class Tenant(Base):
    """Tenant model for multi-tenancy (Platform, Organization, Institution)."""
    
    __tablename__ = "tenants"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(200), nullable=False)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    type = Column(SQLEnum(TenantType, values_callable=lambda x: [e.value for e in x]), nullable=False)
    
    # Hierarchical structure
    parent_tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True)
    hierarchy_path = Column(String(500), nullable=False, index=True)  # e.g., "/org-123/school-456/"
    
    # Settings
    settings = Column(JSON, nullable=True)  # Tenant-specific settings
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    
    # Relationships
    parent = relationship("Tenant", remote_side=[id], backref="children")
    users = relationship("User", back_populates="tenant", lazy="dynamic")
    
    def __repr__(self) -> str:
        return f"<Tenant(id={self.id}, name={self.name}, type={self.type})>"


class User(Base):
    """User model for authentication and user accounts."""
    
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    # Tenant association
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True)
    
    # Authentication
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), unique=True, nullable=True, index=True)
    password_hash = Column(String(255), nullable=False)
    
    # Profile
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    full_name = Column(String(200), nullable=True)  # Computed field, can be updated
    phone = Column(String(20), nullable=True)
    profile_picture_url = Column(String(500), nullable=True)

    # Preferences (language/timezone/theme, etc.)
    preferences = Column(JSON, nullable=True)
    
    # Status
    status = Column(SQLEnum(UserStatus, values_callable=lambda x: [e.value for e in x]), default=UserStatus.PENDING_VERIFICATION, nullable=False, index=True)
    email_verified = Column(Boolean, default=False, nullable=False, index=True)
    
    # Security
    failed_login_attempts = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    last_password_change_at = Column(DateTime(timezone=True), nullable=True)
    must_change_password = Column(Boolean, default=False, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    
    # Relationships
    tenant = relationship("Tenant", back_populates="users")
    roles = relationship("UserRole", foreign_keys="UserRole.user_id", back_populates="user", cascade="all, delete-orphan")
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
    memberships = relationship("UserMembership", foreign_keys="UserMembership.user_id", back_populates="user", cascade="all, delete-orphan")
    personal_workspace = relationship("PersonalWorkspace", back_populates="user", uselist=False, cascade="all, delete-orphan")
    teacher_profile_context = relationship(
        "TeacherProfileContext", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email}, status={self.status})>"


class ContextResolutionStatus(str, enum.Enum):
    """Teacher profile context resolution status for education framework mapping."""
    RESOLVED = "resolved"
    PARTIAL = "partial"
    NOT_FOUND = "not_found"


class TeacherProfileContext(Base):
    """
    Teacher professional learning context for Hyper-Personalization and Professional Learning Hub.
    Maps a teacher to their national/regional education framework.
    """
    __tablename__ = "teacher_profile_context"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)

    # Core required (for framework mapping)
    country = Column(String(100), nullable=False, index=True)
    region = Column(String(150), nullable=False, index=True)
    school_type = Column(String(50), nullable=False)  # Public, Private, Charter, International, Other
    grade_band = Column(String(50), nullable=False)  # K–2, 3–5, 6–8, 9–12, Higher Education, Other
    subjects = Column(JSON, nullable=False)  # ["Math", "Science"] array
    language_preference = Column(String(100), nullable=False)

    # Optional (strongly recommended)
    school_name = Column(String(200), nullable=True)
    city = Column(String(100), nullable=True)
    postal_code = Column(String(20), nullable=True)
    curriculum_framework = Column(String(80), nullable=True)  # National Curriculum, Common Core, IB, etc.
    years_experience = Column(String(20), nullable=True)  # 0–2, 3–5, 6–10, 10+
    professional_goals = Column(JSON, nullable=True)  # ["classroom engagement", "differentiation", ...]

    # Resolution status (set by external_context service)
    context_resolution_status = Column(
        String(20), nullable=True, index=True,
        default=ContextResolutionStatus.NOT_FOUND.value
    )

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="teacher_profile_context", uselist=False)

    def __repr__(self) -> str:
        return f"<TeacherProfileContext(user_id={self.user_id}, country={self.country}, status={self.context_resolution_status})>"


class Role(Base):
    """Role model for RBAC."""
    
    __tablename__ = "roles"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(SQLEnum(RoleName, values_callable=lambda x: [e.value for e in x]), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    scope = Column(SQLEnum(RoleScope, values_callable=lambda x: [e.value for e in x]), nullable=False)
    is_system_role = Column(Boolean, default=False, nullable=False)  # Cannot be deleted
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    
    # Relationships
    permissions = relationship("RolePermission", back_populates="role", cascade="all, delete-orphan")
    user_roles = relationship("UserRole", back_populates="role")
    user_memberships = relationship("UserMembership", back_populates="role")
    invites = relationship("Invite", back_populates="role")
    
    def __repr__(self) -> str:
        return f"<Role(id={self.id}, name={self.name}, scope={self.scope})>"


class Permission(Base):
    """Permission model for fine-grained access control."""
    
    __tablename__ = "permissions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)  # e.g., "user:create", "school:manage"
    description = Column(Text, nullable=True)
    resource = Column(String(50), nullable=False, index=True)  # e.g., "user", "school", "course"
    action = Column(String(50), nullable=False, index=True)  # e.g., "create", "read", "update", "delete", "manage"
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    
    # Relationships
    role_permissions = relationship("RolePermission", back_populates="permission")
    
    def __repr__(self) -> str:
        return f"<Permission(id={self.id}, name={self.name})>"


class RolePermission(Base):
    """Many-to-many relationship between roles and permissions."""
    
    __tablename__ = "role_permissions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True)
    permission_id = Column(UUID(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    
    # Relationships
    role = relationship("Role", back_populates="permissions")
    permission = relationship("Permission", back_populates="role_permissions")
    
    # Unique constraint
    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),
        Index("idx_role_permission", "role_id", "permission_id"),
    )
    
    def __repr__(self) -> str:
        return f"<RolePermission(role_id={self.role_id}, permission_id={self.permission_id})>"


class UserRole(Base):
    """User-role assignments with tenant scope."""
    
    __tablename__ = "user_roles"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Tenant scope for this role assignment
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Optional scope restrictions (e.g., specific class_ids, resource_ids)
    scope = Column(JSON, nullable=True)  # {"class_ids": ["uuid1"], "resource_ids": [...]}
    
    # Audit
    granted_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    granted_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id], back_populates="roles")
    role = relationship("Role", back_populates="user_roles")
    tenant = relationship("Tenant", foreign_keys=[tenant_id])
    grantor = relationship("User", foreign_keys=[granted_by])
    
    # Unique constraint
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", "tenant_id", name="uq_user_role_tenant"),
        Index("idx_user_role_tenant", "user_id", "role_id", "tenant_id"),
    )
    
    def __repr__(self) -> str:
        return f"<UserRole(user_id={self.user_id}, role_id={self.role_id}, tenant_id={self.tenant_id})>"


class RefreshToken(Base):
    """Refresh token model for JWT token refresh."""
    
    __tablename__ = "refresh_tokens"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Token hash (never store plain token)
    token_hash = Column(String(255), unique=True, nullable=False, index=True)
    
    # Device/Client info
    device_info = Column(JSON, nullable=True)  # {"user_agent": "...", "ip": "..."}
    
    # Expiration
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    
    # Revocation
    revoked_at = Column(DateTime(timezone=True), nullable=True, index=True)
    revoked_reason = Column(String(100), nullable=True)
    
    # Token rotation (for refresh token rotation)
    parent_token_id = Column(UUID(as_uuid=True), ForeignKey("refresh_tokens.id", ondelete="SET NULL"), nullable=True)
    next_token_id = Column(UUID(as_uuid=True), ForeignKey("refresh_tokens.id", ondelete="SET NULL"), nullable=True)
    
    # Active membership context (which membership this token is scoped to)
    active_membership_id = Column(UUID(as_uuid=True), ForeignKey("user_memberships.id", ondelete="SET NULL"), nullable=True, index=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="refresh_tokens")
    active_membership = relationship("UserMembership", foreign_keys=[active_membership_id])
    
    def __repr__(self) -> str:
        return f"<RefreshToken(id={self.id}, user_id={self.user_id}, expires_at={self.expires_at})>"


class PasswordResetToken(Base):
    """Password reset token model."""
    
    __tablename__ = "password_reset_tokens"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Token hash (never store plain token)
    token_hash = Column(String(255), unique=True, nullable=False, index=True)
    
    # Expiration
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    
    # Usage tracking
    used_at = Column(DateTime(timezone=True), nullable=True)
    
    # Security tracking
    ip_address = Column(String(45), nullable=True)  # IPv6 support
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    
    def __repr__(self) -> str:
        return f"<PasswordResetToken(id={self.id}, user_id={self.user_id}, expires_at={self.expires_at})>"


class EmailVerificationToken(Base):
    """Email verification token model."""
    
    __tablename__ = "email_verification_tokens"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Token hash (never store plain token)
    token_hash = Column(String(255), unique=True, nullable=False, index=True)
    
    # Expiration
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    
    # Verification tracking
    verified_at = Column(DateTime(timezone=True), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    
    def __repr__(self) -> str:
        return f"<EmailVerificationToken(id={self.id}, user_id={self.user_id}, expires_at={self.expires_at})>"


class ParentStudentLink(Base):
    """Parent-student relationship model."""
    
    __tablename__ = "parent_student_links"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Verification
    is_verified = Column(Boolean, default=False, nullable=False, index=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    verified_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    
    # Relationships
    parent = relationship("User", foreign_keys=[parent_id])
    student = relationship("User", foreign_keys=[student_id])
    verifier = relationship("User", foreign_keys=[verified_by])
    
    # Unique constraint
    __table_args__ = (
        UniqueConstraint("parent_id", "student_id", name="uq_parent_student"),
        Index("idx_parent_student", "parent_id", "student_id"),
    )
    
    def __repr__(self) -> str:
        return f"<ParentStudentLink(parent_id={self.parent_id}, student_id={self.student_id})>"


class Institution(Base):
    """Institution model (replaces School concept)."""
    
    __tablename__ = "institutions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    # Basic info
    name = Column(String(200), nullable=False)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    institution_type = Column(SQLEnum(InstitutionType, values_callable=lambda x: [e.value for e in x]), nullable=False)
    
    # Organization relationship (references Tenant with type=ORGANIZATION)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    
    # Settings
    settings = Column(JSON, nullable=True)
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    
    # Relationships
    organization = relationship("Tenant", foreign_keys=[organization_id])
    # Note: memberships relationship is handled via scope_id in UserMembership
    
    def __repr__(self) -> str:
        return f"<Institution(id={self.id}, name={self.name}, type={self.institution_type})>"


class PersonalWorkspace(Base):
    """Personal workspace model for individual users."""
    
    __tablename__ = "personal_workspaces"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    
    # Workspace info
    name = Column(String(200), default="Personal Workspace", nullable=False)
    settings = Column(JSON, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="personal_workspace")
    memberships = relationship(
        "UserMembership",
        back_populates="personal_workspace",
        primaryjoin="and_(PersonalWorkspace.id == UserMembership.scope_id, UserMembership.scope_type == 'personal_workspace')",
        foreign_keys="[UserMembership.scope_id]"
    )
    
    def __repr__(self) -> str:
        return f"<PersonalWorkspace(id={self.id}, user_id={self.user_id}, name={self.name})>"


class UserMembership(Base):
    """User membership model for multi-tenant access."""
    
    __tablename__ = "user_memberships"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Scope (what the membership is for)
    scope_type = Column(SQLEnum(ScopeType, values_callable=lambda x: [e.value for e in x]), nullable=False, index=True)
    scope_id = Column(UUID(as_uuid=True), nullable=False, index=True)  # ID of institution, personal_workspace, or organization
    
    # Role in this scope
    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    
    # Audit
    granted_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    granted_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revoked_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id], back_populates="memberships")
    role = relationship("Role", back_populates="user_memberships")
    grantor = relationship("User", foreign_keys=[granted_by])
    revoker = relationship("User", foreign_keys=[revoked_by])
    personal_workspace = relationship(
        "PersonalWorkspace",
        primaryjoin="and_(PersonalWorkspace.id == UserMembership.scope_id, UserMembership.scope_type == 'personal_workspace')",
        back_populates="memberships",
        foreign_keys="[UserMembership.scope_id]"
    )
    
    # Note: Polymorphic relationships are handled in service layer based on scope_type
    
    # Unique constraint
    __table_args__ = (
        UniqueConstraint("user_id", "scope_type", "scope_id", name="uq_user_membership_scope"),
        Index("idx_user_membership_scope", "user_id", "scope_type", "scope_id"),
        Index("idx_user_membership_active", "user_id", "is_active"),
    )
    
    def __repr__(self) -> str:
        return f"<UserMembership(id={self.id}, user_id={self.user_id}, scope_type={self.scope_type}, scope_id={self.scope_id})>"


class Invite(Base):
    """Invite model for user invitations."""
    
    __tablename__ = "invites"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    # Invite details
    email = Column(String(255), nullable=False, index=True)
    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Scope (what the invite is for)
    scope_type = Column(SQLEnum(ScopeType, values_callable=lambda x: [e.value for e in x]), nullable=False, index=True)
    scope_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    # Token
    token_hash = Column(String(255), unique=True, nullable=False, index=True)
    
    # Status
    status = Column(SQLEnum(InviteStatus, values_callable=lambda x: [e.value for e in x]), default=InviteStatus.PENDING, nullable=False, index=True)
    
    # Expiration
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    
    # Audit
    invited_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    accepted_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    
    # Relationships
    role = relationship("Role", back_populates="invites")
    inviter = relationship("User", foreign_keys=[invited_by])
    accepted_by = relationship("User", foreign_keys=[accepted_by_user_id])
    
    # Note: Polymorphic relationships are handled in service layer based on scope_type
    
    # Indexes
    __table_args__ = (
        Index("idx_invite_email_status", "email", "status"),
        Index("idx_invite_scope", "scope_type", "scope_id"),
    )
    
    def __repr__(self) -> str:
        return f"<Invite(id={self.id}, email={self.email}, status={self.status})>"


class AuditLog(Base):
    """Audit log model for security and compliance tracking."""
    
    __tablename__ = "audit_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    # Context
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True, index=True)
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    actor_type = Column(String(20), nullable=False, default="user")  # "user" or "system"
    
    # Target
    target_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    target_type = Column(String(50), nullable=True)  # "user", "tenant", "role", etc.
    
    # Event
    event_type = Column(SQLEnum(AuditEventType, values_callable=lambda x: [e.value for e in x]), nullable=False, index=True)
    description = Column(Text, nullable=False)
    event_metadata = Column(JSON, nullable=True)  # Additional event data (renamed from metadata to avoid SQLAlchemy conflict)
    
    # Request context
    ip_address = Column(String(45), nullable=True)  # IPv6 support
    user_agent = Column(String(500), nullable=True)
    request_id = Column(String(100), nullable=True, index=True)  # For tracing
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    
    # Relationships
    tenant = relationship("Tenant", foreign_keys=[tenant_id])
    actor = relationship("User", foreign_keys=[actor_user_id])
    target = relationship("User", foreign_keys=[target_user_id])
    
    # Index for common queries
    __table_args__ = (
        Index("idx_audit_tenant_event", "tenant_id", "event_type", "created_at"),
        Index("idx_audit_actor", "actor_user_id", "created_at"),
    )
    
    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, event_type={self.event_type}, created_at={self.created_at})>"

