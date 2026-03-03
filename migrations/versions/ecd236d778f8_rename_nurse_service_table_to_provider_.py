"""rename nurse_service table to provider_service

Revision ID: ecd236d778f8
Revises: 4222f85b37ec
Create Date: 2026-02-27 10:57:13.949386

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ecd236d778f8'
down_revision = '4222f85b37ec'
branch_labels = None
depends_on = None


def upgrade():
    # Drop empty provider_service if it was created by a stale migration
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema='public' AND table_name='provider_service'
            ) THEN
                DROP TABLE provider_service CASCADE;
            END IF;
        END$$;
    """)
    op.execute('ALTER TABLE nurse_service RENAME TO provider_service')


def downgrade():
    op.execute('ALTER TABLE provider_service RENAME TO nurse_service')
