"""push notifications: the phones' subscriptions, the push schedule with its counts, and text settings

Revision ID: 0018
Revises: 0017
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0018'
down_revision = '0017'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # One row per phone that said yes; the push service's «gone» switches it off
    op.create_table(
        'push_subscriptions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('key', sa.String(32), nullable=False, unique=True),
        sa.Column('guest_id', sa.Integer(), sa.ForeignKey('guests.id', ondelete='CASCADE'), nullable=False),
        sa.Column('endpoint', sa.Text(), nullable=False, unique=True),
        sa.Column('p256dh', sa.String(200), nullable=False),
        sa.Column('auth', sa.String(100), nullable=False),
        sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    # The schedule: one row per source (a stage start, a quiz window, the market) or per one-off message
    op.create_table(
        'push_messages',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('kind', sa.String(16), nullable=False),
        sa.Column('source', sa.String(32), unique=True),
        sa.Column('task_id', sa.Integer(), sa.ForeignKey('tasks.id', ondelete='SET NULL')),
        sa.Column('source_at', sa.DateTime(timezone=True)),
        sa.Column('shift_seconds', sa.Integer(), server_default='0', nullable=False),
        sa.Column('at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('text', sa.Text(), server_default='', nullable=False),
        sa.Column('text_tg', sa.Text(), server_default='', nullable=False),
        sa.Column('title_tg', sa.String(200), server_default='', nullable=False),
        sa.Column('text_edited', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('state', sa.String(16), server_default='planned', nullable=False),
        sa.Column('shown_at', sa.DateTime(timezone=True)),
        sa.Column('sends', sa.Integer(), server_default='0', nullable=False),
        sa.Column('deliveries', sa.Integer(), server_default='0', nullable=False),
        sa.Column('failures', sa.Integer(), server_default='0', nullable=False),
        sa.Column('counted_subscriptions', postgresql.ARRAY(sa.Integer()), server_default='{}', nullable=False),
        sa.Column('version', sa.Integer(), server_default='1', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('push_messages_state_at', 'push_messages', ['state', 'at'])
    op.create_index('push_messages_shown_at', 'push_messages', ['shown_at'])
    # A text setting (the push texts) keeps its value here; numeric settings leave it empty
    op.add_column('settings', sa.Column('text_value', sa.Text()))


def downgrade() -> None:
    op.drop_column('settings', 'text_value')
    op.drop_index('push_messages_shown_at', 'push_messages')
    op.drop_index('push_messages_state_at', 'push_messages')
    op.drop_table('push_messages')
    op.drop_table('push_subscriptions')
