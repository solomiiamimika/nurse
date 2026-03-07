"""
Services that providers offer to clients.

  Service         → the global catalogue of standard service types
  ProviderService → a specific service customised by a provider (price, duration)
  CancellationPolicy → provider's rules for late cancellation / no-show fees
"""
from app.extensions import db
from sqlalchemy import Column, Integer, Text, Boolean, Float, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime


class Service(db.Model):
    """Global service catalogue — e.g. 'Blood Pressure Check', 'IV Infusion'."""
    __tablename__ = 'service'

    id            = Column(Integer, primary_key=True)
    name          = Column(String(100), nullable=False)
    description   = Column(Text)
    base_price    = Column(Float, nullable=False)
    base_duration = Column(Integer, nullable=False)   # minutes
    is_standart   = Column(Boolean, default=True)

    provider_services = relationship('ProviderService', backref='base_service', lazy=True)


class ProviderService(db.Model):
    """A service offered by a specific provider, with their own price and duration."""
    __tablename__ = 'provider_service'

    id           = Column(Integer, primary_key=True)
    provider_id  = Column(Integer, ForeignKey('user.id'), nullable=False)
    service_id   = Column(Integer, ForeignKey('service.id'), nullable=True)
    name         = Column(String(100))
    price        = Column(Float, nullable=False)
    duration     = Column(Integer, nullable=False)   # minutes
    description  = Column(Text)
    is_available = Column(Boolean, default=True)
    tags         = Column(String(500), nullable=True)  # comma-separated tags

    appointments = relationship('Appointment', backref='provider_service', lazy=True)


# Predefined service tags
SERVICE_TAGS = [
    'Injection', 'IV Drip', 'Wound Care', 'Blood Test',
    'Physiotherapy', 'Massage', 'Elderly Care', 'Post-Surgery',
    'Consultation', 'Home Visit', 'Emergency', 'Vaccination',
    'Bandaging', 'Catheter', 'Vital Signs', 'Medication',
    'Rehabilitation', 'Palliative Care', 'Pediatric', 'Prenatal',
]


class CancellationPolicy(db.Model):
    """How much a client pays if they cancel late or don't show up."""
    __tablename__ = 'cancellation_policy'

    id          = Column(Integer, primary_key=True)
    provider_id = Column(Integer, ForeignKey('user.id'), nullable=False, unique=True)

    free_cancel_hours        = Column(Integer, nullable=True, default=None)   # None = always free
    late_cancel_fee_percent  = Column(Integer, nullable=False, default=0)
    no_show_client_fee_percent = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    provider = relationship('User', foreign_keys=[provider_id])
