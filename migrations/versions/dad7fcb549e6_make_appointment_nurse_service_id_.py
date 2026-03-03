"""make appointment nurse_service_id nullable

Revision ID: dad7fcb549e6
Revises: ecd236d778f8
Create Date: 2026-02-27 11:10:21.179146

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'dad7fcb549e6'
down_revision = 'ecd236d778f8'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('appointment', 'nurse_service_id',
                    existing_type=sa.INTEGER(),
                    nullable=True)


def downgrade():
    op.alter_column('appointment', 'nurse_service_id',
                    existing_type=sa.INTEGER(),
                    nullable=False)
