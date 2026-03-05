"""
Medical data: records, prescriptions, and reviews.

  MedicalRecord  → diagnosis + treatment notes written by provider
  Prescription   → medication instructions for a patient
  Review         → star rating + comment left by client after appointment
"""
from app.extensions import db
from sqlalchemy import Column, Integer, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy import func
from datetime import datetime


class MedicalRecord(db.Model):
    __tablename__ = 'medical_record'

    id         = Column(Integer, primary_key=True)
    client_id  = Column(Integer, ForeignKey('user.id'), nullable=False)
    diagnosis  = Column(Text, nullable=False)
    treatment  = Column(Text)
    record_date = Column(DateTime, default=datetime.now)

    client = relationship('User', foreign_keys=[client_id])


class Prescription(db.Model):
    __tablename__ = 'prescription'

    id              = Column(Integer, primary_key=True)
    patient_id      = Column(Integer, ForeignKey('user.id'), nullable=False)
    provider_id     = Column(Integer, ForeignKey('user.id'), nullable=False)
    appointment_id  = Column(Integer, ForeignKey('appointment.id'))
    medication_name = Column(Text)
    dosage          = Column(Text)
    instructions    = Column(Text)
    created_at      = Column(DateTime, default=datetime.now)

    patient  = relationship('User', foreign_keys=[patient_id])
    provider = relationship('User', foreign_keys=[provider_id])


class Review(db.Model):
    """Star rating (1–5) + optional comment, tied to a completed appointment."""
    __tablename__ = 'review'

    id             = Column(Integer, primary_key=True)
    patient_id     = Column(Integer, ForeignKey('user.id'), nullable=False)
    provider_id    = Column(Integer, ForeignKey('user.id'), nullable=False)
    appointment_id = Column(Integer, ForeignKey('appointment.id'), nullable=False)
    rating         = Column(Integer, nullable=False)   # 1 – 5
    comment        = Column(Text)
    created_at     = Column(DateTime, default=datetime.now)

    patient  = relationship('User', foreign_keys=[patient_id])
    provider = relationship('User', foreign_keys=[provider_id])

    @hybrid_property
    def average_nurse_rating(self):
        return (
            db.session.query(func.avg(Review.rating))
            .filter(Review.provider_id == self.id)
            .scalar() or 0
        )

    @hybrid_property
    def reviews_nurse_count(self):
        return Review.query.filter_by(provider_id=self.id).count()
