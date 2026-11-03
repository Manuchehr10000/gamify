"""badges set by admin: the badge list with its rules, and what badge_awards now records

Revision ID: 0019
Revises: 0018
"""
from alembic import op
import sqlalchemy as sa

revision = '0019'
down_revision = '0018'
branch_labels = None
depends_on = None

# TAG's five badges (rules 3.3), with 011's codes so the awards guests hold carry over: the client's configuration
TAG_BADGES = [
    {'code': 'photo_hunter', 'name': 'Фотоохотник', 'rule': 'tasks', 'count': 5, 'kinds': 'Фото, Фото+текст',
     'any_partner': False},
    {'code': 'networker', 'name': 'Нетворкер', 'rule': 'all_of_type', 'count': None, 'kinds': 'Нетворкинг',
     'any_partner': False},
    {'code': 'erudite', 'name': 'Эрудит', 'rule': 'quiz_streak', 'count': 5, 'kinds': '', 'any_partner': False},
    {'code': 'brand_friend', 'name': 'Друг бренда', 'rule': 'tasks', 'count': 3, 'kinds': '', 'any_partner': True},
    {'code': 'forum_spirit', 'name': 'Дух форума', 'rule': 'bonuses', 'count': 1, 'kinds': 'Крейзи',
     'any_partner': False},
]


def upgrade() -> None:
    badges = op.create_table(
        'badges',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('code', sa.String(32), nullable=False, unique=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('rule', sa.String(16), nullable=False),
        sa.Column('count', sa.Integer()),
        sa.Column('kinds', sa.String(200), server_default='', nullable=False),
        sa.Column('partner_id', sa.Integer(), sa.ForeignKey('partners.id')),
        sa.Column('any_partner', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('task_id', sa.Integer(), sa.ForeignKey('tasks.id')),
        sa.Column('coins', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('on_screen', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('position', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('version', sa.Integer(), server_default='1', nullable=False),
    )
    op.bulk_insert(badges, [{**b, 'position': n} for n, b in enumerate(TAG_BADGES)])
    # The awards held so far were already seen; from now on a row is added unseen and the feed marks it
    op.add_column('badge_awards', sa.Column('seen', sa.Boolean(), server_default=sa.text('true'), nullable=False))
    op.alter_column('badge_awards', 'seen', server_default=sa.text('false'))
    op.add_column('badge_awards', sa.Column('announce', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('badge_awards', sa.Column('shown_at', sa.DateTime(timezone=True)))
    op.create_foreign_key('badge_awards_badge_fkey', 'badge_awards', 'badges', ['badge'], ['code'])


def downgrade() -> None:
    op.drop_constraint('badge_awards_badge_fkey', 'badge_awards', type_='foreignkey')
    op.drop_column('badge_awards', 'shown_at')
    op.drop_column('badge_awards', 'announce')
    op.drop_column('badge_awards', 'seen')
    op.drop_table('badges')
