"""
Telegram notification helper.

Usage:
    from app.utils.telegram import send_telegram
    send_telegram("Hello from the app!")
"""
import requests
from flask import current_app
from threading import Thread


def send_telegram(message):
    """Send a message to the configured Telegram chat (non-blocking)."""
    token   = current_app.config.get('TELEGRAM_BOT_TOKEN')
    chat_id = current_app.config.get('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {'chat_id': chat_id, 'text': message, 'parse_mode': 'HTML'}

    def _send():
        try:
            requests.post(url, json=payload, timeout=5)
        except Exception:
            pass

    Thread(target=_send, daemon=True).start()
