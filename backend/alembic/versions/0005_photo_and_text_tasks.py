"""photo and text tasks

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa


revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column('tasks', 'method', type_=sa.String(length=16), existing_type=sa.String(length=8),
                    existing_nullable=False, existing_server_default='')
    op.create_table(
        'submissions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('guest_id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('photo', sa.LargeBinary(), nullable=True),
        sa.Column('text', sa.Text(), server_default='', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['guest_id'], ['guests.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('guest_id', 'task_id'),
    )


def downgrade() -> None:
    op.drop_table('submissions')
    # «Фото+текст» doesn't fit the old width; those tasks go back to not doable yet
    op.execute("UPDATE tasks SET method = '' WHERE method IN ('photo', 'text', 'photo_text')")
    op.alter_column('tasks', 'method', type_=sa.String(length=8), existing_type=sa.String(length=16),
                    existing_nullable=False, existing_server_default='')
