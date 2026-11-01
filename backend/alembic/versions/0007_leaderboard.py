"""leaderboard and hall screen

Revision ID: 0007
Revises: 0006
"""
from alembic import op
import sqlalchemy as sa


revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('guests', sa.Column('in_rating', sa.Boolean(), server_default=sa.text('true'), nullable=False))
    op.add_column('guests', sa.Column('frozen_place', sa.Integer(), nullable=True))
    op.add_column('guests', sa.Column('frozen_points', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('guests', 'frozen_points')
    op.drop_column('guests', 'frozen_place')
    op.drop_column('guests', 'in_rating')
