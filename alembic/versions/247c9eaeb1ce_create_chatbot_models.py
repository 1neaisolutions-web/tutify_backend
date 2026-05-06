"""create_chatbot_models

Revision ID: 247c9eaeb1ce
Revises: 7572e12d1331
Create Date: 2025-01-15 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '247c9eaeb1ce'
down_revision: Union[str, None] = '7572e12d1331'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Chatbots table
    op.create_table(
        'chatbots',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('slug', sa.String(length=100), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', sa.String(length=50), nullable=True),
        sa.Column('subject', sa.String(length=50), nullable=True),
        sa.Column('access_level', sa.String(length=20), nullable=False),
        sa.Column('system_prompt', sa.Text(), nullable=True),
        sa.Column('model_config', postgresql.JSONB(), nullable=True),
        sa.Column('fallback_models', postgresql.JSONB(), nullable=True),
        sa.Column('model_strategy', sa.String(length=50), nullable=True, server_default='primary_fallback'),
        sa.Column('premium_features', postgresql.JSONB(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug')
    )
    op.create_index(op.f('ix_chatbots_id'), 'chatbots', ['id'], unique=False)
    op.create_index(op.f('ix_chatbots_slug'), 'chatbots', ['slug'], unique=True)
    op.create_index(op.f('ix_chatbots_access_level'), 'chatbots', ['access_level'], unique=False)
    op.create_index(op.f('ix_chatbots_category'), 'chatbots', ['category'], unique=False)

    # Chatbot model assignments table
    op.create_table(
        'chatbot_model_assignments',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('chatbot_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('provider', sa.String(length=50), nullable=False),
        sa.Column('model_name', sa.String(length=100), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('temperature', sa.Numeric(3, 2), nullable=True, server_default='0.7'),
        sa.Column('max_tokens', sa.Integer(), nullable=True, server_default='2000'),
        sa.Column('top_p', sa.Numeric(3, 2), nullable=True),
        sa.Column('frequency_penalty', sa.Numeric(3, 2), nullable=True),
        sa.Column('presence_penalty', sa.Numeric(3, 2), nullable=True),
        sa.Column('max_tokens_per_request', sa.Integer(), nullable=True),
        sa.Column('rate_limit_per_minute', sa.Integer(), nullable=True),
        sa.Column('is_primary', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('metadata', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['chatbot_id'], ['chatbots.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('chatbot_id', 'provider', 'model_name', name='uq_chatbot_provider_model')
    )
    op.create_index(op.f('ix_chatbot_model_assignments_id'), 'chatbot_model_assignments', ['id'], unique=False)
    op.create_index('idx_chatbot_priority', 'chatbot_model_assignments', ['chatbot_id', 'priority', 'is_enabled'], unique=False)

    # Chatbot capabilities table
    op.create_table(
        'chatbot_capabilities',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('chatbot_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('capability_key', sa.String(length=100), nullable=False),
        sa.Column('capability_name', sa.String(length=200), nullable=False),
        sa.Column('capability_description', sa.Text(), nullable=True),
        sa.Column('capability_category', sa.String(length=50), nullable=True),
        sa.Column('icon_name', sa.String(length=50), nullable=True),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_primary', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('requires_input_type', sa.String(length=50), nullable=True),
        sa.Column('system_prompt_template', sa.Text(), nullable=True),
        sa.Column('output_schema', postgresql.JSONB(), nullable=True),
        sa.Column('processing_mode', sa.String(length=50), nullable=True, server_default='structured'),
        sa.Column('metadata', postgresql.JSONB(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['chatbot_id'], ['chatbots.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('chatbot_id', 'capability_key', name='uq_chatbot_capability')
    )
    op.create_index(op.f('ix_chatbot_capabilities_id'), 'chatbot_capabilities', ['id'], unique=False)
    op.create_index(op.f('ix_chatbot_capabilities_chatbot_id'), 'chatbot_capabilities', ['chatbot_id'], unique=False)

    # Chatbot conversations table
    op.create_table(
        'chatbot_conversations',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('chatbot_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('title', sa.String(length=200), nullable=True),
        sa.Column('metadata', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['chatbot_id'], ['chatbots.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_chatbot_conversations_id'), 'chatbot_conversations', ['id'], unique=False)
    op.create_index('idx_user_chatbot', 'chatbot_conversations', ['user_id', 'chatbot_id'], unique=False)
    op.create_index('idx_user_updated', 'chatbot_conversations', ['user_id', sa.text('updated_at DESC')], unique=False)

    # Chatbot messages table
    op.create_table(
        'chatbot_messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('metadata', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['conversation_id'], ['chatbot_conversations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_chatbot_messages_id'), 'chatbot_messages', ['id'], unique=False)
    op.create_index('idx_conversation', 'chatbot_messages', ['conversation_id', 'created_at'], unique=False)

    # Chatbot model usage table
    op.create_table(
        'chatbot_model_usage',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('chatbot_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('assignment_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('provider', sa.String(length=50), nullable=True),
        sa.Column('model_name', sa.String(length=100), nullable=True),
        sa.Column('tokens_used', sa.Integer(), nullable=True),
        sa.Column('cost_estimate', sa.Numeric(10, 6), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('success', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['chatbot_id'], ['chatbots.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['conversation_id'], ['chatbot_conversations.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['assignment_id'], ['chatbot_model_assignments.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_chatbot_model_usage_id'), 'chatbot_model_usage', ['id'], unique=False)
    op.create_index('idx_chatbot_usage', 'chatbot_model_usage', ['chatbot_id', sa.text('created_at DESC')], unique=False)
    op.create_index('idx_model_usage', 'chatbot_model_usage', ['provider', 'model_name', sa.text('created_at DESC')], unique=False)

    # User capability progress table
    op.create_table(
        'user_capability_progress',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('capability_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('times_used', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('mastery_level', sa.String(length=50), nullable=True),
        sa.Column('achievements', postgresql.JSONB(), nullable=True),
        sa.Column('preferred_settings', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['capability_id'], ['chatbot_capabilities.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'capability_id', name='uq_user_capability')
    )
    op.create_index(op.f('ix_user_capability_progress_id'), 'user_capability_progress', ['id'], unique=False)
    op.create_index('idx_user_capability', 'user_capability_progress', ['user_id', 'capability_id'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_user_capability', table_name='user_capability_progress')
    op.drop_index(op.f('ix_user_capability_progress_id'), table_name='user_capability_progress')
    op.drop_table('user_capability_progress')
    
    op.drop_index('idx_model_usage', table_name='chatbot_model_usage')
    op.drop_index('idx_chatbot_usage', table_name='chatbot_model_usage')
    op.drop_index(op.f('ix_chatbot_model_usage_id'), table_name='chatbot_model_usage')
    op.drop_table('chatbot_model_usage')
    
    op.drop_index('idx_conversation', table_name='chatbot_messages')
    op.drop_index(op.f('ix_chatbot_messages_id'), table_name='chatbot_messages')
    op.drop_table('chatbot_messages')
    
    op.drop_index('idx_user_updated', table_name='chatbot_conversations')
    op.drop_index('idx_user_chatbot', table_name='chatbot_conversations')
    op.drop_index(op.f('ix_chatbot_conversations_id'), table_name='chatbot_conversations')
    op.drop_table('chatbot_conversations')
    
    op.drop_index(op.f('ix_chatbot_capabilities_chatbot_id'), table_name='chatbot_capabilities')
    op.drop_index(op.f('ix_chatbot_capabilities_id'), table_name='chatbot_capabilities')
    op.drop_table('chatbot_capabilities')
    
    op.drop_index('idx_chatbot_priority', table_name='chatbot_model_assignments')
    op.drop_index(op.f('ix_chatbot_model_assignments_id'), table_name='chatbot_model_assignments')
    op.drop_table('chatbot_model_assignments')
    
    op.drop_index(op.f('ix_chatbots_category'), table_name='chatbots')
    op.drop_index(op.f('ix_chatbots_access_level'), table_name='chatbots')
    op.drop_index(op.f('ix_chatbots_slug'), table_name='chatbots')
    op.drop_index(op.f('ix_chatbots_id'), table_name='chatbots')
    op.drop_table('chatbots')
