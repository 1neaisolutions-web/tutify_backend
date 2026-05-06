"""
Seeder for creating the first super admin user.
Follows Django's createsuperuser pattern - industry standard for Python.
"""
from typing import Optional
from sqlalchemy.orm import Session

from app.domains.auth.models import (
    User,
    UserStatus,
    Role,
    RoleName,
    Tenant,
    TenantType,
    UserRole,
)
from app.core.security import hash_password, validate_password_strength
from app.core.config import settings
from app.core.logging import get_logger
from app.domains.auth.services import UserService
from app.domains.auth.schemas import CreateUserRequest

logger = get_logger(__name__)


def seed_super_admin(
    db: Session,
    email: Optional[str] = None,
    password: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    force: bool = False,
) -> dict:
    """
    Create the first super admin user using application services.
    
    This follows Django's createsuperuser pattern - the industry standard
    for Python web applications.
    
    Args:
        db: Database session
        email: Admin email (if None, uses env var or skips)
        password: Admin password (if None, uses env var or skips)
        first_name: Admin first name
        last_name: Admin last name
        force: If True, recreate even if exists
        
    Returns:
        Dictionary with creation results
    """
    result = {
        "created": False,
        "skipped": False,
        "error": None,
        "user_id": None,
        "email": None,
    }
    
    # Get email and password from args or environment
    admin_email = email or settings.SUPER_ADMIN_EMAIL
    admin_password = password or settings.SUPER_ADMIN_PASSWORD
    admin_first_name = first_name or settings.SUPER_ADMIN_FIRST_NAME
    admin_last_name = last_name or settings.SUPER_ADMIN_LAST_NAME
    
    # Skip if no credentials provided
    if not admin_email or not admin_password:
        logger.info("Skipping super admin creation: No credentials provided")
        result["skipped"] = True
        result["error"] = "Email and password required (via args or environment variables)"
        return result
    
    try:
        # Get platform tenant
        platform = db.query(Tenant).filter(Tenant.type == TenantType.PLATFORM).first()
        if not platform:
            result["error"] = "Platform tenant not found. Run: python -m app.seed.cli --auth"
            return result
        
        # Get super_admin role
        super_admin_role = db.query(Role).filter(Role.name == RoleName.SUPER_ADMIN).first()
        if not super_admin_role:
            result["error"] = "Super admin role not found. Run: python -m app.seed.cli --auth"
            return result
        
        # Check if super admin already exists
        existing_admin = (
            db.query(User)
            .join(UserRole)
            .filter(
                UserRole.role_id == super_admin_role.id,
                User.email == admin_email.lower(),
                User.status == UserStatus.ACTIVE
            )
            .first()
        )
        
        if existing_admin and not force:
            logger.info(f"Super admin already exists: {admin_email}")
            result["skipped"] = True
            result["user_id"] = str(existing_admin.id)
            result["email"] = admin_email
            return result
        
        # Use application service for user creation
        # This ensures all business logic, validation, and audit logging
        user_service = UserService(db)
        
        # Create user using application service
        # This handles: password validation, hashing, email normalization, etc.
        user = user_service.create_user(
            CreateUserRequest(
                email=admin_email,
                password=admin_password,
                first_name=admin_first_name,
                last_name=admin_last_name,
                role_name=RoleName.SUPER_ADMIN,
            ),
            tenant_id=platform.id,
            created_by=None if not existing_admin else existing_admin.id,
        )
        
        result["created"] = True
        result["user_id"] = str(user.id)
        result["email"] = user.email
        logger.info(f"Super admin created successfully: {user.email}")
        
    except Exception as e:
        logger.error(f"Error creating super admin: {e}", exc_info=True)
        db.rollback()
        result["error"] = str(e)
    
    return result

