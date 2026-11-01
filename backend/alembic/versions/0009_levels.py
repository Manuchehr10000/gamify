"""levels and profile

Revision ID: 0009
Revises: 0008
"""
from alembic import op
import sqlalchemy as sa


revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None

# TAG's starting levels (the rules, section 3.3); the admin changes them in the file's «Уровни» sheet
TAG_LEVELS = [("Новичок форума", 0), ("Участник", 50), ("Актив", 150), ("Эксперт форума", 300), ("Легенда MF", 500)]


def upgrade() -> None:
    levels = op.create_table(
        'levels',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('min_points', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('min_points'),
    )
    op.bulk_insert(levels, [{"name": name, "min_points": points} for name, points in TAG_LEVELS])
    op.add_column('guests', sa.Column('level_shown', sa.Integer(), server_default=sa.text('0'), nullable=False))
    # Guests who already hold points start at the level they have, so no moment shows for a level they didn't cross
    op.execute("""
        UPDATE guests SET level_shown = COALESCE((
            SELECT MAX(l.min_points) FROM levels l
            WHERE l.min_points <= (SELECT COALESCE(SUM(e.points), 0) FROM score_events e WHERE e.guest_id = guests.id)
        ), 0)
    """)


def downgrade() -> None:
    op.drop_column('guests', 'level_shown')
    op.drop_table('levels')
