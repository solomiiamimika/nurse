"""
Real-time messages between users (via Flask-SocketIO).

Supports text, images, audio, video, and file attachments.
Files are stored in Supabase Storage, referenced here by path.
"""
from app.extensions import db
from sqlalchemy import Column, Integer, Text, Boolean, DateTime, ForeignKey, String
from datetime import datetime


class Message(db.Model):
    __tablename__ = 'message'

    id           = Column(Integer, primary_key=True)
    sender_id    = Column(Integer, ForeignKey('user.id', name='fk_message_sender'))
    recipient_id = Column(Integer, ForeignKey('user.id', name='fk_message_recipient'))
    text         = Column(Text)
    timestamp    = Column(DateTime, default=datetime.now)
    is_read      = Column(Boolean, default=False)

    # For non-text messages
    message_type      = Column(String, default='text')   # 'text' | 'audio' | 'video' | 'photo' | 'file'
    supabase_file_path = Column(String)
    mime_type         = Column(String)
    file_name         = Column(String)
    file_size         = Column(Integer)
