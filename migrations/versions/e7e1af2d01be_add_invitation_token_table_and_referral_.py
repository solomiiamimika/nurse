"""add invitation_token table and referral fields to user

Revision ID: e7e1af2d01be
Revises: 44ee9e247322
Create Date: 2026-03-03 09:13:42.152542

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e7e1af2d01be'
down_revision = '44ee9e247322'
branch_labels = None
depends_on = None


def upgrade():
    # invitation_token already exists in DB — skip create
    op.add_column('user', sa.Column('referral_code', sa.String(20), nullable=True))
    op.add_column('user', sa.Column('referred_by', sa.String(20), nullable=True))
    op.create_unique_constraint('uq_user_referral_code', 'user', ['referral_code'])


def downgrade():
    op.drop_constraint('uq_user_referral_code', 'user', type_='unique')
    op.drop_column('user', 'referred_by')
    op.drop_column('user', 'referral_code')
