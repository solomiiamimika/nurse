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


# Categorized service tags
SERVICE_TAG_CATEGORIES = {
    'Home': [
        'Cleaning', 'Deep Cleaning', 'Window Cleaning', 'Cooking',
        'Laundry', 'Ironing', 'Repairs', 'Furniture Assembly',
        'Moving Help', 'Packing', 'Garden/Balcony', 'Decluttering',
        'Painting', 'Plumbing', 'Electrical',
    ],
    'Elderly Care': [
        'Companionship', 'Mobility Help', 'Medication Reminder',
        'Personal Hygiene', 'Night Watch', 'Doctor Accompaniment',
        'Meal Preparation', 'Exercise Assistance',
        'Reading/Conversation', 'Hospital Visit',
    ],
    'Childcare': [
        'Babysitting', 'Tutoring', 'School Pickup/Dropoff',
        'Newborn Care', 'Homework Help', 'Language Practice',
        'Creative Activities', 'Overnight Care', 'Special Needs Support',
    ],
    'Health': [
        'Injection', 'IV Drip', 'Wound Care', 'Physiotherapy',
        'Blood Test', 'Massage', 'Blood Pressure Check', 'ECG',
        'Post-Surgery Care', 'Rehabilitation Exercise',
        'Mental Health Support',
    ],
    'Pets': [
        'Dog Walking', 'Pet Sitting', 'Grooming', 'Vet Visit',
        'Pet Feeding', 'Cat Care', 'Pet Transport',
        'Pet Training', 'Overnight Pet Care',
    ],
    'Errands': [
        'Grocery Shopping', 'Pharmacy Run', 'Delivery', 'Post Office',
        'Package Pickup', 'Returns/Exchanges', 'Key Handover',
        'Waiting for Delivery/Technician', 'Airport Pickup/Dropoff',
        'Gift Shopping',
    ],
    'Tech Help': [
        'WiFi/Router Setup', 'Printer Setup', 'Phone Help',
        'Computer Help', 'Smart Home Setup', 'TV/Streaming Setup',
        'Data Backup', 'Software Install', 'Online Account Help',
    ],
    'Admin & Bureaucracy': [
        'Anmeldung Help', 'Insurance Forms', 'Tax Documents',
        'Translation', 'Appointment Booking', 'Letter Writing',
        'Visa Paperwork', 'Bank Account Setup',
        'Kündigung Help', 'Bürgeramt Accompaniment',
    ],
    'Events': [
        'Party Help', 'Catering', 'Decoration', 'Photography',
        'DJ/Music', 'Event Cleanup', 'Birthday Organization',
        'BBQ Setup', 'Moving-in Party',
    ],
    'Lessons & Skills': [
        'German Language', 'English Language', 'Ukrainian Language',
        'Music Lessons', 'Cooking Lessons', 'Yoga/Fitness',
        'Art Lessons', 'Dance Lessons', 'Driving Practice',
    ],
}

# Flat list for backward compatibility
SERVICE_TAGS = []
for _tags in SERVICE_TAG_CATEGORIES.values():
    SERVICE_TAGS.extend(_tags)


class CancellationPolicy(db.Model):
    """How much a client pays if they cancel late or don't show up."""
    __tablename__ = 'cancellation_policy'

    id          = Column(Integer, primary_key=True)
    provider_id = Column(Integer, ForeignKey('user.id'), nullable=False, unique=True)

    free_cancel_hours        = Column(Integer, nullable=True, default=24)     # 24h free cancellation
    late_cancel_fee_percent  = Column(Integer, nullable=False, default=25)   # 25% fee for late cancel
    no_show_client_fee_percent = Column(Integer, nullable=False, default=100) # 100% if client no-shows

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    provider = relationship('User', foreign_keys=[provider_id])
