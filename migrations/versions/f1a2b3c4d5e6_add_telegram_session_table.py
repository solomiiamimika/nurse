"""add telegram_session table for bot conversation persistence

Revision ID: f1a2b3c4d5e6
Revises: 4246b15ba905
Create Date: 2026-03-07 15:36:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f1a2b3c4d5e6'
down_revision = '4246b15ba905'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'telegram_session',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('telegram_id', sa.BigInteger(), nullable=False),
        sa.Column('flow', sa.String(50), nullable=False),
        sa.Column('step', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('data_json', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_telegram_session_telegram_id', 'telegram_session', ['telegram_id'], unique=True)


def downgrade():
    op.drop_index('ix_telegram_session_telegram_id', table_name='telegram_session')
    op.drop_table('telegram_session')
