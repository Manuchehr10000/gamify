"""qr and link tasks

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa


revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('score_events', sa.Column('coins', sa.Integer(), server_default='0', nullable=False))
    op.add_column('tasks', sa.Column('method', sa.String(length=8), server_default='', nullable=False))
    op.add_column('tasks', sa.Column('link', sa.Text(), server_default='', nullable=False))
    op.add_column('tasks', sa.Column('qr_code', sa.String(length=16), nullable=True))
    op.create_unique_constraint('tasks_qr_code_key', 'tasks', ['qr_code'])


def downgrade() -> None:
    op.drop_constraint('tasks_qr_code_key', 'tasks', type_='unique')
    op.drop_column('tasks', 'qr_code')
    op.drop_column('tasks', 'link')
    op.drop_column('tasks', 'method')
    op.drop_column('score_events', 'coins')
