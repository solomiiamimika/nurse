"""
Telegram notifications to individual users.

send_user_telegram()  — low-level: send a message to a user by user_id
notify_*()            — high-level: event-based notifications
"""
import logging
from threading import Thread
from flask import current_app

logger = logging.getLogger(__name__)


def _send_raw(token, chat_id, text, reply_markup=None):
    """Send a Telegram message (blocking, with retry). Used in threads."""
    from .handlers import telegram_api_request
    payload = {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'}
    if reply_markup:
        payload['reply_markup'] = reply_markup
    result = telegram_api_request('sendMessage', token, payload)
    if result is None:
        logger.error("Failed to deliver notification to chat_id=%s", chat_id)


def send_user_telegram(user_id, message, reply_markup=None):
    """
    Send a Telegram message to a user (non-blocking).
    Checks that user has telegram_id and notifications enabled.
    """
    from app.models import User
    token = current_app.config.get('TELEGRAM_BOT_TOKEN')
    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN not configured, skipping notification")
        return

    user = User.query.get(user_id)
    if not user:
        logger.warning("Notification skipped: user_id=%s not found", user_id)
        return
    if not user.telegram_id:
        return
    if not user.telegram_notifications:
        return

    tg_id = user.telegram_id
    user_name = user.user_name

    def _send():
        try:
            _send_raw(token, tg_id, message, reply_markup)
            logger.info("Notification sent to %s (telegram_id=%s)", user_name, tg_id)
        except Exception:
            logger.exception("Failed to send notification to %s (telegram_id=%s)",
                             user_name, tg_id)

    Thread(target=_send, daemon=True, name=f"tg-notify-{user_id}").start()


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
    """Provider receives: client sent a counter-offer (with inline buttons)."""
    from . import keyboards
    req = offer.appointment_requests
    svc = req.service_name if req else 'Service'
    msg = (
        f"<b>Counter-offer received</b>\n\n"
        f"Request: {svc}\n"
        f"Your price: {offer.proposed_price:.2f} EUR\n"
        f"Client counter: {offer.counter_price:.2f} EUR\n\n"
        f"Accept or revise below:"
    )
    send_user_telegram(offer.provider_id, msg,
                       reply_markup=keyboards.counter_offer_response(offer.id))


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


def notify_provider_arrived(client_id, service_name):
    """Client receives: provider has arrived and started work."""
    msg = (
        f"<b>Provider has arrived!</b>\n\n"
        f"Service: {service_name}\n"
        f"Work is now in progress."
    )
    send_user_telegram(client_id, msg)


def notify_provider_late(client_id, service_name, minutes):
    """Client receives: provider is running late."""
    msg = (
        f"<b>Provider is running late</b>\n\n"
        f"Service: {service_name}\n"
        f"Estimated delay: ~{minutes} minutes"
    )
    send_user_telegram(client_id, msg)


def notify_work_submitted(client_id, service_name):
    """Client receives: provider submitted work for approval."""
    msg = (
        f"<b>Work completed!</b>\n\n"
        f"Service: {service_name}\n"
        f"Please approve the work or report an issue.\n"
        f"Auto-approved in 48 hours if no action taken."
    )
    send_user_telegram(client_id, msg)


def notify_work_approved(provider_id, service_name):
    """Provider receives: client approved their work."""
    msg = (
        f"<b>Work approved!</b>\n\n"
        f"Service: {service_name}\n"
        f"Payment will be released shortly."
    )
    send_user_telegram(provider_id, msg)


def notify_no_show(user_id, service_name, role):
    """User receives: they were marked as no-show."""
    msg = (
        f"<b>No-show recorded</b>\n\n"
        f"You were marked as no-show for: {service_name}\n"
        f"If this is a mistake, please contact support."
    )
    send_user_telegram(user_id, msg)


def notify_dispute_created(provider_id, service_name, reason):
    """Provider receives: client created a dispute."""
    reason_labels = {
        'not_completed': 'Not completed',
        'quality_issue': 'Quality issue',
        'other': 'Other',
    }
    msg = (
        f"<b>Dispute reported</b>\n\n"
        f"Service: {service_name}\n"
        f"Reason: {reason_labels.get(reason, reason)}\n"
        f"The platform team will review this case."
    )
    send_user_telegram(provider_id, msg)


def notify_dispute_resolved(user_id, service_name, resolution):
    """User receives: dispute has been resolved."""
    msg = (
        f"<b>Dispute resolved</b>\n\n"
        f"Service: {service_name}\n"
        f"Resolution: {resolution}\n"
        f"If you have questions, please contact support."
    )
    send_user_telegram(user_id, msg)
