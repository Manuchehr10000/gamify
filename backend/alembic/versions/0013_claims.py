"""uploads that survive closing the app: claims, submission thumbnails

Revision ID: 0013
Revises: 0012
"""
from alembic import op
import sqlalchemy as sa

revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The first step of sending: the phone's submission ID holds the guest's place until the files arrive
    op.create_table(
        'claims',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('guest_id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        # The server's time of the claim: it sets the stage (and later the stock and multiplier)
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('stage_id', sa.Integer(), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        # open (waiting for files) · done · lapsed (files never came in time)
        sa.Column('state', sa.String(length=8), nullable=False),
        sa.ForeignKeyConstraint(['guest_id'], ['guests.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id']),
        sa.ForeignKeyConstraint(['stage_id'], ['stages.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    # One open claim per guest per task: a second phone can't hold two places
    op.create_index('claims_open_guest_task', 'claims', ['guest_id', 'task_id'], unique=True,
                    postgresql_where=sa.text("state = 'open'"))
    op.create_index('claims_open_expires', 'claims', ['expires_at'], postgresql_where=sa.text("state = 'open'"))
    op.add_column('submissions', sa.Column('thumb', sa.LargeBinary(), nullable=True))
    # What an ok job run did, e.g. how many claims lapsed
    op.add_column('job_runs', sa.Column('detail', sa.Text(), nullable=False, server_default=''))


def downgrade() -> None:
    op.drop_column('job_runs', 'detail')
    op.drop_column('submissions', 'thumb')
    op.drop_index('claims_open_expires', table_name='claims')
    op.drop_index('claims_open_guest_task', table_name='claims')
    op.drop_table('claims')
