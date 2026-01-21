"""empty message

Revision ID: e8810b566179
Revises: 06f1fe320ee7
Create Date: 2026-01-21 10:05:28.737149

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e8810b566179'
down_revision = '06f1fe320ee7'
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('stripe_account_id', sa.String(), nullable=True))