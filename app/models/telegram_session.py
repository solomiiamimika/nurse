"""
Persistent conversation state for the Telegram bot.

Each row represents one active multi-step conversation.
Rows are deleted when the conversation ends (confirm/cancel/timeout).
"""
import json
from datetime import datetime
from app.extensions import db
from sqlalchemy import Column, Integer, BigInteger, String, Text, DateTime


class TelegramSession(db.Model):
    __tablename__ = 'telegram_session'

    id          = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    flow        = Column(String(50), nullable=False)
    step        = Column(Integer, nullable=False, default=0)
    data_json   = Column(Text, nullable=False, default='{}')
    created_at  = Column(DateTime, default=datetime.utcnow)
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def data(self):
        try:
            return json.loads(self.data_json or '{}')
        except (json.JSONDecodeError, TypeError):
            return {}

    @data.setter
    def data(self, value):
        self.data_json = json.dumps(value, default=str)

    def __repr__(self):
        return f'<TelegramSession tg={self.telegram_id} flow={self.flow} step={self.step}>'
