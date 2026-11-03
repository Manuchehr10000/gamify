"""stage multipliers: each stage's points multiplier, kept on claims and quiz attempts from when the action began

Revision ID: 0015
Revises: 0014
"""
from alembic import op
import sqlalchemy as sa

revision = '0015'
down_revision = '0014'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # «Множитель»: 1 to 5 in steps of 0.5; it multiplies the points of the stage's task awards
    op.add_column('stages', sa.Column('multiplier', sa.Numeric(5, 2), server_default=sa.text('1'), nullable=False))
    # The stage's multiplier at the claim and at «Начать»: a later change doesn't touch them
    op.add_column('claims', sa.Column('multiplier', sa.Numeric(5, 2), server_default=sa.text('1'), nullable=False))
    op.add_column('quiz_attempts',
                  sa.Column('multiplier', sa.Numeric(5, 2), server_default=sa.text('1'), nullable=False))


def downgrade() -> None:
    op.drop_column('quiz_attempts', 'multiplier')
    op.drop_column('claims', 'multiplier')
    op.drop_column('stages', 'multiplier')
