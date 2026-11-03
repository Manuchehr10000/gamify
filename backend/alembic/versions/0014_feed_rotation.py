"""feed card states and rotation: task limits, batch size per stage, the guests' place in each stage's rotation

Revision ID: 0014
Revises: 0013
"""
from alembic import op
import sqlalchemy as sa

revision = '0014'
down_revision = '0013'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # «Лимит»: how many guests may do the task in all; empty = no limit
    op.add_column('tasks', sa.Column('limit', sa.Integer(), nullable=True))
    # «Карточек в ленте»: the cards a guest's feed shows at once in the stage
    op.add_column('stages', sa.Column('batch_size', sa.Integer(), server_default=sa.text('15'), nullable=False))
    # Per guest and stage: where the batch on screen starts, and the last rotating card shown (the next batch
    # starts after it)
    op.create_table(
        'feed_rotations',
        sa.Column('guest_id', sa.Integer(), nullable=False),
        sa.Column('stage_id', sa.Integer(), nullable=False),
        sa.Column('after_task_id', sa.Integer(), nullable=True),
        sa.Column('last_task_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['guest_id'], ['guests.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['stage_id'], ['stages.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['after_task_id'], ['tasks.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['last_task_id'], ['tasks.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('guest_id', 'stage_id'),
    )


def downgrade() -> None:
    op.drop_table('feed_rotations')
    op.drop_column('stages', 'batch_size')
    op.drop_column('tasks', 'limit')
