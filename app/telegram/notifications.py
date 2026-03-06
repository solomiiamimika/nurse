"""
Telegram notifications to individual users.

send_user_telegram()  — low-level: send a message to a user by user_id
notify_*()            — high-level: event-based notifications
"""
import requests
from threading import Thread
from flask import current_app


def _send_raw(token, chat_id, text, reply_markup=None):
    """Send a Telegram message (blocking). Use in threads."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'}
    if reply_markup:
        payload['reply_markup'] = reply_markup
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception:
        pass


def send_user_telegram(user_id, message, reply_markup=None):
    """
    Send a Telegram message to a user (non-blocking).
    Checks that user has telegram_id and notifications enabled.
    """
    from app.models import User
    token = current_app.config.get('TELEGRAM_BOT_TOKEN')
    if not token:
        return

    user = User.query.get(user_id)
    if not user or not user.telegram_id or not user.telegram_notifications:
        return

    Thread(
        target=_send_raw,
        args=(token, user.telegram_id, message, reply_markup),
        daemon=True,
    ).start()


# ── Event-based notifications ──────────────────────────────────────


def notify_new_offer(request_obj, offer):
    """Client receives: a provider sent an offer."""
    from app.models import User
    provider = User.query.get(offer.provider_id)
    name = (provider.full_name or provider.user_name) if provider else 'Provider'
    msg = (
        f"<b>New offer on your request!</b>\n\n"
        f"Service: {request_obj.service_name}\n"
        f"Provider: {name}\n"
        f"Price: {offer.proposed_price:.2f} EUR\n\n"
        f"Open the app to accept or negotiate."
    )
    send_user_telegram(request_obj.patient_id, msg)


def notify_offer_accepted(offer):
    """Provider receives: client accepted their offer."""
    from app.models import User
    req = offer.appointment_requests
    if not req:
        return
    client = User.query.get(req.patient_id)
    name = (client.full_name or client.user_name) if client else 'Client'
    msg = (
        f"<b>Your offer was accepted!</b>\n\n"
        f"Service: {req.service_name}\n"
        f"Client: {name}\n"
        f"Price: {offer.proposed_price:.2f} EUR\n"
        f"Date: {req.appointment_start_time.strftime('%d.%m.%Y %H:%M')}"
    )
    send_user_telegram(offer.provider_id, msg)


def notify_offer_rejected(offer):
    """Provider receives: client rejected their offer."""
    req = offer.appointment_requests
    svc = req.service_name if req else 'Service'
    msg = f"Your offer for <b>{svc}</b> was declined."
    send_user_telegram(offer.provider_id, msg)


def notify_counter_offer(offer):
    """Provider receives: client sent a counter-offer."""
    req = offer.appointment_requests
    svc = req.service_name if req else 'Service'
    msg = (
        f"<b>Counter-offer received</b>\n\n"
        f"Request: {svc}\n"
        f"Your price: {offer.proposed_price:.2f} EUR\n"
        f"Client counter: {offer.counter_price:.2f} EUR\n\n"
        f"Open the app to respond."
    )
    send_user_telegram(offer.provider_id, msg)


def notify_status_change(user_id, service_name, old_status, new_status):
    """Notify user when appointment/request status changes."""
    msg = (
        f"<b>Status update</b>\n\n"
        f"<b>{service_name}</b>: {old_status} → <b>{new_status}</b>"
    )
    send_user_telegram(user_id, msg)


def notify_appointment_reminder(user_id, service_name, date_str, time_str):
    """Scheduled reminder about upcoming appointment."""
    msg = (
        f"<b>Reminder: Upcoming appointment</b>\n\n"
        f"Service: {service_name}\n"
        f"Date: {date_str}\n"
        f"Time: {time_str}\n\n"
        f"Don't forget to prepare!"
    )
    send_user_telegram(user_id, msg)
