"""migrate_school_to_institution

Revision ID: d6e42d4a8046
Revises: 9648346e2f84
Create Date: 2026-01-03 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd6e42d4a8046'
down_revision: Union[str, None] = '9648346e2f84'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Migrate existing data from School model to Institution model.
    This migration:
    1. Migrates Tenant records with type=SCHOOL to type=INSTITUTION
    2. Creates Institution records from Tenant records
    3. Migrates UserRole records to UserMembership format
    4. Creates PersonalWorkspace records for individual users
    """
    connection = op.get_bind()
    
    # Step 1: Migrate Tenant records with type=SCHOOL to type=INSTITUTION
    # Note: We keep both SCHOOL and INSTITUTION in enum for backward compatibility
    # Update tenant type from SCHOOL to INSTITUTION
    connection.execute(sa.text("""
        UPDATE tenants 
        SET type = 'institution' 
        WHERE type = 'school'
    """))
    
    # Step 2: Create Institution records from Tenant records with type=INSTITUTION
    connection.execute(sa.text("""
        INSERT INTO institutions (id, name, slug, institution_type, organization_id, settings, is_active, created_at, updated_at)
        SELECT 
            t.id,
            t.name,
            t.slug,
            'k12_school'::institutiontype,  -- Default type
            t.parent_tenant_id,
            t.settings,
            t.is_active,
            t.created_at,
            t.updated_at
        FROM tenants t
        WHERE t.type = 'institution'
        AND NOT EXISTS (
            SELECT 1 FROM institutions i WHERE i.id = t.id
        )
    """))
    
    # Step 3: Migrate UserRole records to UserMembership format
    # For each UserRole, create a corresponding UserMembership
    connection.execute(sa.text("""
        INSERT INTO user_memberships (
            id, user_id, scope_type, scope_id, role_id, is_active, 
            granted_by, granted_at, created_at, updated_at
        )
        SELECT 
            gen_random_uuid(),  -- New UUID for membership
            ur.user_id,
            CASE 
                WHEN t.type = 'institution' THEN 'institution'::scopetype
                WHEN t.type = 'organization' THEN 'organization'::scopetype
                WHEN t.type = 'platform' THEN 'personal_workspace'::scopetype
                ELSE 'institution'::scopetype
            END,
            ur.tenant_id,  -- scope_id = tenant_id
            ur.role_id,
            TRUE,  -- is_active
            ur.granted_by,
            ur.granted_at,
            ur.granted_at,  -- created_at
            ur.granted_at   -- updated_at
        FROM user_roles ur
        JOIN tenants t ON ur.tenant_id = t.id
        WHERE NOT EXISTS (
            SELECT 1 FROM user_memberships um 
            WHERE um.user_id = ur.user_id 
            AND um.scope_id = ur.tenant_id
            AND um.role_id = ur.role_id
        )
    """))
    
    # Step 4: Create PersonalWorkspace records for users without institution memberships
    # Users who only have platform-scoped roles should get a personal workspace
    connection.execute(sa.text("""
        INSERT INTO personal_workspaces (id, user_id, name, settings, created_at, updated_at)
        SELECT 
            gen_random_uuid(),
            u.id,
            'Personal Workspace',
            NULL,
            u.created_at,
            u.created_at
        FROM users u
        WHERE NOT EXISTS (
            SELECT 1 FROM personal_workspaces pw WHERE pw.user_id = u.id
        )
        AND EXISTS (
            SELECT 1 FROM user_roles ur
            JOIN tenants t ON ur.tenant_id = t.id
            WHERE ur.user_id = u.id
            AND t.type = 'platform'
        )
        AND NOT EXISTS (
            SELECT 1 FROM user_roles ur
            JOIN tenants t ON ur.tenant_id = t.id
            WHERE ur.user_id = u.id
            AND t.type IN ('institution', 'organization')
        )
    """))
    
    # Step 5: Create memberships for personal workspaces
    connection.execute(sa.text("""
        INSERT INTO user_memberships (
            id, user_id, scope_type, scope_id, role_id, is_active,
            granted_by, granted_at, created_at, updated_at
        )
        SELECT 
            gen_random_uuid(),
            pw.user_id,
            'personal_workspace'::scopetype,
            pw.id,
            ur.role_id,
            TRUE,
            NULL,
            pw.created_at,
            pw.created_at,
            pw.created_at
        FROM personal_workspaces pw
        JOIN users u ON pw.user_id = u.id
        JOIN user_roles ur ON ur.user_id = u.id
        JOIN tenants t ON ur.tenant_id = t.id
        WHERE t.type = 'platform'
        AND NOT EXISTS (
            SELECT 1 FROM user_memberships um
            WHERE um.user_id = pw.user_id
            AND um.scope_type = 'personal_workspace'
            AND um.scope_id = pw.id
        )
    """))
    
    # Step 6: Update RoleName enum values in roles table
    # Update SCHOOL_ADMIN to INSTITUTION_ADMIN in roles
    connection.execute(sa.text("""
        UPDATE roles
        SET name = 'institution_admin'::rolename
        WHERE name = 'school_admin'::rolename
    """))
    
    # Step 7: Update UserRole records that reference school_admin role
    # This is handled by the role update above, but we need to ensure consistency
    # Note: The role_id foreign key will still work because we're updating the role name, not the ID


def downgrade() -> None:
    """
    Reverse the migration.
    Note: This is a destructive operation and should be used with caution.
    """
    connection = op.get_bind()
    
    # Reverse Step 7: Update roles back
    connection.execute(sa.text("""
        UPDATE roles
        SET name = 'school_admin'::rolename
        WHERE name = 'institution_admin'::rolename
    """))
    
    # Reverse Step 5: Delete personal workspace memberships
    connection.execute(sa.text("""
        DELETE FROM user_memberships
        WHERE scope_type = 'personal_workspace'
    """))
    
    # Reverse Step 4: Delete personal workspaces
    connection.execute(sa.text("""
        DELETE FROM personal_workspaces
    """))
    
    # Reverse Step 3: Delete user memberships
    connection.execute(sa.text("""
        DELETE FROM user_memberships
    """))
    
    # Reverse Step 2: Delete institutions
    connection.execute(sa.text("""
        DELETE FROM institutions
    """))
    
    # Reverse Step 1: Update tenant types back
    connection.execute(sa.text("""
        UPDATE tenants 
        SET type = 'school' 
        WHERE type = 'institution'
    """))
