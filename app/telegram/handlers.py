"""
Telegram bot command handlers.

dispatch_update() is the single entry point called from the webhook.
"""
import requests as http_requests
from flask import current_app
from app.extensions import db
from app.models import (
    User, Appointment, ClientSelfCreatedAppointment,
    RequestOfferResponse, ServiceHistory,
)
from . import keyboards
from .conversations import conversation_manager

API_BASE = "https://api.telegram.org/bot{token}"


def send_message(token, chat_id, text, reply_markup=None):
    url = f"{API_BASE.format(token=token)}/sendMessage"
    payload = {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'}
    if reply_markup:
        payload['reply_markup'] = reply_markup
    try:
        http_requests.post(url, json=payload, timeout=5)
    except Exception:
        pass


def answer_callback(token, callback_query_id, text=''):
    url = f"{API_BASE.format(token=token)}/answerCallbackQuery"
    try:
        http_requests.post(url, json={
            'callback_query_id': callback_query_id, 'text': text
        }, timeout=5)
    except Exception:
        pass


# ── Dispatcher ─────────────────────────────────────────────────────

def dispatch_update(update, bot_token):
    """Route an incoming Telegram update to the correct handler."""

    if 'callback_query' in update:
        handle_callback_query(update['callback_query'], bot_token)
        return

    message = update.get('message')
    if not message:
        return

    chat_id = message['chat']['id']
    text = (message.get('text') or '').strip()
    telegram_id = message['from']['id']

    # Check if user is in a multi-step conversation
    if conversation_manager.is_active(telegram_id):
        conversation_manager.process(telegram_id, text, bot_token, chat_id)
        return

    # Command routing
    commands = {
        '/start': handle_start,
        '/help': handle_help,
        '/register': handle_register,
        '/appointments': handle_appointments,
        '/my_appointments': handle_appointments,
        '/create_request': handle_create_request,
        '/open_requests': handle_open_requests,
        '/my_offers': handle_my_offers,
        '/notifications': handle_notifications,
        '/link': handle_link,
    }

    cmd = text.split()[0].lower() if text.startswith('/') else ''
    handler = commands.get(cmd)
    if handler:
        handler(telegram_id, chat_id, bot_token, message.get('from', {}))
    else:
        send_message(bot_token, chat_id, "Unknown command. /help for available commands.")


def handle_callback_query(cq, bot_token):
    """Handle inline button presses."""
    data = cq.get('data', '')
    chat_id = cq['message']['chat']['id']
    telegram_id = cq['from']['id']
    cq_id = cq['id']

    answer_callback(bot_token, cq_id)

    # Check if conversation wants to handle it
    if conversation_manager.is_active(telegram_id):
        if conversation_manager.process_callback(telegram_id, data, bot_token, chat_id):
            return

    # Menu commands
    cmd_map = {
        'cmd_appointments': handle_appointments,
        'cmd_create_request': handle_create_request,
        'cmd_open_requests': handle_open_requests,
        'cmd_my_offers': handle_my_offers,
        'cmd_notifications': handle_notifications,
        'cmd_register': handle_register,
        'cmd_link': handle_link,
    }
    handler = cmd_map.get(data)
    if handler:
        handler(telegram_id, chat_id, bot_token, cq.get('from', {}))
        return

    # Toggle notifications
    if data == 'toggle_notifications':
        user = User.query.filter_by(telegram_id=telegram_id).first()
        if user:
            user.telegram_notifications = not user.telegram_notifications
            db.session.commit()
            status = 'ON' if user.telegram_notifications else 'OFF'
            send_message(bot_token, chat_id,
                         f"Notifications: <b>{status}</b>",
                         keyboards.notification_toggle(user.telegram_notifications))
        return

    # Offer on a request
    if data.startswith('offer_req_'):
        req_id = int(data.replace('offer_req_', ''))
        user = User.query.filter_by(telegram_id=telegram_id).first()
        if not user or user.role != 'provider':
            send_message(bot_token, chat_id, "Only providers can send offers.")
            return
        req = ClientSelfCreatedAppointment.query.get(req_id)
        if not req or req.status in ('completed', 'cancelled'):
            send_message(bot_token, chat_id, "This request is no longer available.")
            return
        conversation_manager.start(telegram_id, 'send_offer', {'request_id': req_id})
        send_message(bot_token, chat_id,
                     f"Sending offer for <b>{req.service_name}</b>\n"
                     f"Budget: {(req.payment or 0):.2f} EUR\n\n"
                     f"Enter your proposed price:")


# ── Command handlers ───────────────────────────────────────────────

def handle_start(telegram_id, chat_id, bot_token, from_data):
    user = User.query.filter_by(telegram_id=telegram_id).first()
    first_name = from_data.get('first_name', '')

    if user:
        menu = keyboards.main_menu(user.role)
        send_message(bot_token, chat_id,
                     f"Welcome back, <b>{user.full_name or user.user_name}</b>! ({user.role})",
                     menu)
    else:
        send_message(bot_token, chat_id,
                     f"Hello, {first_name}! Welcome to the platform.\n\n"
                     f"You don't have an account yet.\n"
                     f"/register — Create a new account\n"
                     f"/link — Link an existing account",
                     keyboards.unregistered_menu())


def handle_help(telegram_id, chat_id, bot_token, from_data):
    user = User.query.filter_by(telegram_id=telegram_id).first()

    if not user:
        send_message(bot_token, chat_id,
                     "<b>Available commands:</b>\n"
                     "/register — Create account\n"
                     "/link — Link existing account\n"
                     "/help — This message")
        return

    base = (
        "<b>Available commands:</b>\n"
        "/appointments — Your upcoming appointments\n"
        "/notifications — Toggle Telegram notifications\n"
    )
    if user.role == 'client':
        base += "/create_request — Post a new service request\n"
    elif user.role == 'provider':
        base += (
            "/open_requests — Browse open requests nearby\n"
            "/my_offers — View your sent offers\n"
        )
    base += "/help — This message"
    send_message(bot_token, chat_id, base)


def handle_register(telegram_id, chat_id, bot_token, from_data):
    user = User.query.filter_by(telegram_id=telegram_id).first()
    if user:
        send_message(bot_token, chat_id,
                     f"You already have an account: <b>@{user.user_name}</b>")
        return

    conversation_manager.start(telegram_id, 'register')
    send_message(bot_token, chat_id,
                 "Let's create your account!\n\nAre you a <b>Client</b> or a <b>Provider</b>?",
                 keyboards.role_select())


def handle_link(telegram_id, chat_id, bot_token, from_data):
    user = User.query.filter_by(telegram_id=telegram_id).first()
    if user:
        send_message(bot_token, chat_id,
                     f"Already linked to <b>@{user.user_name}</b>")
        return

    base_url = current_app.config.get('BASE_URL', '')
    link_url = f"{base_url}/telegram/link?tg_id={telegram_id}"
    send_message(bot_token, chat_id,
                 f"Open this link to log into your account and link Telegram:\n\n"
                 f"{link_url}\n\n"
                 f"After linking, come back here and type /start.")


def handle_appointments(telegram_id, chat_id, bot_token, from_data):
    user = User.query.filter_by(telegram_id=telegram_id).first()
    if not user:
        send_message(bot_token, chat_id, "Please /register or /link first.")
        return

    from datetime import datetime
    now = datetime.now()

    if user.role == 'client':
        # Direct appointments
        appts = Appointment.query.filter(
            Appointment.client_id == user.id,
            Appointment.appointment_time >= now,
            Appointment.status.notin_(['cancelled', 'completed']),
        ).order_by(Appointment.appointment_time).limit(10).all()

        # Request-based
        reqs = ClientSelfCreatedAppointment.query.filter(
            ClientSelfCreatedAppointment.patient_id == user.id,
            ClientSelfCreatedAppointment.appointment_start_time >= now,
            ClientSelfCreatedAppointment.status.notin_(['cancelled', 'completed']),
        ).order_by(ClientSelfCreatedAppointment.appointment_start_time).limit(10).all()

    else:  # provider
        appts = Appointment.query.filter(
            Appointment.provider_id == user.id,
            Appointment.appointment_time >= now,
            Appointment.status.notin_(['cancelled', 'completed']),
        ).order_by(Appointment.appointment_time).limit(10).all()

        reqs = ClientSelfCreatedAppointment.query.filter(
            ClientSelfCreatedAppointment.provider_id == user.id,
            ClientSelfCreatedAppointment.appointment_start_time >= now,
            ClientSelfCreatedAppointment.status.notin_(['cancelled', 'completed']),
        ).order_by(ClientSelfCreatedAppointment.appointment_start_time).limit(10).all()

    if not appts and not reqs:
        send_message(bot_token, chat_id, "No upcoming appointments.")
        return

    lines = ["<b>Upcoming appointments:</b>\n"]
    for a in appts:
        dt = a.appointment_time.strftime('%d.%m.%Y %H:%M')
        svc = a.provider_service.name if a.provider_service else 'Service'
        lines.append(f"• {svc} — {dt} [{a.status}]")

    for r in reqs:
        dt = r.appointment_start_time.strftime('%d.%m.%Y %H:%M')
        lines.append(f"• {r.service_name or 'Request'} — {dt} [{r.status}]")

    send_message(bot_token, chat_id, "\n".join(lines))


def handle_create_request(telegram_id, chat_id, bot_token, from_data):
    user = User.query.filter_by(telegram_id=telegram_id).first()
    if not user:
        send_message(bot_token, chat_id, "Please /register or /link first.")
        return
    if user.role != 'client':
        send_message(bot_token, chat_id, "Only clients can create requests.")
        return

    conversation_manager.start(telegram_id, 'create_request')
    send_message(bot_token, chat_id, "What service do you need?")


def handle_open_requests(telegram_id, chat_id, bot_token, from_data):
    user = User.query.filter_by(telegram_id=telegram_id).first()
    if not user:
        send_message(bot_token, chat_id, "Please /register or /link first.")
        return
    if user.role != 'provider':
        send_message(bot_token, chat_id, "Only providers can browse requests.")
        return

    from datetime import datetime
    now = datetime.now()

    reqs = ClientSelfCreatedAppointment.query.filter(
        ClientSelfCreatedAppointment.status.in_(['pending', 'has_offers']),
        ClientSelfCreatedAppointment.appointment_start_time >= now,
    ).order_by(ClientSelfCreatedAppointment.appointment_start_time).limit(15).all()

    if not reqs:
        send_message(bot_token, chat_id, "No open requests right now.")
        return

    for r in reqs:
        dt = r.appointment_start_time.strftime('%d.%m.%Y %H:%M')
        budget = f"{(r.payment or 0):.2f} EUR" if r.payment else 'Open'
        text = (
            f"<b>{r.service_name or 'Request'}</b>\n"
            f"Date: {dt}\n"
            f"Budget: {budget}\n"
            f"Address: {r.address or '—'}"
        )
        send_message(bot_token, chat_id, text, keyboards.offer_button(r.id))


def handle_my_offers(telegram_id, chat_id, bot_token, from_data):
    user = User.query.filter_by(telegram_id=telegram_id).first()
    if not user:
        send_message(bot_token, chat_id, "Please /register or /link first.")
        return
    if user.role != 'provider':
        send_message(bot_token, chat_id, "Only providers have offers.")
        return

    offers = RequestOfferResponse.query.filter_by(
        provider_id=user.id
    ).order_by(RequestOfferResponse.created_at.desc()).limit(10).all()

    if not offers:
        send_message(bot_token, chat_id, "No offers sent yet.")
        return

    lines = ["<b>Your offers:</b>\n"]
    for o in offers:
        req = o.appointment_requests
        svc = req.service_name if req else 'Service'
        lines.append(f"• {svc} — {o.proposed_price:.2f} EUR [{o.status}]")

    send_message(bot_token, chat_id, "\n".join(lines))


def handle_notifications(telegram_id, chat_id, bot_token, from_data):
    user = User.query.filter_by(telegram_id=telegram_id).first()
    if not user:
        send_message(bot_token, chat_id, "Please /register or /link first.")
        return

    status = 'ON' if user.telegram_notifications else 'OFF'
    send_message(bot_token, chat_id,
                 f"Notifications are currently <b>{status}</b>.",
                 keyboards.notification_toggle(user.telegram_notifications))
