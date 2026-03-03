"""rename doctor_id and nurse_id to provider_id

Revision ID: 4222f85b37ec
Revises: 2500f36fe504
Create Date: 2026-02-27 10:50:29.627213

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4222f85b37ec'
down_revision = '2500f36fe504'
branch_labels = None
depends_on = None


def upgrade():
    # Rename columns using raw SQL to preserve data
    op.execute('ALTER TABLE appointment RENAME COLUMN nurse_id TO provider_id')
    op.execute('ALTER TABLE nurse_service RENAME COLUMN nurse_id TO provider_id')
    op.execute('ALTER TABLE client_self_create_appointment RENAME COLUMN doctor_id TO provider_id')
    op.execute('ALTER TABLE request_offer_response RENAME COLUMN doctor_id TO provider_id')
    op.execute('ALTER TABLE review RENAME COLUMN doctor_id TO provider_id')
    op.execute('ALTER TABLE prescription RENAME COLUMN doctor_id TO provider_id')

    # Also rename in service_history if it exists with nurse_id
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='service_history' AND column_name='nurse_id'
            ) THEN
                ALTER TABLE service_history RENAME COLUMN nurse_id TO provider_id;
            END IF;
        END$$;
    """)

    # Make payment.appointment_id and amount_cents nullable
    op.alter_column('payment', 'appointment_id', existing_type=sa.INTEGER(), nullable=True)
    op.alter_column('payment', 'amount_cents', existing_type=sa.INTEGER(), nullable=True)


def downgrade():
    op.execute('ALTER TABLE appointment RENAME COLUMN provider_id TO nurse_id')
    op.execute('ALTER TABLE nurse_service RENAME COLUMN provider_id TO nurse_id')
    op.execute('ALTER TABLE client_self_create_appointment RENAME COLUMN provider_id TO doctor_id')
    op.execute('ALTER TABLE request_offer_response RENAME COLUMN provider_id TO doctor_id')
    op.execute('ALTER TABLE review RENAME COLUMN provider_id TO doctor_id')
    op.execute('ALTER TABLE prescription RENAME COLUMN provider_id TO doctor_id')

    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='service_history' AND column_name='provider_id'
            ) THEN
                ALTER TABLE service_history RENAME COLUMN provider_id TO nurse_id;
            END IF;
        END$$;
    """)

    op.alter_column('payment', 'appointment_id', existing_type=sa.INTEGER(), nullable=False)
    op.alter_column('payment', 'amount_cents', existing_type=sa.INTEGER(), nullable=False)
