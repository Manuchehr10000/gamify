"""quizzes with a timer

Revision ID: 0008
Revises: 0007
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('tasks', sa.Column('timer_seconds', sa.Integer(), nullable=True))
    op.add_column('tasks', sa.Column('requires_task_id', sa.Integer(), sa.ForeignKey('tasks.id'), nullable=True))
    op.create_table(
        'questions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('option1', sa.Text(), nullable=False),
        sa.Column('option2', sa.Text(), nullable=False),
        sa.Column('option3', sa.Text(), nullable=True),
        sa.Column('option4', sa.Text(), nullable=True),
        sa.Column('correct', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('task_id', 'number'),
    )
    op.create_table(
        'quiz_attempts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('guest_id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('answers', postgresql.JSONB(), nullable=False),
        sa.Column('correct', sa.Integer(), nullable=True),
        sa.Column('total', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['guest_id'], ['guests.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('guest_id', 'task_id'),
    )


def downgrade() -> None:
    op.drop_table('quiz_attempts')
    op.drop_table('questions')
    op.drop_column('tasks', 'requires_task_id')
    op.drop_column('tasks', 'timer_seconds')
    # «Квиз» doesn't exist before this revision; those tasks go back to not doable yet
    op.execute("UPDATE tasks SET method = '' WHERE method = 'quiz'")
