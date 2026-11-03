"""blitz speed bonus: a quiz's «Блиц» flag and bonus numbers, and when the server sent and got each question

Revision ID: 0016
Revises: 0015
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0016'
down_revision = '0015'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # «Блиц», «Бонус за скорость» (max per question), «Без потерь, сек» and «Время бонуса, сек»; blank = 20 / 3 / 12
    op.add_column('tasks', sa.Column('blitz', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('tasks', sa.Column('speed_bonus', sa.Integer(), server_default=sa.text('20'), nullable=False))
    op.add_column('tasks', sa.Column('grace_seconds', sa.Integer(), server_default=sa.text('3'), nullable=False))
    op.add_column('tasks', sa.Column('bonus_seconds', sa.Integer(), server_default=sa.text('12'), nullable=False))
    # {"question number": {"sent": first sent, "got": answer received}}, from the server clock
    op.add_column('quiz_attempts', sa.Column('times', postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"),
                                             nullable=False))
    # The stage running at «Начать»: the speed bonus row is stored on it
    op.add_column('quiz_attempts', sa.Column('stage_id', sa.Integer(),
                                             sa.ForeignKey('stages.id', ondelete='SET NULL'), nullable=True))


def downgrade() -> None:
    op.drop_column('quiz_attempts', 'stage_id')
    op.drop_column('quiz_attempts', 'times')
    op.drop_column('tasks', 'bonus_seconds')
    op.drop_column('tasks', 'grace_seconds')
    op.drop_column('tasks', 'speed_bonus')
    op.drop_column('tasks', 'blitz')
