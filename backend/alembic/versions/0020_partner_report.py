"""partner report: an unguessable token on each photo submission for the partner's photo links

Revision ID: 0020
Revises: 0019
"""
import secrets

from alembic import op
import sqlalchemy as sa

revision = '0020'
down_revision = '0019'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('submissions', sa.Column('photo_token', sa.String(64), nullable=True))
    op.create_index('submissions_photo_token', 'submissions', ['photo_token'], unique=True)
    # Photos sent before this piece get their token now; text submissions have no photo to link
    conn = op.get_bind()
    for (sid,) in conn.execute(sa.text("SELECT id FROM submissions WHERE photo IS NOT NULL")).all():
        conn.execute(sa.text("UPDATE submissions SET photo_token = :t WHERE id = :id"),
                     {"t": secrets.token_urlsafe(24), "id": sid})


def downgrade() -> None:
    op.drop_index('submissions_photo_token', table_name='submissions')
    op.drop_column('submissions', 'photo_token')
