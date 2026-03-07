"""
Appointments between clients and providers.

  Appointment                   → booked by client for a specific ProviderService
  ClientSelfCreatedAppointment  → client posts a request, providers send offers
  ServiceHistory                → completed service record (for provider's portfolio)
  RequestOfferResponse          → provider's bid on a client's open request
"""
from app.extensions import db
from sqlalchemy import Column, Integer, Text, Boolean, DateTime, ForeignKey, Float, String
from sqlalchemy.orm import relationship
from datetime import datetime


class Appointment(db.Model):
    """A confirmed booking between one client and one provider."""
    __tablename__ = 'appointment'

    id               = Column(Integer, primary_key=True)
    client_id        = Column(Integer, ForeignKey('user.id'), nullable=False)
    provider_id      = Column(Integer, ForeignKey('user.id'), nullable=False)
    nurse_service_id = Column(Integer, ForeignKey('provider_service.id'), nullable=True)
    appointment_time = Column(DateTime, nullable=False)
    end_time         = Column(DateTime, nullable=False)
    status           = Column(String(20), default='scheduled')
    previous_status  = Column(String(20), nullable=True)
    # Possible statuses: scheduled → confirmed → confirmed_paid → work_submitted → completed | cancelled
    notes   = Column(Text)
    payment = relationship('Payment', backref='appointment', uselist=False)

    def set_status(self, new_status):
        """Set status while remembering previous one."""
        self.previous_status = self.status
        self.status = new_status


class ClientSelfCreatedAppointment(db.Model):
    """
    Client posts a service request without choosing a provider.
    Nearby providers see it and can send an offer (RequestOfferResponse).
    """
    __tablename__ = 'client_self_create_appointment'

    id                   = Column(Integer, primary_key=True)
    patient_id           = Column(Integer, ForeignKey('user.id'), nullable=False)
    provider_id          = Column(Integer, ForeignKey('user.id'), nullable=True)
    appointment_start_time = Column(DateTime, nullable=False)
    end_time             = Column(DateTime, nullable=False)
    status               = Column(String(20), default='scheduled')
    previous_status      = Column(String(20), nullable=True)
    notes                = Column(Text)
    payment              = Column(Float)
    nurse_service_id     = Column(Integer, ForeignKey('provider_service.id'), nullable=True)
    service_name         = Column(String, nullable=True)
    service_description  = Column(Text, nullable=True)
    latitude             = Column(Float)
    longitude            = Column(Float)
    address              = Column(String, nullable=True)
    district             = Column(String(100), nullable=True)  # neighborhood shown to provider before acceptance
    service_tags         = Column(String(500), nullable=True)  # comma-separated tags
    created_appo         = Column(DateTime, default=datetime.now)
    payment_intent_id    = Column(String, nullable=True)   # Stripe PI id (for capture/cancel)

    patient       = relationship('User', foreign_keys=[patient_id])
    provider      = relationship('User', foreign_keys=[provider_id])
    provider_service = relationship('ProviderService')
    offers        = relationship('RequestOfferResponse', backref='appointment_requests')

    def set_status(self, new_status):
        """Set status while remembering previous one."""
        self.previous_status = self.status
        self.status = new_status


class RequestOfferResponse(db.Model):
    """A provider's price offer on a client's open request."""
    __tablename__ = 'request_offer_response'

    id             = Column(Integer, primary_key=True)
    request_id     = Column(Integer, ForeignKey('client_self_create_appointment.id'))
    provider_id    = Column(Integer, ForeignKey('user.id'))
    proposed_price = Column(Float, default=0.0)
    counter_price  = Column(Float, nullable=True)          # client's counter-offer
    last_action_by = Column(String(10), default='provider') # 'provider' or 'client'
    status         = Column(Text, default='pending')   # pending | accepted | rejected
    created_at     = Column(DateTime, default=datetime.now)

    provider = relationship('User', foreign_keys=[provider_id])


class ServiceHistory(db.Model):
    """Archive of completed services — used to build provider's experience profile."""
    __tablename__ = 'service_history'

    id                  = Column(Integer, primary_key=True)
    provider_id         = Column(Integer, ForeignKey('user.id'), nullable=False)
    client_id           = Column(Integer, ForeignKey('user.id'), nullable=False)
    request_id          = Column(Integer, ForeignKey('client_self_create_appointment.id'), nullable=True)
    service_name        = Column(String, nullable=True)
    service_description = Column(Text, nullable=True)
    price               = Column(Float, nullable=False)
    appointment_time    = Column(DateTime, nullable=False)
    end_time            = Column(DateTime, nullable=False)
    status              = Column(String(20), default='scheduled')
    created_at          = Column(DateTime, default=datetime.now)

    provider = relationship('User', foreign_keys=[provider_id])
    client   = relationship('User', foreign_keys=[client_id])
    request  = relationship('ClientSelfCreatedAppointment', foreign_keys=[request_id])
