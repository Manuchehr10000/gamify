"""moderation queue

Revision ID: 0006
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa


revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('sessions', sa.Column('staff_name', sa.String(length=100), server_default='', nullable=False))
    op.add_column('submissions', sa.Column('status', sa.String(length=16), server_default='', nullable=False))
    op.add_column('submissions', sa.Column('moderator', sa.String(length=100), server_default='', nullable=False))
    op.add_column('submissions', sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('submissions', sa.Column('upload', sa.String(length=64), server_default='', nullable=False))
    # A submission sent back for a retake stays as the log; the guest's new one takes its place
    op.drop_constraint('submissions_guest_id_task_id_key', 'submissions', type_='unique')
    op.create_index('submissions_guest_task', 'submissions', ['guest_id', 'task_id'], unique=True,
                    postgresql_where=sa.text("status <> 'retake'"))
    op.create_index('submissions_unchecked', 'submissions', ['created_at'], postgresql_where=sa.text("status = ''"))


def downgrade() -> None:
    op.drop_index('submissions_unchecked', table_name='submissions')
    op.drop_index('submissions_guest_task', table_name='submissions')
    # Only the last submission per task can come back under the old one-per-task rule
    op.execute("DELETE FROM submissions WHERE status = 'retake'")
    op.create_unique_constraint('submissions_guest_id_task_id_key', 'submissions', ['guest_id', 'task_id'])
    op.drop_column('submissions', 'upload')
    op.drop_column('submissions', 'decided_at')
    op.drop_column('submissions', 'moderator')
    op.drop_column('submissions', 'status')
    op.drop_column('sessions', 'staff_name')
