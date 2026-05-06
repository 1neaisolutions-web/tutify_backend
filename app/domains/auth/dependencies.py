"""
FastAPI dependencies for authentication and authorization.
"""
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.security import decode_token
from app.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    AccountLockedError,
    EmailNotVerifiedError,
)
from app.domains.auth.models import User, UserStatus
from app.core.logging import get_logger

logger = get_logger(__name__)

# HTTP Bearer token scheme (auto_error=False so we can return 401 with a clear message)
security = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """
    FastAPI dependency to get the current authenticated user.
    
    Raises:
        AuthenticationError: If token is invalid or user not found
        AccountLockedError: If account is locked
        EmailNotVerifiedError: If email is not verified
    """
    if not credentials:
        raise AuthenticationError(
            "Not authenticated. Provide a valid Bearer token in the Authorization header (e.g. Authorization: Bearer <access_token>)."
        )
    token = credentials.credentials

    try:
        logger.debug(f"Validating token: {token[:20]}..." if len(token) > 20 else f"Token: {token}")
        payload = decode_token(token, token_type="access")
        user_id = payload.get("user_id")
        
        if not user_id:
            logger.error("Token payload missing user_id")
            raise AuthenticationError("Invalid token payload")
        
        logger.debug(f"Token decoded successfully, user_id: {user_id}")
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            logger.error(f"User not found for user_id: {user_id}")
            raise AuthenticationError("User not found")
        
        # Check account status
        if user.status == UserStatus.LOCKED:
            logger.warning(f"Account locked for user_id: {user_id}")
            raise AccountLockedError()
        
        if user.status != UserStatus.ACTIVE:
            logger.warning(f"Account not active for user_id: {user_id}, status: {user.status}")
            raise AuthenticationError(f"Account status: {user.status}")
        
        if not user.email_verified:
            logger.warning(f"Email not verified for user_id: {user_id}")
            raise EmailNotVerifiedError()
        
        logger.debug(f"Authentication successful for user_id: {user_id}")
        return user
        
    except Exception as e:
        if isinstance(e, (AccountLockedError, EmailNotVerifiedError, AuthenticationError)):
            raise
        logger.error(f"Authentication error: {str(e)}", exc_info=True)
        raise AuthenticationError(f"Could not validate credentials: {str(e)}")


def require_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Ensure user is active (additional check on top of get_current_user).
    """
    if current_user.status != UserStatus.ACTIVE:
        raise AuthenticationError(f"Account is not active. Status: {current_user.status}")
    
    return current_user


def require_permission(permission_name: str):
    """
    Factory function to create a dependency that requires a specific permission.
    
    Usage:
        @router.get("/admin/users")
        async def list_users(
            current_user: User = Depends(require_permission("user:read")),
            ...
        ):
            ...
    """
    def permission_checker(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        # Import RBACService directly from services.py file (not services/ directory)
        # Use importlib to import from the file directly
        import importlib.util
        import sys
        from pathlib import Path
        
        # Get the services.py file path
        current_file = Path(__file__)
        services_py_path = current_file.parent / "services.py"
        
        # Load the module
        spec = importlib.util.spec_from_file_location("auth_services_file", str(services_py_path))
        if spec and spec.loader:
            services_module = importlib.util.module_from_spec(spec)
            sys.modules["auth_services_file"] = services_module
            spec.loader.exec_module(services_module)
            RBACService = getattr(services_module, 'RBACService')
        else:
            raise ImportError("Could not load services.py module")
        
        rbac_service = RBACService(db)
        has_permission = rbac_service.check_permission(
            user_id=current_user.id,
            permission_name=permission_name,
            tenant_id=current_user.tenant_id,
        )
        
        if not has_permission:
            raise AuthorizationError(f"Permission required: {permission_name}")
        
        return current_user
    
    return permission_checker


def require_role(role_name: str):
    """
    Factory function to create a dependency that requires a specific role.
    
    Usage:
        @router.get("/admin/schools")
        async def list_schools(
            current_user: User = Depends(require_role("org_admin")),
            ...
        ):
            ...
    """
    def role_checker(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        # Check if user has the required role in their tenant
        from app.domains.auth.models import UserRole, Role, RoleName
        from sqlalchemy import or_
        
        # Map institution_admin to school_admin since database enum doesn't have institution_admin
        # IMPORTANT: Never use RoleName.INSTITUTION_ADMIN as it doesn't exist in the database enum
        if role_name == "institution_admin":
            # Map to school_admin (the actual enum value in DB)
            role_filter = Role.name == RoleName.SCHOOL_ADMIN
        elif role_name == "school_admin":
            role_filter = Role.name == RoleName.SCHOOL_ADMIN
        else:
            # Use RoleName enum value if it exists
            try:
                role_enum = RoleName(role_name)
                role_filter = Role.name == role_enum
            except ValueError:
                # If not a valid enum, this will fail - but shouldn't happen with valid role names
                raise AuthorizationError(f"Invalid role name: {role_name}")
        
        user_role = db.query(UserRole).join(Role).filter(
            UserRole.user_id == current_user.id,
            UserRole.tenant_id == current_user.tenant_id,
            role_filter,
        ).first()
        
        if not user_role:
            raise AuthorizationError(f"Role required: {role_name}")
        
        return current_user
    
    return role_checker


def require_any_role(*role_names: str):
    """
    Factory function to create a dependency that requires any one of the specified roles.
    
    Usage:
        @router.get("/admin/content")
        async def get_content(
            current_user: User = Depends(require_any_role("org_admin", "institution_admin", "super_admin")),
            ...
        ):
            ...
    """
    def role_checker(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        # Check if user has any of the required roles in their tenant
        from app.domains.auth.models import UserRole, Role, RoleName
        from sqlalchemy import or_
        
        # CRITICAL FIX: The database enum does NOT have "institution_admin"
        # We MUST replace it with "school_admin" BEFORE building any SQL queries
        
        # CRITICAL FIX: Database enum does NOT have "institution_admin"
        # MUST replace "institution_admin" with "school_admin" BEFORE any SQL operations
        # This prevents SQLAlchemy from passing invalid enum values to PostgreSQL
        
        # Step 1: Replace institution_admin with school_admin IMMEDIATELY
        # CRITICAL: Log what we're processing for debugging
        logger.debug(f"Processing roles: {role_names}")
        processed_roles = []
        for role_str in role_names:
            if role_str == "institution_admin":
                logger.info(f"Replacing 'institution_admin' with 'school_admin' (database enum fix)")
                processed_roles.append("school_admin")  # Replace with valid DB enum
            else:
                processed_roles.append(role_str)
        
        # Step 2: Remove duplicates
        processed_roles = list(dict.fromkeys(processed_roles))
        logger.debug(f"Processed roles after normalization: {processed_roles}")
        
        # Step 3: Build SQL filters using ONLY valid database enum values
        # NEVER use RoleName.INSTITUTION_ADMIN - it doesn't exist in database
        role_filters = []
        for role_str in processed_roles:
            # Explicitly map each role to its enum - no try/except to catch issues early
            if role_str == "school_admin":
                enum_val = RoleName.SCHOOL_ADMIN
            elif role_str == "org_admin":
                enum_val = RoleName.ORG_ADMIN
            elif role_str == "super_admin":
                enum_val = RoleName.SUPER_ADMIN
            elif role_str == "teacher":
                enum_val = RoleName.TEACHER
            elif role_str == "student":
                enum_val = RoleName.STUDENT
            elif role_str == "parent":
                enum_val = RoleName.PARENT
            else:
                # Log and skip unknown roles
                logger.warning(f"Unknown role '{role_str}' skipped - not in database enum")
                continue
            
            # Add filter - SQLAlchemy will use enum.value which matches database
            role_filters.append(Role.name == enum_val)
        
        # Safety check: Ensure we have at least one valid role filter
        if not role_filters:
            logger.error(f"No valid roles found after processing: {role_names}")
            raise AuthorizationError(f"Invalid role configuration. Required roles: {', '.join(role_names)}")
        
        # Combine all filters with OR
        combined_filter = or_(*role_filters)
        
        try:
            user_role = db.query(UserRole).join(Role).filter(
                UserRole.user_id == current_user.id,
                UserRole.tenant_id == current_user.tenant_id,
                combined_filter,
            ).first()
        except Exception as db_error:
            # Log the actual database error for debugging
            logger.error(f"Database error during role check: {db_error}", exc_info=True)
            # Re-raise as a more user-friendly error
            raise AuthorizationError(f"Database error during authorization check. Please try again.")
        
        if not user_role:
            raise AuthorizationError(f"One of the following roles required: {', '.join(role_names)}")
        
        return current_user
    
    return role_checker


def get_current_tenant(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get the current user's tenant.
    """
    from app.domains.auth.models import Tenant
    
    tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
    if not tenant:
        raise AuthenticationError("Tenant not found")
    
    return tenant


def get_optional_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """
    Optional authentication dependency that returns None if no token is provided.
    Useful for endpoints that work with or without authentication.
    
    Returns:
        User if token is valid, None if no token provided
    """
    if not credentials:
        return None
    
    token = credentials.credentials
    
    try:
        payload = decode_token(token, token_type="access")
        user_id = payload.get("user_id")
        
        if not user_id:
            return None
        
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return None
        
        # Check account status - only return user if active and verified
        if user.status == UserStatus.LOCKED:
            return None
        
        if user.status != UserStatus.ACTIVE:
            return None
        
        if not user.email_verified:
            return None
        
        return user
        
    except Exception as e:
        # Silently fail for optional auth
        logger.debug(f"Optional auth failed: {str(e)}")
        return None

