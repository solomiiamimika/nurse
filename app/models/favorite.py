"""
Favorite — client's wishlist of providers and services.
FavoriteShareToken — shareable public link for a user's favorites list.
"""
from app.extensions import db
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime


class Favorite(db.Model):
    __tablename__ = 'favorite'
    __table_args__ = (
        UniqueConstraint('user_id', 'provider_id', name='uq_fav_provider'),
        UniqueConstraint('user_id', 'service_id', name='uq_fav_service'),
    )

    id          = Column(Integer, primary_key=True)
    user_id     = Column(Integer, ForeignKey('user.id'), nullable=False)
    provider_id = Column(Integer, ForeignKey('user.id'), nullable=True)
    service_id  = Column(Integer, ForeignKey('provider_service.id'), nullable=True)
    created_at  = Column(DateTime, default=datetime.now)

    user     = relationship('User', foreign_keys=[user_id], backref='favorites')
    provider = relationship('User', foreign_keys=[provider_id])
    service  = relationship('ProviderService', foreign_keys=[service_id])


class FavoriteShareToken(db.Model):
    __tablename__ = 'favorite_share_token'

    id         = Column(Integer, primary_key=True)
    user_id    = Column(Integer, ForeignKey('user.id'), nullable=False, unique=True)
    token      = Column(String(64), unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.now)

    user = relationship('User', foreign_keys=[user_id])
