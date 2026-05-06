"""create_credit_system_tables

Revision ID: a9b8c7d6e5f4
Revises: 7572e12d1331
Create Date: 2025-05-02 10:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'a9b8c7d6e5f4'
down_revision: Union[str, None] = '7572e12d1331'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # feature_credit_costs — cost config per feature key
    op.create_table(
        'feature_credit_costs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('feature_key', sa.String(100), nullable=False, unique=True),
        sa.Column('display_name', sa.String(200), nullable=False),
        sa.Column('module_name', sa.String(100), nullable=False),
        sa.Column('base_credits', sa.Integer(), nullable=False, default=1),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
    )
    op.create_index('idx_feature_cost_key', 'feature_credit_costs', ['feature_key'])

    # access_codes — activation codes (beta + staff)
    op.create_table(
        'access_codes',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('code', sa.String(50), nullable=False, unique=True),
        sa.Column('code_type', sa.String(20), nullable=False),  # 'beta' | 'staff'
        sa.Column('credit_allocation', sa.Integer(), nullable=False),
        sa.Column('validity_days', sa.Integer(), nullable=False, default=30),
        sa.Column('max_uses', sa.Integer(), nullable=True),  # null = unlimited
        sa.Column('times_used', sa.Integer(), nullable=False, default=0),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('auto_renew', sa.Boolean(), nullable=False, default=False),
        sa.Column('auto_renew_threshold_pct', sa.Integer(), nullable=True, default=20),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('idx_access_code', 'access_codes', ['code'])

    # user_code_redemptions — record of every activation
    op.create_table(
        'user_code_redemptions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('access_code_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('access_codes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('redeemed_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('credit_allocation', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('auto_renew', sa.Boolean(), nullable=False, default=False),
        sa.Column('last_renewed_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('idx_redemption_user', 'user_code_redemptions', ['user_id'])
    op.create_index('idx_redemption_active', 'user_code_redemptions', ['user_id', 'is_active'])

    # user_token_balances — the user's live credit wallet
    op.create_table(
        'user_token_balances',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('balance', sa.Integer(), nullable=False, default=0),
        sa.Column('total_allocated', sa.Integer(), nullable=False, default=0),
        sa.Column('total_spent', sa.Integer(), nullable=False, default=0),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('auto_renew', sa.Boolean(), nullable=False, default=False),
        sa.Column('subscription_started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_topped_up_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
    )
    op.create_index('idx_balance_user', 'user_token_balances', ['user_id'])

    # user_credit_transactions — append-only ledger
    op.create_table(
        'user_credit_transactions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('type', sa.String(20), nullable=False),  # 'debit' | 'credit' | 'renewal' | 'expiry_adjustment'
        sa.Column('amount', sa.Integer(), nullable=False),  # positive = credit, negative = debit
        sa.Column('balance_after', sa.Integer(), nullable=False),
        sa.Column('feature_key', sa.String(100), nullable=True),
        sa.Column('description', sa.String(500), nullable=True),
        sa.Column('reference_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('model_used', sa.String(100), nullable=True),
        sa.Column('input_tokens', sa.Integer(), nullable=True),
        sa.Column('output_tokens', sa.Integer(), nullable=True),
        sa.Column('usd_cost', sa.Numeric(10, 6), nullable=True),
        sa.Column('metadata', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
    )
    op.create_index('idx_txn_user_date', 'user_credit_transactions', ['user_id', 'created_at'])
    op.create_index('idx_txn_feature', 'user_credit_transactions', ['user_id', 'feature_key'])

    # Seed feature_credit_costs with default values
    op.execute("""
        INSERT INTO feature_credit_costs (id, feature_key, display_name, module_name, base_credits, description, is_active)
        VALUES
            (gen_random_uuid(), 'chatbot_message',         'AI Chat Message',       'AI Chatbots',      2,  'Each message sent to an AI chatbot', true),
            (gen_random_uuid(), 'chatbot_message_search',  'AI Chat + Web Search',  'AI Chatbots',      4,  'Chat message with web search enabled', true),
            (gen_random_uuid(), 'template_generate',       'Template Generation',   'Templates',        8,  'Generate a worksheet or lesson template', true),
            (gen_random_uuid(), 'quiz_generate',           'Quiz Creation',         'Teacher Tools',    10, 'Generate a quiz from content', true),
            (gen_random_uuid(), 'youtube_analyze',         'YouTube Analysis',      'Teacher Tools',    8,  'Analyze or transcribe a YouTube video', true),
            (gen_random_uuid(), 'pixgen_image',            'AI Image Generation',   'PixGen',           20, 'Generate an AI image', true),
            (gen_random_uuid(), 'content_gap_fill',        'Content Generation',    'Content Factory',  6,  'Generate gap-fill or content items', true),
            (gen_random_uuid(), 'document_ocr',            'Document Processing',   'Documents',        3,  'Process and extract text from a document', true),
            (gen_random_uuid(), 'assignment_generate',     'Assignment Creation',   'Teacher Tools',    10, 'Generate a full assignment with rubric', true),
            (gen_random_uuid(), 'worksheet_generate',      'Worksheet Generation',  'Teacher Tools',    8,  'Generate a custom worksheet', true)
    """)


def downgrade() -> None:
    op.drop_table('user_credit_transactions')
    op.drop_table('user_token_balances')
    op.drop_table('user_code_redemptions')
    op.drop_table('access_codes')
    op.drop_table('feature_credit_costs')
