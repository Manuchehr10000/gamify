"""admin settings: settings, change log, versions for concurrent edits, switch-offs, partner logos

Revision ID: 0012
Revises: 0011
"""
from alembic import op
import sqlalchemy as sa

revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None

# Tables the admin edits in forms: a save sends the version it read, and a stale one is refused
VERSIONED = ('stages', 'tasks', 'prizes', 'questions', 'levels', 'partners', 'staff')


def upgrade() -> None:
    # Game settings; app.settings.ensure fills missing keys with their defaults when the app starts
    op.create_table(
        'settings',
        sa.Column('key', sa.String(length=64), nullable=False),
        sa.Column('value', sa.Numeric(12, 2), nullable=False),
        sa.Column('min_value', sa.Numeric(12, 2), nullable=False),
        sa.Column('max_value', sa.Numeric(12, 2), nullable=False),
        # now (from now on) · recheck (past activity is checked again) · locked (refused while running)
        sa.Column('effect', sa.String(length=16), nullable=False),
        sa.Column('version', sa.Integer(), server_default='1', nullable=False),
        sa.PrimaryKeyConstraint('key'),
    )
    op.create_table(
        'change_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        # No foreign key: the log outlives the account
        sa.Column('staff_id', sa.Integer(), nullable=True),
        sa.Column('staff_name', sa.String(length=100), nullable=False),
        sa.Column('kind', sa.String(length=32), nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=True),
        sa.Column('item', sa.String(length=200), nullable=False),
        sa.Column('field', sa.String(length=64), nullable=False),
        sa.Column('old_value', sa.Text(), nullable=True),
        sa.Column('new_value', sa.Text(), nullable=True),
        sa.Column('source', sa.String(length=8), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('change_events_created_at', 'change_events', ['created_at'])
    # The log can't be edited or deleted, whoever connects
    op.execute("""
        CREATE FUNCTION change_events_frozen() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'change_events is append-only'; END $$
    """)
    op.execute("CREATE TRIGGER change_events_frozen BEFORE UPDATE OR DELETE ON change_events "
               "FOR EACH ROW EXECUTE FUNCTION change_events_frozen()")

    for table in VERSIONED:
        op.add_column(table, sa.Column('version', sa.Integer(), server_default='1', nullable=False))
    op.add_column('stages', sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False))
    op.add_column('staff', sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False))
    # Logos are PNG or JPEG bytes, as photos are; nothing wrote the old text column
    op.drop_column('partners', 'logo')
    op.add_column('partners', sa.Column('logo', sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    op.drop_column('partners', 'logo')
    op.add_column('partners', sa.Column('logo', sa.Text(), nullable=True))
    op.drop_column('staff', 'active')
    op.drop_column('stages', 'active')
    for table in VERSIONED:
        op.drop_column(table, 'version')
    op.execute("DROP TRIGGER change_events_frozen ON change_events")
    op.execute("DROP FUNCTION change_events_frozen()")
    op.drop_index('change_events_created_at', table_name='change_events')
    op.drop_table('change_events')
    op.drop_table('settings')
