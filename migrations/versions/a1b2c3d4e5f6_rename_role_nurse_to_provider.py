"""rename role nurse to provider

Revision ID: a1b2c3d4e5f6
Revises: e7e1af2d01be
Create Date: 2026-03-03 12:00:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'e7e1af2d01be'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("UPDATE \"user\" SET role = 'provider' WHERE role = 'nurse'")


def downgrade():
    op.execute("UPDATE \"user\" SET role = 'nurse' WHERE role = 'provider'")
