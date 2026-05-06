"""Create template models

Revision ID: 001_create_template_models
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_create_template_models'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enums using raw SQL to avoid conflicts
    op.execute("DO $$ BEGIN CREATE TYPE templatecategory AS ENUM ('lesson_design', 'assessment', 'behavior', 'subject_specific', 'communication'); EXCEPTION WHEN duplicate_object THEN null; END $$;")
    op.execute("DO $$ BEGIN CREATE TYPE templateversionstatus AS ENUM ('draft', 'published', 'archived'); EXCEPTION WHEN duplicate_object THEN null; END $$;")
    
    # Create enum objects for use in table definitions (create_type=False prevents SQLAlchemy from trying to create them)
    template_category_enum = postgresql.ENUM('lesson_design', 'assessment', 'behavior', 'subject_specific', 'communication', name='templatecategory', create_type=False)
    template_version_status_enum = postgresql.ENUM('draft', 'published', 'archived', name='templateversionstatus', create_type=False)
    
    # Create templates table
    op.create_table(
        'templates',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('slug', sa.String(length=100), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', template_category_enum, nullable=False),
        sa.Column('subject_default', sa.String(length=50), nullable=True),
        sa.Column('grade_bands_supported', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('is_system_template', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index(op.f('ix_templates_id'), 'templates', ['id'], unique=False)
    op.create_index(op.f('ix_templates_slug'), 'templates', ['slug'], unique=True)

    # Create template_versions table
    op.create_table(
        'template_versions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('template_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('status', template_version_status_enum, nullable=False, server_default='draft'),
        sa.Column('input_schema', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('output_schema', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('prompt_definition', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('model_config', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('published_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['template_id'], ['templates.id'], ondelete='CASCADE'),
    )
    op.create_index(op.f('ix_template_versions_id'), 'template_versions', ['id'], unique=False)
    op.create_index(op.f('ix_template_versions_template_id'), 'template_versions', ['template_id'], unique=False)
    op.create_unique_constraint('uq_template_version', 'template_versions', ['template_id', 'version'])

    # Create template_executions table
    op.create_table(
        'template_executions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('template_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('template_version_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('template_version', sa.Integer(), nullable=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('input_data', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('output_data', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('model_used', sa.String(length=100), nullable=True),
        sa.Column('provider_used', sa.String(length=50), nullable=True),
        sa.Column('token_usage', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('cost_estimate', sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('cache_hit', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('alignment_flags', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['template_id'], ['templates.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['template_version_id'], ['template_versions.id'], ondelete='SET NULL'),
    )
    op.create_index(op.f('ix_template_executions_id'), 'template_executions', ['id'], unique=False)
    op.create_index(op.f('ix_template_executions_template_id'), 'template_executions', ['template_id'], unique=False)
    op.create_index(op.f('ix_template_executions_template_version_id'), 'template_executions', ['template_version_id'], unique=False)
    op.create_index(op.f('ix_template_executions_user_id'), 'template_executions', ['user_id'], unique=False)
    op.create_index(op.f('ix_template_executions_tenant_id'), 'template_executions', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_template_executions_created_at'), 'template_executions', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_template_executions_created_at'), table_name='template_executions')
    op.drop_index(op.f('ix_template_executions_tenant_id'), table_name='template_executions')
    op.drop_index(op.f('ix_template_executions_user_id'), table_name='template_executions')
    op.drop_index(op.f('ix_template_executions_template_version_id'), table_name='template_executions')
    op.drop_index(op.f('ix_template_executions_template_id'), table_name='template_executions')
    op.drop_index(op.f('ix_template_executions_id'), table_name='template_executions')
    op.drop_table('template_executions')
    
    op.drop_constraint('uq_template_version', 'template_versions', type_='unique')
    op.drop_index(op.f('ix_template_versions_template_id'), table_name='template_versions')
    op.drop_index(op.f('ix_template_versions_id'), table_name='template_versions')
    op.drop_table('template_versions')
    
    op.drop_index(op.f('ix_templates_slug'), table_name='templates')
    op.drop_index(op.f('ix_templates_id'), table_name='templates')
    op.drop_table('templates')
    
    # Drop enums
    op.execute("DROP TYPE IF EXISTS templateversionstatus")
    op.execute("DROP TYPE IF EXISTS templatecategory")

