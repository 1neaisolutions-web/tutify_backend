"""add_institution_membership_models

Revision ID: 9648346e2f84
Revises: 52aabe358ec8
Create Date: 2026-01-03 21:28:49.917788

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '9648346e2f84'
down_revision: Union[str, None] = '52aabe358ec8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create new enums (create_type=True for explicit create with checkfirst; use create_type=False in tables so dialect won't recreate)
    institution_type_enum_create = postgresql.ENUM(
        'k12_school', 'college', 'university', 'training_center', 'other',
        name='institutiontype',
        create_type=True
    )
    institution_type_enum_create.create(op.get_bind(), checkfirst=True)
    institution_type_enum = postgresql.ENUM(
        'k12_school', 'college', 'university', 'training_center', 'other',
        name='institutiontype',
        create_type=False
    )

    scope_type_enum_create = postgresql.ENUM(
        'institution', 'personal_workspace', 'organization',
        name='scopetype',
        create_type=True
    )
    scope_type_enum_create.create(op.get_bind(), checkfirst=True)
    scope_type_enum = postgresql.ENUM(
        'institution', 'personal_workspace', 'organization',
        name='scopetype',
        create_type=False
    )

    invite_status_enum_create = postgresql.ENUM(
        'pending', 'accepted', 'expired', 'revoked',
        name='invitestatus',
        create_type=True
    )
    invite_status_enum_create.create(op.get_bind(), checkfirst=True)
    invite_status_enum = postgresql.ENUM(
        'pending', 'accepted', 'expired', 'revoked',
        name='invitestatus',
        create_type=False
    )
    
    # Add INSTITUTION to TenantType enum
    op.execute("ALTER TYPE tenanttype ADD VALUE IF NOT EXISTS 'institution'")
    
    # Add INSTITUTION_ADMIN to RoleName enum
    op.execute("ALTER TYPE rolename ADD VALUE IF NOT EXISTS 'institution_admin'")
    
    # Add INSTITUTION to RoleScope enum
    op.execute("ALTER TYPE rolescope ADD VALUE IF NOT EXISTS 'institution'")
    
    # Add INVITED to UserStatus enum
    op.execute("ALTER TYPE userstatus ADD VALUE IF NOT EXISTS 'invited'")
    
    # Create institutions table
    op.create_table(
        'institutions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('slug', sa.String(length=100), nullable=False),
        sa.Column('institution_type', institution_type_enum, nullable=False),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('settings', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug')
    )
    op.create_index(op.f('ix_institutions_id'), 'institutions', ['id'], unique=False)
    op.create_index(op.f('ix_institutions_organization_id'), 'institutions', ['organization_id'], unique=False)
    op.create_index(op.f('ix_institutions_slug'), 'institutions', ['slug'], unique=True)
    
    # Create personal_workspaces table
    op.create_table(
        'personal_workspaces',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('settings', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
    )
    op.create_index(op.f('ix_personal_workspaces_id'), 'personal_workspaces', ['id'], unique=False)
    op.create_index(op.f('ix_personal_workspaces_user_id'), 'personal_workspaces', ['user_id'], unique=True)
    
    # Create user_memberships table
    op.create_table(
        'user_memberships',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('scope_type', scope_type_enum, nullable=False),
        sa.Column('scope_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('role_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('granted_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('granted_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['granted_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['revoked_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'scope_type', 'scope_id', name='uq_user_membership_scope')
    )
    op.create_index(op.f('ix_user_memberships_id'), 'user_memberships', ['id'], unique=False)
    op.create_index(op.f('ix_user_memberships_user_id'), 'user_memberships', ['user_id'], unique=False)
    op.create_index(op.f('ix_user_memberships_scope_type'), 'user_memberships', ['scope_type'], unique=False)
    op.create_index(op.f('ix_user_memberships_scope_id'), 'user_memberships', ['scope_id'], unique=False)
    op.create_index(op.f('ix_user_memberships_role_id'), 'user_memberships', ['role_id'], unique=False)
    op.create_index('idx_user_membership_scope', 'user_memberships', ['user_id', 'scope_type', 'scope_id'], unique=False)
    op.create_index('idx_user_membership_active', 'user_memberships', ['user_id', 'is_active'], unique=False)
    
    # Create invites table
    op.create_table(
        'invites',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('role_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('scope_type', scope_type_enum, nullable=False),
        sa.Column('scope_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('token_hash', sa.String(length=255), nullable=False),
        sa.Column('status', invite_status_enum, nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('invited_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('accepted_by_user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['invited_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['accepted_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_hash')
    )
    op.create_index(op.f('ix_invites_id'), 'invites', ['id'], unique=False)
    op.create_index(op.f('ix_invites_email'), 'invites', ['email'], unique=False)
    op.create_index(op.f('ix_invites_role_id'), 'invites', ['role_id'], unique=False)
    op.create_index(op.f('ix_invites_scope_type'), 'invites', ['scope_type'], unique=False)
    op.create_index(op.f('ix_invites_scope_id'), 'invites', ['scope_id'], unique=False)
    op.create_index(op.f('ix_invites_token_hash'), 'invites', ['token_hash'], unique=True)
    op.create_index(op.f('ix_invites_status'), 'invites', ['status'], unique=False)
    op.create_index('idx_invite_email_status', 'invites', ['email', 'status'], unique=False)
    op.create_index('idx_invite_scope', 'invites', ['scope_type', 'scope_id'], unique=False)
    
    # Add active_membership_id to refresh_tokens table
    op.add_column('refresh_tokens', sa.Column('active_membership_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key('fk_refresh_tokens_active_membership', 'refresh_tokens', 'user_memberships', ['active_membership_id'], ['id'], ondelete='SET NULL')
    op.create_index(op.f('ix_refresh_tokens_active_membership_id'), 'refresh_tokens', ['active_membership_id'], unique=False)


def downgrade() -> None:
    # Remove active_membership_id from refresh_tokens
    op.drop_index(op.f('ix_refresh_tokens_active_membership_id'), table_name='refresh_tokens')
    op.drop_constraint('fk_refresh_tokens_active_membership', 'refresh_tokens', type_='foreignkey')
    op.drop_column('refresh_tokens', 'active_membership_id')
    
    # Drop invites table
    op.drop_index('idx_invite_scope', table_name='invites')
    op.drop_index('idx_invite_email_status', table_name='invites')
    op.drop_index(op.f('ix_invites_status'), table_name='invites')
    op.drop_index(op.f('ix_invites_token_hash'), table_name='invites')
    op.drop_index(op.f('ix_invites_scope_id'), table_name='invites')
    op.drop_index(op.f('ix_invites_scope_type'), table_name='invites')
    op.drop_index(op.f('ix_invites_role_id'), table_name='invites')
    op.drop_index(op.f('ix_invites_email'), table_name='invites')
    op.drop_index(op.f('ix_invites_id'), table_name='invites')
    op.drop_table('invites')
    
    # Drop user_memberships table
    op.drop_index('idx_user_membership_active', table_name='user_memberships')
    op.drop_index('idx_user_membership_scope', table_name='user_memberships')
    op.drop_index(op.f('ix_user_memberships_role_id'), table_name='user_memberships')
    op.drop_index(op.f('ix_user_memberships_scope_id'), table_name='user_memberships')
    op.drop_index(op.f('ix_user_memberships_scope_type'), table_name='user_memberships')
    op.drop_index(op.f('ix_user_memberships_user_id'), table_name='user_memberships')
    op.drop_index(op.f('ix_user_memberships_id'), table_name='user_memberships')
    op.drop_table('user_memberships')
    
    # Drop personal_workspaces table
    op.drop_index(op.f('ix_personal_workspaces_user_id'), table_name='personal_workspaces')
    op.drop_index(op.f('ix_personal_workspaces_id'), table_name='personal_workspaces')
    op.drop_table('personal_workspaces')
    
    # Drop institutions table
    op.drop_index(op.f('ix_institutions_slug'), table_name='institutions')
    op.drop_index(op.f('ix_institutions_organization_id'), table_name='institutions')
    op.drop_index(op.f('ix_institutions_id'), table_name='institutions')
    op.drop_table('institutions')
    
    # Note: We don't remove enum values as PostgreSQL doesn't support removing enum values easily
    # The enums will remain but unused
