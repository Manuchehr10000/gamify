"""hall screen: the screen's mode the staff switch, and the log of every logo the screen showed

Revision ID: 0017
Revises: 0016
"""
from alembic import op
import sqlalchemy as sa

revision = '0017'
down_revision = '0016'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # One row (id 1), added by the first switch; no row means «Авто»
    op.create_table(
        'hall_state',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('mode', sa.String(8), nullable=False),
        sa.Column('staff_name', sa.String(100), nullable=False),
        sa.Column('changed_at', sa.DateTime(timezone=True), nullable=False),
    )
    # For piece 21's partner report; a screen resending its queue after a timeout doesn't log a show twice
    op.create_table(
        'logo_shows',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('partner_id', sa.Integer(), sa.ForeignKey('partners.id', ondelete='CASCADE'), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('seconds', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('partner_id', 'started_at'),
    )


def downgrade() -> None:
    op.drop_table('logo_shows')
    op.drop_table('hall_state')
