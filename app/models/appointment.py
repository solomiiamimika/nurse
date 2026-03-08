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
    # Possible statuses: scheduled → confirmed → confirmed_paid → in_progress → work_submitted → completed | cancelled | no_show | disputed
    notes   = Column(Text)
    payment = relationship('Payment', backref='appointment', uselist=False)

    # Arrival & lateness tracking
    provider_arrived_at  = Column(DateTime, nullable=True)
    provider_late_minutes = Column(Integer, nullable=True)
    work_submitted_at    = Column(DateTime, nullable=True)

    def set_status(self, new_status):
        """Set status while remembering previous one."""
        self.previous_status = self.status
        self.status = new_status
        if new_status == 'work_submitted':
            self.work_submitted_at = datetime.now()


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

    # Arrival & lateness tracking
    provider_arrived_at  = Column(DateTime, nullable=True)
    provider_late_minutes = Column(Integer, nullable=True)
    work_submitted_at    = Column(DateTime, nullable=True)

    patient       = relationship('User', foreign_keys=[patient_id])
    provider      = relationship('User', foreign_keys=[provider_id])
    provider_service = relationship('ProviderService')
    offers        = relationship('RequestOfferResponse', backref='appointment_requests')

    def set_status(self, new_status):
        """Set status while remembering previous one."""
        self.previous_status = self.status
        self.status = new_status
        if new_status == 'work_submitted':
            self.work_submitted_at = datetime.now()


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


class NoShowRecord(db.Model):
    """Record of a no-show event for tracking purposes."""
    __tablename__ = 'no_show_record'

    id              = Column(Integer, primary_key=True)
    appointment_id  = Column(Integer, ForeignKey('appointment.id'), nullable=True)
    request_id      = Column(Integer, ForeignKey('client_self_create_appointment.id'), nullable=True)
    reported_by_id  = Column(Integer, ForeignKey('user.id'), nullable=False)
    no_show_user_id = Column(Integer, ForeignKey('user.id'), nullable=False)
    role            = Column(String(20), nullable=False)   # 'client' or 'provider'
    reason          = Column(Text, nullable=True)
    created_at      = Column(DateTime, default=datetime.now)

    reported_by  = relationship('User', foreign_keys=[reported_by_id])
    no_show_user = relationship('User', foreign_keys=[no_show_user_id])
    appointment  = relationship('Appointment', foreign_keys=[appointment_id])
    request_rel  = relationship('ClientSelfCreatedAppointment', foreign_keys=[request_id])


class Dispute(db.Model):
    """Client dispute about service quality or completion."""
    __tablename__ = 'dispute'

    id              = Column(Integer, primary_key=True)
    appointment_id  = Column(Integer, ForeignKey('appointment.id'), nullable=True)
    request_id      = Column(Integer, ForeignKey('client_self_create_appointment.id'), nullable=True)
    reporter_id     = Column(Integer, ForeignKey('user.id'), nullable=False)
    reason          = Column(String(50), nullable=False)   # 'not_completed', 'quality_issue', 'other'
    description     = Column(Text, nullable=True)
    status          = Column(String(20), default='open')   # 'open', 'under_review', 'resolved'
    admin_notes     = Column(Text, nullable=True)
    resolution      = Column(String(30), nullable=True)    # 'refunded', 'partial_refund', 'dismissed', 'warning'
    resolved_by_id  = Column(Integer, ForeignKey('user.id'), nullable=True)
    created_at      = Column(DateTime, default=datetime.now)
    resolved_at     = Column(DateTime, nullable=True)

    reporter    = relationship('User', foreign_keys=[reporter_id])
    resolved_by = relationship('User', foreign_keys=[resolved_by_id])
    appointment = relationship('Appointment', foreign_keys=[appointment_id])
    request_rel = relationship('ClientSelfCreatedAppointment', foreign_keys=[request_id])
