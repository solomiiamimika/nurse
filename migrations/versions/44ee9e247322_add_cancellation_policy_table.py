"""add cancellation_policy table

Revision ID: 44ee9e247322
Revises: dad7fcb549e6
Create Date: 2026-03-03 09:09:42.843655

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '44ee9e247322'
down_revision = 'dad7fcb549e6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'cancellation_policy',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('provider_id', sa.Integer(), nullable=False),
        sa.Column('free_cancel_hours', sa.Integer(), nullable=True),
        sa.Column('late_cancel_fee_percent', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('no_show_client_fee_percent', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['provider_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('provider_id')
    )


def downgrade():
    op.drop_table('cancellation_policy')
