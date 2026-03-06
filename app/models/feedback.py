"""
Feedback — user-submitted bug reports and suggestions.
"""
from app.extensions import db
from sqlalchemy import Column, Integer, Text, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime


class Feedback(db.Model):
    __tablename__ = 'feedback'

    id         = Column(Integer, primary_key=True)
    user_id    = Column(Integer, ForeignKey('user.id'), nullable=True)
    category   = Column(String(20), nullable=False)   # 'bug' or 'suggestion'
    message    = Column(Text, nullable=False)
    page_url   = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    status     = Column(String(20), default='new')     # new / reviewed / resolved

    user = relationship('User', foreign_keys=[user_id])
