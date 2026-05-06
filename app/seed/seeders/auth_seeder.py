"""
Seeder for authentication data (roles, permissions, platform tenant).
"""
from sqlalchemy.orm import Session

from app.domains.auth.models import (
    Tenant,
    Role,
    Permission,
    RolePermission,
    TenantType,
    RoleName,
    RoleScope,
)
from app.core.logging import get_logger

logger = get_logger(__name__)


# Default permissions
DEFAULT_PERMISSIONS = [
    # User management
    {"name": "user:create", "description": "Create users", "resource": "user", "action": "create"},
    {"name": "user:read", "description": "View users", "resource": "user", "action": "read"},
    {"name": "user:update", "description": "Update users", "resource": "user", "action": "update"},
    {"name": "user:delete", "description": "Delete users", "resource": "user", "action": "delete"},
    {"name": "user:manage", "description": "Full user management", "resource": "user", "action": "manage"},
    
    # School management
    {"name": "school:create", "description": "Create schools", "resource": "school", "action": "create"},
    {"name": "school:read", "description": "View schools", "resource": "school", "action": "read"},
    {"name": "school:update", "description": "Update schools", "resource": "school", "action": "update"},
    {"name": "school:delete", "description": "Delete schools", "resource": "school", "action": "delete"},
    {"name": "school:manage", "description": "Full school management", "resource": "school", "action": "manage"},
    
    # Organization management
    {"name": "org:create", "description": "Create organizations", "resource": "organization", "action": "create"},
    {"name": "org:read", "description": "View organizations", "resource": "organization", "action": "read"},
    {"name": "org:update", "description": "Update organizations", "resource": "organization", "action": "update"},
    {"name": "org:delete", "description": "Delete organizations", "resource": "organization", "action": "delete"},
    {"name": "org:manage", "description": "Full organization management", "resource": "organization", "action": "manage"},
    
    # Role management
    {"name": "role:assign", "description": "Assign roles", "resource": "role", "action": "assign"},
    {"name": "role:revoke", "description": "Revoke roles", "resource": "role", "action": "revoke"},
    {"name": "role:manage", "description": "Full role management", "resource": "role", "action": "manage"},
    
    # Self-registration
    {"name": "signup:approve", "description": "Approve signups", "resource": "signup", "action": "approve"},
    {"name": "signup:reject", "description": "Reject signups", "resource": "signup", "action": "reject"},
]


# Role-permission mappings
ROLE_PERMISSIONS = {
    RoleName.SUPER_ADMIN: [
        # Super admin has all permissions
        "user:manage",
        "school:manage",
        "org:manage",
        "role:manage",
        "signup:approve",
        "signup:reject",
    ],
    RoleName.ORG_ADMIN: [
        "user:manage",
        "school:create",
        "school:read",
        "school:update",
        "school:delete",
        "role:assign",
        "signup:approve",
        "signup:reject",
    ],
    RoleName.SCHOOL_ADMIN: [
        "user:create",
        "user:read",
        "user:update",
        "user:delete",
        "school:read",
        "school:update",
        "role:assign",
        "signup:approve",
        "signup:reject",
    ],
    RoleName.TEACHER: [
        "user:read",  # View other teachers/students
    ],
    RoleName.STUDENT: [
        # Students have minimal permissions - can be extended
    ],
    RoleName.PARENT: [
        # Parents have minimal permissions - can be extended
    ],
}


def seed_platform_tenant(db: Session) -> Tenant:
    """Create or get platform tenant."""
    platform = db.query(Tenant).filter(Tenant.type == TenantType.PLATFORM).first()
    
    if not platform:
        platform = Tenant(
            name="Platform",
            slug="platform",
            type=TenantType.PLATFORM,
            parent_tenant_id=None,
            hierarchy_path="/",
            is_active=True,
        )
        db.add(platform)
        db.commit()
        db.refresh(platform)
        logger.info("Created platform tenant")
    else:
        logger.info("Platform tenant already exists")
    
    return platform


def seed_roles(db: Session) -> dict:
    """Seed system roles."""
    roles = {}
    
    role_definitions = [
        {"name": RoleName.SUPER_ADMIN, "description": "Super Administrator", "scope": RoleScope.PLATFORM},
        {"name": RoleName.ORG_ADMIN, "description": "Organization Administrator", "scope": RoleScope.ORGANIZATION},
        {"name": RoleName.SCHOOL_ADMIN, "description": "School Administrator (Principal)", "scope": RoleScope.SCHOOL},
        {"name": RoleName.TEACHER, "description": "Teacher", "scope": RoleScope.SCHOOL},
        {"name": RoleName.STUDENT, "description": "Student", "scope": RoleScope.SCHOOL},
        {"name": RoleName.PARENT, "description": "Parent", "scope": RoleScope.SCHOOL},
    ]
    
    for role_def in role_definitions:
        role = db.query(Role).filter(Role.name == role_def["name"]).first()
        
        if not role:
            role = Role(
                name=role_def["name"],
                description=role_def["description"],
                scope=role_def["scope"],
                is_system_role=True,
                is_active=True,
            )
            db.add(role)
            db.commit()
            db.refresh(role)
            logger.info(f"Created role: {role_def['name']}")
        else:
            logger.info(f"Role already exists: {role_def['name']}")
        
        roles[role_def["name"]] = role
    
    return roles


def seed_permissions(db: Session) -> dict:
    """Seed permissions."""
    permissions = {}
    
    for perm_def in DEFAULT_PERMISSIONS:
        permission = db.query(Permission).filter(Permission.name == perm_def["name"]).first()
        
        if not permission:
            permission = Permission(
                name=perm_def["name"],
                description=perm_def["description"],
                resource=perm_def["resource"],
                action=perm_def["action"],
            )
            db.add(permission)
            db.commit()
            db.refresh(permission)
            logger.info(f"Created permission: {perm_def['name']}")
        else:
            logger.info(f"Permission already exists: {perm_def['name']}")
        
        permissions[perm_def["name"]] = permission
    
    return permissions


def seed_role_permissions(db: Session, roles: dict, permissions: dict) -> None:
    """Seed role-permission mappings."""
    for role_name, permission_names in ROLE_PERMISSIONS.items():
        role = roles.get(role_name)
        if not role:
            continue
        
        for perm_name in permission_names:
            permission = permissions.get(perm_name)
            if not permission:
                logger.warning(f"Permission {perm_name} not found for role {role_name}")
                continue
            
            # Check if mapping already exists
            existing = db.query(RolePermission).filter(
                RolePermission.role_id == role.id,
                RolePermission.permission_id == permission.id,
            ).first()
            
            if not existing:
                role_permission = RolePermission(
                    role_id=role.id,
                    permission_id=permission.id,
                )
                db.add(role_permission)
                logger.info(f"Linked permission {perm_name} to role {role_name}")
    
    db.commit()


def seed_auth_data(db: Session, force: bool = False) -> dict:
    """
    Seed all authentication data.
    
    Args:
        db: Database session
        force: If True, recreate existing data
        
    Returns:
        Dictionary with seeding results
    """
    results = {
        "platform_tenant_created": False,
        "roles_created": 0,
        "permissions_created": 0,
        "role_permissions_created": 0,
    }
    
    try:
        # Seed platform tenant
        platform = seed_platform_tenant(db)
        results["platform_tenant_created"] = platform.id is not None
        
        # Seed roles
        roles = seed_roles(db)
        results["roles_created"] = len(roles)
        
        # Seed permissions
        permissions = seed_permissions(db)
        results["permissions_created"] = len(permissions)
        
        # Seed role-permission mappings
        seed_role_permissions(db, roles, permissions)
        
        # Count role-permission mappings
        results["role_permissions_created"] = db.query(RolePermission).count()
        
        logger.info("Auth data seeding completed successfully")
        return results
        
    except Exception as e:
        logger.error(f"Error seeding auth data: {e}")
        db.rollback()
        raise



