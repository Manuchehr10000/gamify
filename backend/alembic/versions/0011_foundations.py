"""foundations: ledger, partners, staff access, job runner

Revision ID: 0011
Revises: 0010
"""
from alembic import op
import sqlalchemy as sa

revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A partner whose tasks name two packages has no single package to keep: stop and name it, as an upload would
    conflicts = op.get_bind().scalars(sa.text(
        "SELECT partner_name FROM tasks WHERE partner_name <> '' AND partner_package <> '' "
        "GROUP BY partner_name HAVING count(DISTINCT partner_package) > 1 ORDER BY partner_name")).all()
    if conflicts:
        raise RuntimeError("У партнёра в заданиях разные пакеты, исправьте перед обновлением: " + ", ".join(conflicts))

    # Partners: built from the names already in tasks and prizes; the package comes from the tasks
    op.create_table(
        'partners',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('package', sa.String(length=16), server_default='', nullable=False),
        sa.Column('logo', sa.Text(), nullable=True),
        sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    op.execute("""
        INSERT INTO partners (name, package)
        SELECT name, max(package) FROM (
            SELECT partner_name AS name, partner_package AS package FROM tasks WHERE partner_name <> ''
            UNION ALL
            SELECT partner, '' FROM prizes WHERE partner <> ''
        ) named GROUP BY name
    """)
    op.add_column('tasks', sa.Column('partner_id', sa.Integer(), sa.ForeignKey('partners.id'), nullable=True))
    op.add_column('prizes', sa.Column('partner_id', sa.Integer(), sa.ForeignKey('partners.id'), nullable=True))
    op.execute("UPDATE tasks SET partner_id = p.id FROM partners p WHERE p.name = tasks.partner_name")
    op.execute("UPDATE prizes SET partner_id = p.id FROM partners p WHERE p.name = prizes.partner")
    op.alter_column('prizes', 'partner_id', nullable=False)
    op.drop_column('tasks', 'partner_name')
    op.drop_column('tasks', 'partner_package')
    op.drop_column('prizes', 'partner')

    # Staff accounts: app.accounts.seed_if_empty fills an empty table from the environment when the app starts
    op.create_table(
        'staff',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('role', sa.String(length=16), nullable=False),
        sa.Column('secret_hash', sa.String(length=60), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.add_column('sessions', sa.Column('staff_id', sa.Integer(), sa.ForeignKey('staff.id'), nullable=True))
    # Staff sessions from before name no account: their holders log in again
    op.execute("DELETE FROM sessions WHERE role <> 'guest'")

    op.create_table(
        'job_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job', sa.String(length=64), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('result', sa.String(length=16), server_default='', nullable=False),
        sa.Column('error', sa.Text(), server_default='', nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    # The ledger: every row says what it came from, and a retake points at the award it takes back
    op.add_column('score_events', sa.Column('base_points', sa.Integer(), nullable=True))
    op.add_column('score_events', sa.Column('multiplier', sa.Numeric(5, 2), server_default='1', nullable=False))
    op.add_column('score_events', sa.Column('stage_id', sa.Integer(),
                                            sa.ForeignKey('stages.id', ondelete='SET NULL'), nullable=True))
    op.add_column('score_events', sa.Column('action', sa.String(length=16), nullable=True))
    op.add_column('score_events', sa.Column('reverses_id', sa.Integer(), sa.ForeignKey('score_events.id'),
                                            nullable=True))
    op.execute("UPDATE score_events SET base_points = points")
    op.execute("""
        UPDATE score_events SET action = CASE
            WHEN reason = 'forum_arrival' THEN 'arrival'
            WHEN reason LIKE 'task:%' THEN 'task'
            WHEN reason LIKE 'bonus:%' THEN 'bonus'
            WHEN reason LIKE 'penalty:%' THEN 'penalty'
            WHEN reason LIKE 'buy:%' THEN 'buy'
            ELSE 'task' END
    """)
    op.alter_column('score_events', 'base_points', nullable=False)
    op.alter_column('score_events', 'action', nullable=False)
    op.create_unique_constraint('score_events_reverses_id_key', 'score_events', ['reverses_id'])
    # One open award per reason is checked by the ledger under the guest's lock, so an award can be paid again
    # after a retake reversed it
    op.drop_constraint('score_events_guest_id_reason_key', 'score_events', type_='unique')
    op.create_index('score_events_guest_reason', 'score_events', ['guest_id', 'reason'])

    # Stored totals, kept equal to the sum of the guest's rows by the ledger
    op.add_column('guests', sa.Column('points', sa.Integer(), server_default='0', nullable=False))
    op.add_column('guests', sa.Column('coins', sa.Integer(), server_default='0', nullable=False))
    op.execute("""
        UPDATE guests SET points = s.points, coins = s.coins
        FROM (SELECT guest_id, sum(points) AS points, sum(coins) AS coins FROM score_events GROUP BY guest_id) s
        WHERE s.guest_id = guests.id
    """)


def downgrade() -> None:
    op.drop_column('guests', 'coins')
    op.drop_column('guests', 'points')
    op.drop_index('score_events_guest_reason', table_name='score_events')
    # The old rule allows one row per reason: reversed awards and their reversals go
    op.execute("DELETE FROM score_events WHERE reverses_id IS NOT NULL OR id IN "
               "(SELECT reverses_id FROM score_events WHERE reverses_id IS NOT NULL)")
    op.create_unique_constraint('score_events_guest_id_reason_key', 'score_events', ['guest_id', 'reason'])
    op.drop_constraint('score_events_reverses_id_key', 'score_events', type_='unique')
    for column in ('reverses_id', 'action', 'stage_id', 'multiplier', 'base_points'):
        op.drop_column('score_events', column)

    op.drop_table('job_runs')

    op.execute("DELETE FROM sessions WHERE role <> 'guest'")
    op.drop_column('sessions', 'staff_id')
    op.drop_table('staff')

    op.add_column('tasks', sa.Column('partner_name', sa.String(length=100), server_default='', nullable=False))
    op.add_column('tasks', sa.Column('partner_package', sa.String(length=16), server_default='', nullable=False))
    op.add_column('prizes', sa.Column('partner', sa.String(length=100), server_default='', nullable=False))
    op.execute("UPDATE tasks SET partner_name = p.name, partner_package = p.package FROM partners p "
               "WHERE p.id = tasks.partner_id")
    op.execute("UPDATE prizes SET partner = p.name FROM partners p WHERE p.id = prizes.partner_id")
    op.drop_column('tasks', 'partner_id')
    op.drop_column('prizes', 'partner_id')
    op.drop_table('partners')
