"""
Payments processed through Stripe.

Tracks the full lifecycle:
  pending → completed/paid → paid_out
  or
  pending → failed | cancelled | refunded
"""
from app.extensions import db
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from datetime import datetime


class Payment(db.Model):
    __tablename__ = 'payment'

    id             = Column(Integer, primary_key=True)
    user_id        = Column(Integer, ForeignKey('user.id'), nullable=False)
    appointment_id = Column(Integer, ForeignKey('appointment.id'), nullable=True)

    amount          = Column(Float, nullable=False)          # display value
    amount_cents    = Column(Integer, nullable=True)         # e.g. 5000 = €50.00
    currency        = Column(String(3), nullable=False, default='eur')

    platform_fee_cents = Column(Integer, nullable=False, default=0)   # our commission

    payment_date   = Column(DateTime, default=datetime.now)
    status         = Column(String(20), default='pending')
    # pending | completed | paid | failed | cancelled | refunded | paid_out

    payment_method = Column(String(50))
    transaction_id = Column(String(50), index=True)

    # Stripe identifiers
    stripe_payment_intent_id = Column(String(64), index=True)
    stripe_charge_id         = Column(String(64), index=True)
    stripe_transfer_id       = Column(String(64), index=True)
    transfer_group           = Column(String(64), index=True)
