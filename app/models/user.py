"""
User accounts and invitation tokens.

Every person in the system is a User — role decides what they can do:
  - 'client'   → books providers
  - 'provider' → provides services
"""
from app.extensions import db, bcrypt, login_manager
from flask_login import UserMixin
from sqlalchemy import Column, Integer, Text, Boolean, DateTime, ForeignKey, Float, String, Date
from sqlalchemy.orm import relationship
from datetime import datetime


class User(db.Model, UserMixin):
    __tablename__ = 'user'

    id            = Column(Integer, primary_key=True)
    user_name     = Column(Text, unique=True, nullable=False, name='uq_user_user_name')
    email         = Column(Text(), unique=True, nullable=False, name='uq_user_email')
    password_hash = Column(Text, nullable=True)
    google_id     = Column(String(100), unique=True, nullable=True)

    role          = Column(Text)           # 'client' or 'provider'
    full_name     = Column(String)
    phone_number  = Column(String)
    date_birth    = Column(Date)
    about_me      = Column(String)
    address       = Column(String)
    photo         = Column(String)
    documents     = Column(Text)
    portfolio     = Column(Text)   # JSON: [{"url":"filename","type":"photo|video"}, ...]

    latitude          = Column(Float)
    longitude         = Column(Float)
    location_approved = Column(Boolean, default=False)
    online            = Column(Boolean)

    stripe_account_id  = Column(String)   # Provider's Stripe Connected Account
    stripe_customer_id = Column(String)   # Client's Stripe Customer (for saved cards)
    referral_code     = Column(String(20), unique=True, nullable=True)
    referred_by       = Column(String(20), nullable=True)

    is_owner    = Column(Boolean, default=False)
    is_active   = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    verification_method = Column(String(50), nullable=True)   # 'manual', 'stripe_kyc', etc.
    verification_date   = Column(DateTime, nullable=True)

    terms_accepted     = Column(Boolean, default=False)
    has_insurance      = Column(Boolean, default=False)
    insurance_document = Column(String)
    profile_visibility = Column(Text, default='{}')

    created_at = Column(DateTime, default=datetime.now)

    # ── Relationships ──────────────────────────────────────────────
    reviews_received = db.relationship(
        'Review', foreign_keys='Review.provider_id',
        backref='provider_profile', lazy=True
    )
    sent_messages = db.relationship(
        'Message', foreign_keys='Message.sender_id',
        backref='sender', lazy=True, cascade='all, delete-orphan'
    )
    received_messages = db.relationship(
        'Message', foreign_keys='Message.recipient_id',
        backref='recipient', lazy=True, cascade='all, delete-orphan'
    )
    client_appointments = db.relationship(
        'Appointment', foreign_keys='Appointment.client_id',
        backref='client', lazy=True, cascade='all, delete-orphan'
    )
    provider_appointments = db.relationship(
        'Appointment', foreign_keys='Appointment.provider_id',
        backref='provider', lazy=True, cascade='all, delete-orphan'
    )
    payments = db.relationship(
        'Payment', backref='user', lazy=True, cascade='all, delete-orphan'
    )

    # ── Computed properties ────────────────────────────────────────
    @property
    def average_rating(self):
        if not self.reviews_received:
            return 0.0
        total = sum(r.rating for r in self.reviews_received)
        return round(total / len(self.reviews_received), 1)

    @property
    def review_count(self):
        return len(self.reviews_received)

    # ── Gamification ──────────────────────────────────────────────
    LEVEL_THRESHOLDS = [
        (0,   'Newcomer',    '🌱'),
        (3,   'Explorer',    '🔍'),
        (10,  'Regular',     '⭐'),
        (25,  'Pro',         '💎'),
        (50,  'Expert',      '🏆'),
        (100, 'Legend',      '👑'),
    ]

    @property
    def completed_orders_count(self):
        if self.role == 'client':
            return len([a for a in self.client_appointments if a.status in ('completed', 'confirmed_paid')])
        return len([a for a in self.provider_appointments if a.status in ('completed', 'confirmed_paid')])

    @property
    def player_level(self):
        count = self.completed_orders_count
        level = self.LEVEL_THRESHOLDS[0]
        for threshold, title, icon in self.LEVEL_THRESHOLDS:
            if count >= threshold:
                level = (threshold, title, icon)
        return level

    @property
    def player_level_info(self):
        count = self.completed_orders_count
        _, title, icon = self.player_level
        # Find next level
        next_level = None
        for threshold, next_title, next_icon in self.LEVEL_THRESHOLDS:
            if threshold > count:
                next_level = (threshold, next_title, next_icon)
                break
        progress = 0
        if next_level:
            prev_threshold = self.player_level[0]
            progress = int((count - prev_threshold) / (next_level[0] - prev_threshold) * 100)
        else:
            progress = 100
        return {
            'title': title,
            'icon': icon,
            'count': count,
            'progress': progress,
            'next_title': next_level[1] if next_level else None,
            'next_icon': next_level[2] if next_level else None,
            'next_threshold': next_level[0] if next_level else None,
        }

    # ── Password helpers ───────────────────────────────────────────
    @property
    def password(self):
        raise AttributeError('password is not readable')

    @password.setter
    def password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def verify_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)


class InvitationToken(db.Model):
    """One-time invite links — optionally pre-assigned to a role or email."""
    __tablename__ = 'invitation_token'

    id         = Column(Integer, primary_key=True)
    token      = Column(String(64), unique=True, nullable=False)
    created_by = Column(Integer, ForeignKey('user.id'), nullable=True)
    role_hint  = Column(String(10), nullable=True)   # 'provider' | 'client' | None
    email_hint = Column(String(255), nullable=True)

    used    = Column(Boolean, default=False)
    used_by = Column(Integer, ForeignKey('user.id'), nullable=True)
    used_at = Column(DateTime, nullable=True)

    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    creator      = relationship('User', foreign_keys=[created_by])
    used_by_user = relationship('User', foreign_keys=[used_by])
