"""create_subscription_models

Revision ID: 7572e12d1331
Revises: cb7fc7887327
Create Date: 2025-01-15 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '7572e12d1331'
down_revision: Union[str, None] = 'cb7fc7887327'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Subscription tiers table
    op.create_table(
        'subscription_tiers',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tier_key', sa.String(length=50), nullable=False),
        sa.Column('tier_name', sa.String(length=200), nullable=False),
        sa.Column('tier_description', sa.Text(), nullable=True),
        sa.Column('hierarchy_level', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('price_monthly', sa.Numeric(10, 2), nullable=True),
        sa.Column('price_yearly', sa.Numeric(10, 2), nullable=True),
        sa.Column('currency', sa.String(length=3), nullable=True, server_default='USD'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_public', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('metadata', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tier_key')
    )
    op.create_index(op.f('ix_subscription_tiers_id'), 'subscription_tiers', ['id'], unique=False)
    op.create_index(op.f('ix_subscription_tiers_tier_key'), 'subscription_tiers', ['tier_key'], unique=True)
    op.create_index(op.f('ix_subscription_tiers_hierarchy_level'), 'subscription_tiers', ['hierarchy_level'], unique=False)

    # Subscription tier features table
    op.create_table(
        'subscription_tier_features',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tier', sa.String(length=20), nullable=False),
        sa.Column('feature_key', sa.String(length=100), nullable=False),
        sa.Column('feature_name', sa.String(length=200), nullable=False),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('limit_value', sa.Integer(), nullable=True),
        sa.Column('limit_period', sa.String(length=20), nullable=True),
        sa.Column('metadata', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['tier'], ['subscription_tiers.tier_key'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tier', 'feature_key', name='uq_tier_feature')
    )
    op.create_index(op.f('ix_subscription_tier_features_id'), 'subscription_tier_features', ['id'], unique=False)
    op.create_index(op.f('ix_subscription_tier_features_tier'), 'subscription_tier_features', ['tier'], unique=False)
    op.create_index(op.f('ix_subscription_tier_features_feature_key'), 'subscription_tier_features', ['feature_key'], unique=False)

    # User subscriptions table
    op.create_table(
        'user_subscriptions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tier', sa.String(length=20), nullable=False, server_default='free'),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='active'),
        sa.Column('trial_started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('trial_ends_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_trial', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('current_period_start', sa.DateTime(timezone=True), nullable=True),
        sa.Column('current_period_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('payment_provider', sa.String(length=50), nullable=True),
        sa.Column('payment_customer_id', sa.String(length=200), nullable=True),
        sa.Column('payment_subscription_id', sa.String(length=200), nullable=True),
        sa.Column('is_manually_granted', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('granted_by_user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('granted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('grant_reason', sa.Text(), nullable=True),
        sa.Column('metadata', postgresql.JSONB(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['granted_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tier'], ['subscription_tiers.tier_key'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
    )
    op.create_index(op.f('ix_user_subscriptions_id'), 'user_subscriptions', ['id'], unique=False)
    op.create_index(op.f('ix_user_subscriptions_user_id'), 'user_subscriptions', ['user_id'], unique=True)
    op.create_index(op.f('ix_user_subscriptions_tier'), 'user_subscriptions', ['tier'], unique=False)
    op.create_index(op.f('ix_user_subscriptions_status'), 'user_subscriptions', ['status'], unique=False)
    op.create_index('idx_user_tier', 'user_subscriptions', ['user_id', 'tier'], unique=False)
    op.create_index('idx_tier_status', 'user_subscriptions', ['tier', 'status'], unique=False)

    # Subscription history table
    op.create_table(
        'subscription_history',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('subscription_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('from_tier', sa.String(length=20), nullable=True),
        sa.Column('to_tier', sa.String(length=20), nullable=True),
        sa.Column('changed_by_user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('metadata', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['subscription_id'], ['user_subscriptions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['changed_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_subscription_history_id'), 'subscription_history', ['id'], unique=False)
    op.create_index('idx_user_history', 'subscription_history', ['user_id', sa.text('created_at DESC')], unique=False)

    # User usage quotas table
    op.create_table(
        'user_usage_quotas',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('subscription_tier', sa.String(length=20), nullable=False),
        sa.Column('daily_messages_limit', sa.Integer(), nullable=False, server_default='20'),
        sa.Column('daily_messages_used', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('daily_reset_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('monthly_messages_limit', sa.Integer(), nullable=False, server_default='500'),
        sa.Column('monthly_messages_used', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('monthly_reset_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('requests_per_minute', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('requests_per_hour', sa.Integer(), nullable=False, server_default='50'),
        sa.Column('last_request_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('request_window_start', sa.DateTime(timezone=True), nullable=True),
        sa.Column('request_count_in_window', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('features', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['subscription_tier'], ['subscription_tiers.tier_key'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'subscription_tier', name='uq_user_tier')
    )
    op.create_index(op.f('ix_user_usage_quotas_id'), 'user_usage_quotas', ['id'], unique=False)
    # Create index only if it doesn't exist
    from sqlalchemy import inspect, Index
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_indexes = [idx['name'] for idx in inspector.get_indexes('user_usage_quotas')]
    if 'idx_user_tier' not in existing_indexes:
        op.create_index('idx_user_tier', 'user_usage_quotas', ['user_id', 'subscription_tier'], unique=False, if_not_exists=True)

    # User usage logs table
    op.create_table(
        'user_usage_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('feature_key', sa.String(length=100), nullable=True),
        sa.Column('tokens_used', sa.Integer(), nullable=True),
        sa.Column('cost_estimate', sa.Numeric(10, 6), nullable=True),
        sa.Column('model_used', sa.String(length=100), nullable=True),
        sa.Column('provider_used', sa.String(length=50), nullable=True),
        sa.Column('metadata', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_usage_logs_id'), 'user_usage_logs', ['id'], unique=False)
    op.create_index('idx_user_date', 'user_usage_logs', ['user_id', sa.text('created_at DESC')], unique=False)
    op.create_index('idx_action_date', 'user_usage_logs', ['action', sa.text('created_at DESC')], unique=False)


def downgrade() -> None:
    op.drop_index('idx_action_date', table_name='user_usage_logs')
    op.drop_index('idx_user_date', table_name='user_usage_logs')
    op.drop_index(op.f('ix_user_usage_logs_id'), table_name='user_usage_logs')
    op.drop_table('user_usage_logs')
    
    op.drop_index('idx_user_tier', table_name='user_usage_quotas')
    op.drop_index(op.f('ix_user_usage_quotas_id'), table_name='user_usage_quotas')
    op.drop_table('user_usage_quotas')
    
    op.drop_index('idx_user_history', table_name='subscription_history')
    op.drop_index(op.f('ix_subscription_history_id'), table_name='subscription_history')
    op.drop_table('subscription_history')
    
    op.drop_index('idx_tier_status', table_name='user_subscriptions')
    op.drop_index('idx_user_tier', table_name='user_subscriptions')
    op.drop_index(op.f('ix_user_subscriptions_status'), table_name='user_subscriptions')
    op.drop_index(op.f('ix_user_subscriptions_tier'), table_name='user_subscriptions')
    op.drop_index(op.f('ix_user_subscriptions_user_id'), table_name='user_subscriptions')
    op.drop_index(op.f('ix_user_subscriptions_id'), table_name='user_subscriptions')
    op.drop_table('user_subscriptions')
    
    op.drop_index(op.f('ix_subscription_tier_features_feature_key'), table_name='subscription_tier_features')
    op.drop_index(op.f('ix_subscription_tier_features_tier'), table_name='subscription_tier_features')
    op.drop_index(op.f('ix_subscription_tier_features_id'), table_name='subscription_tier_features')
    op.drop_table('subscription_tier_features')
    
    op.drop_index(op.f('ix_subscription_tiers_hierarchy_level'), table_name='subscription_tiers')
    op.drop_index(op.f('ix_subscription_tiers_tier_key'), table_name='subscription_tiers')
    op.drop_index(op.f('ix_subscription_tiers_id'), table_name='subscription_tiers')
    op.drop_table('subscription_tiers')
