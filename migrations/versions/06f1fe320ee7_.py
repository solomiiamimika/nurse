"""empty message

Revision ID: 06f1fe320ee7
Revises: 7602c817afe7
Create Date: 2026-01-16 17:27:54.561836

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '06f1fe320ee7'
down_revision = '7602c817afe7'
branch_labels = None
depends_on = None


def upgrade():
   

    with op.batch_alter_table('payment', schema=None) as batch_op:
        batch_op.add_column(sa.Column('amount_cents', sa.Integer(), nullable=False))
        batch_op.add_column(sa.Column('currency', sa.String(length=3), nullable=False))
        batch_op.add_column(sa.Column('platform_fee_cents', sa.Integer(), nullable=False))
        batch_op.add_column(sa.Column('stripe_payment_intent_id', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('stripe_charge_id', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('stripe_transfer_id', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('transfer_group', sa.String(length=64), nullable=True))
        batch_op.create_index(batch_op.f('ix_payment_stripe_charge_id'), ['stripe_charge_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_payment_stripe_payment_intent_id'), ['stripe_payment_intent_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_payment_stripe_transfer_id'), ['stripe_transfer_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_payment_transaction_id'), ['transaction_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_payment_transfer_group'), ['transfer_group'], unique=False)

   

 
