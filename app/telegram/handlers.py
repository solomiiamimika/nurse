"""
Telegram bot command handlers.

dispatch_update() is the single entry point called from the webhook.
"""
import time
import logging
import requests as http_requests
from flask import current_app
from app.extensions import db
from datetime import datetime, timedelta
from app.models import (
    User, Appointment, ClientSelfCreatedAppointment,
    RequestOfferResponse, ServiceHistory,
    NoShowRecord, Dispute,
)
from . import keyboards
from .conversations import conversation_manager

logger = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org/bot{token}"

MAX_RETRIES = 3
RETRY_BACKOFF = [1, 2, 4]


def telegram_api_request(method, token, payload, max_retries=MAX_RETRIES):
    """POST to Telegram Bot API with retry + exponential backoff."""
    url = f"{API_BASE.format(token=token)}/{method}"

    for attempt in range(max_retries):
        try:
            resp = http_requests.post(url, json=payload, timeout=10)
            if resp.ok:
                return resp.json()

            if resp.status_code == 429:
                retry_after = resp.json().get('parameters', {}).get('retry_after', 5)
                logger.warning("Rate limited by Telegram, retry after %ss", retry_after)
                time.sleep(retry_after)
                continue

            if 400 <= resp.status_code < 500:
                logger.error("Telegram API %s client error %s: %s",
                             method, resp.status_code, resp.text[:300])
                return None

            logger.warning("Telegram API %s server error %s (attempt %d/%d)",
                           method, resp.status_code, attempt + 1, max_retries)

        except http_requests.exceptions.Timeout:
            logger.warning("Telegram API %s timeout (attempt %d/%d)",
                           method, attempt + 1, max_retries)
        except Exception:
            logger.exception("Telegram API %s unexpected error (attempt %d/%d)",
                             method, attempt + 1, max_retries)

        if attempt < max_retries - 1:
            time.sleep(RETRY_BACKOFF[attempt])

    logger.error("Telegram API %s failed after %d attempts", method, max_retries)
    return None


def send_message(token, chat_id, text, reply_markup=None):
    payload = {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'}
    if reply_markup:
        payload['reply_markup'] = reply_markup
    return telegram_api_request('sendMessage', token, payload)


def answer_callback(token, callback_query_id, text=''):
    payload = {'callback_query_id': callback_query_id, 'text': text}
    return telegram_api_request('answerCallbackQuery', token, payload, max_retries=1)


# ── Dispatcher ─────────────────────────────────────────────────────

def dispatch_update(update, bot_token):
    """Route an incoming Telegram update to the correct handler."""
    try:
        if 'callback_query' in update:
            handle_callback_query(update['callback_query'], bot_token)
            return

        message = update.get('message')
        if not message:
            return

        chat = message.get('chat')
        from_user = message.get('from')
        if not chat or not from_user:
            logger.warning("Message without chat or from: update_id=%s", update.get('update_id'))
            return

        chat_id = chat['id']
        telegram_id = from_user['id']
        text = (message.get('text') or '').strip()

        # Check if user is in a multi-step conversation
        if conversation_manager.is_active(telegram_id):
            conversation_manager.process(telegram_id, text, bot_token, chat_id)
            return

        # Command routing
        commands = {
            '/start': handle_start,
            '/help': handle_help,
            '/cancel': handle_cancel,
            '/register': handle_register,
            '/appointments': handle_appointments,
            '/my_appointments': handle_appointments,
            '/create_request': handle_create_request,
            '/open_requests': handle_open_requests,
            '/my_offers': handle_my_offers,
            '/notifications': handle_notifications,
            '/link': handle_link,
            '/switch_role': handle_switch_role,
        }

        cmd = text.split()[0].lower() if text.startswith('/') else ''
        handler = commands.get(cmd)
        if handler:
            handler(telegram_id, chat_id, bot_token, message.get('from', {}))
        else:
            send_message(bot_token, chat_id, "Unknown command. /help for available commands.")

    except Exception:
        logger.exception("Unhandled error processing update_id=%s", update.get('update_id'))
        try:
            chat_id = (update.get('message') or
                       update.get('callback_query', {}).get('message', {})).get('chat', {}).get('id')
            if chat_id:
                send_message(bot_token, chat_id,
                             "Something went wrong. Please try again. /help for commands.")
        except Exception:
            logger.exception("Failed to send error message to user")


def handle_callback_query(cq, bot_token):
    """Handle inline button presses."""
    data = cq.get('data', '')
    cq_id = cq.get('id')

    # Always answer the callback query first
    if cq_id:
        answer_callback(bot_token, cq_id)

    message = cq.get('message')
    if not message or not message.get('chat'):
        logger.warning("Callback query without message/chat: %s", cq_id)
        return

    chat_id = message['chat']['id']
    from_user = cq.get('from')
    if not from_user:
        logger.warning("Callback query without from field: %s", cq_id)
        return

    telegram_id = from_user['id']

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
        'cmd_switch_role': handle_switch_role,
    }
    handler = cmd_map.get(data)
    if handler:
        handler(telegram_id, chat_id, bot_token, cq.get('from', {}))
        return

    # Toggle notifications
    if data == 'toggle_notifications':
        try:
            user = User.query.filter_by(telegram_id=telegram_id).first()
            if user:
                user.telegram_notifications = not user.telegram_notifications
                db.session.commit()
                status = 'ON' if user.telegram_notifications else 'OFF'
                send_message(bot_token, chat_id,
                             f"Notifications: <b>{status}</b>",
                             keyboards.notification_toggle(user.telegram_notifications))
        except Exception:
            logger.exception("Error toggling notifications for telegram_id=%s", telegram_id)
            send_message(bot_token, chat_id, "Something went wrong. Please try again.")
        return

    # Offer on a request
    if data.startswith('offer_req_'):
        try:
            req_id = int(data.replace('offer_req_', ''))
        except ValueError:
            logger.warning("Invalid offer callback data: %s", data)
            return
        try:
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
        except Exception:
            logger.exception("Error starting offer flow for telegram_id=%s", telegram_id)
            send_message(bot_token, chat_id, "Something went wrong. Please try again.")

    # Accept counter-offer
    if data.startswith('counter_accept_'):
        try:
            offer_id = int(data.replace('counter_accept_', ''))
        except ValueError:
            logger.warning("Invalid counter_accept callback data: %s", data)
            return
        try:
            user = User.query.filter_by(telegram_id=telegram_id).first()
            if not user:
                send_message(bot_token, chat_id, "Please /register or /link first.")
                return

            offer = RequestOfferResponse.query.filter_by(
                id=offer_id, provider_id=user.id
            ).first()
            if not offer or offer.status != 'pending':
                send_message(bot_token, chat_id, "Offer not found or already processed.")
                return
            if offer.counter_price is None:
                send_message(bot_token, chat_id, "No counter-offer to accept.")
                return

            offer.proposed_price = offer.counter_price
            offer.counter_price = None
            offer.last_action_by = 'provider'
            db.session.commit()

            req = offer.appointment_requests
            svc = req.service_name if req else 'Service'
            send_message(bot_token, chat_id,
                         f"Counter accepted! Price set to <b>{offer.proposed_price:.2f} EUR</b> for <b>{svc}</b>.\n"
                         f"Waiting for client to finalize.")

            # Notify client that provider accepted their counter
            try:
                from .notifications import send_user_telegram
                if req:
                    send_user_telegram(req.patient_id,
                                       f"<b>Your counter-offer was accepted!</b>\n\n"
                                       f"Service: {svc}\n"
                                       f"Agreed price: {offer.proposed_price:.2f} EUR")
            except Exception:
                logger.exception("Failed to notify client about accepted counter")

        except Exception:
            db.session.rollback()
            logger.exception("Error accepting counter for telegram_id=%s", telegram_id)
            send_message(bot_token, chat_id, "Something went wrong. Please try again.")

    # Revise price (counter to counter-offer)
    if data.startswith('counter_revise_'):
        try:
            offer_id = int(data.replace('counter_revise_', ''))
        except ValueError:
            logger.warning("Invalid counter_revise callback data: %s", data)
            return
        try:
            user = User.query.filter_by(telegram_id=telegram_id).first()
            if not user:
                send_message(bot_token, chat_id, "Please /register or /link first.")
                return

            offer = RequestOfferResponse.query.filter_by(
                id=offer_id, provider_id=user.id
            ).first()
            if not offer or offer.status != 'pending':
                send_message(bot_token, chat_id, "Offer not found or already processed.")
                return

            conversation_manager.start(telegram_id, 'revise_offer', {'offer_id': offer_id})
            req = offer.appointment_requests
            svc = req.service_name if req else 'Service'
            send_message(bot_token, chat_id,
                         f"Revising price for <b>{svc}</b>\n"
                         f"Client counter: {(offer.counter_price or 0):.2f} EUR\n\n"
                         f"Enter your new price:")
        except Exception:
            logger.exception("Error starting revise flow for telegram_id=%s", telegram_id)
            send_message(bot_token, chat_id, "Something went wrong. Please try again.")

    # ── Appointment action callbacks ──────────────────────────────
    if data.startswith('act_'):
        _handle_appointment_action(data, telegram_id, chat_id, bot_token)
        return


def _parse_action_target(data):
    """Parse 'act_<action>_<type>_<id>' → (action, type, id) or None."""
    parts = data.split('_', 3)  # act, action, type_id
    if len(parts) < 3:
        return None
    action = parts[1]
    rest = '_'.join(parts[2:])
    # rest = 'appt_123' or 'req_456' or 'arrive_appt_123' etc.
    # Some actions have multi-word: act_client_noshow_req_5 → need to handle
    # Format: act_<action>_<apptType>_<id>
    # actions: arrive, late, done, client_noshow, prov_noshow, complete, dispute
    # Let's re-parse from original data
    prefix = 'act_'
    rest_full = data[len(prefix):]
    # Find the appt/req type and id at the end
    for atype in ('appt', 'req'):
        marker = f'_{atype}_'
        idx = rest_full.rfind(marker)
        if idx >= 0:
            action_name = rest_full[:idx]
            try:
                obj_id = int(rest_full[idx + len(marker):])
                return action_name, atype, obj_id
            except ValueError:
                continue
    return None


def _get_appointment_or_request(atype, obj_id):
    """Get appointment or request by type and id."""
    if atype == 'appt':
        return Appointment.query.get(obj_id), 'appointment'
    else:
        return ClientSelfCreatedAppointment.query.get(obj_id), 'request'


def _handle_appointment_action(data, telegram_id, chat_id, bot_token):
    """Handle all appointment action callbacks."""
    from .notifications import send_user_telegram

    parsed = _parse_action_target(data)
    if not parsed:
        logger.warning("Could not parse action callback: %s", data)
        return

    action, atype, obj_id = parsed

    try:
        user = User.query.filter_by(telegram_id=telegram_id).first()
        if not user:
            send_message(bot_token, chat_id, "Please /register or /link first.")
            return

        obj, obj_label = _get_appointment_or_request(atype, obj_id)
        if not obj:
            send_message(bot_token, chat_id, f"Appointment not found.")
            return

        # Get service name and times
        if atype == 'appt':
            svc_name = obj.provider_service.name if obj.provider_service else 'Service'
            appt_time = obj.appointment_time
            client_id = obj.client_id
            provider_id = obj.provider_id
        else:
            svc_name = obj.service_name or 'Service'
            appt_time = obj.appointment_start_time
            client_id = obj.patient_id
            provider_id = obj.provider_id

        now = datetime.now()

        # ── Provider: Confirm Arrival ──
        if action == 'arrive':
            if user.id != provider_id:
                send_message(bot_token, chat_id, "Only the assigned provider can do this.")
                return
            if obj.status not in ('confirmed_paid', 'confirmed'):
                send_message(bot_token, chat_id, f"Cannot confirm arrival for status: {obj.status}")
                return

            obj.provider_arrived_at = now
            obj.status = 'in_progress'
            if hasattr(obj, 'previous_status'):
                obj.previous_status = 'confirmed_paid'
            db.session.commit()

            send_message(bot_token, chat_id, f"\u2705 Arrival confirmed for <b>{svc_name}</b>! Work is now in progress.")
            send_user_telegram(client_id,
                               f"<b>Provider has arrived!</b>\n\n"
                               f"Service: {svc_name}\n"
                               f"Work is now in progress.")
            return

        # ── Provider: Running Late ──
        if action == 'late':
            if user.id != provider_id:
                send_message(bot_token, chat_id, "Only the assigned provider can do this.")
                return
            # Start conversation to ask for minutes
            conversation_manager.start(telegram_id, 'report_late', {
                'atype': atype, 'obj_id': obj_id, 'svc_name': svc_name, 'client_id': client_id
            })
            send_message(bot_token, chat_id,
                         f"How many minutes will you be late for <b>{svc_name}</b>?\n"
                         f"Enter a number:")
            return

        # ── Provider: Mark Done ──
        if action == 'done':
            if user.id != provider_id:
                send_message(bot_token, chat_id, "Only the assigned provider can do this.")
                return
            if obj.status != 'in_progress':
                send_message(bot_token, chat_id, f"Cannot mark done for status: {obj.status}")
                return

            obj.status = 'work_submitted'
            obj.work_submitted_at = now
            db.session.commit()

            send_message(bot_token, chat_id,
                         f"\u2705 Work submitted for <b>{svc_name}</b>!\n"
                         f"Waiting for client approval.")
            send_user_telegram(client_id,
                               f"<b>Work completed!</b>\n\n"
                               f"Service: {svc_name}\n"
                               f"Please approve the work or report an issue.")
            return

        # ── Provider: Client No-Show ──
        if action == 'client_noshow':
            if user.id != provider_id:
                send_message(bot_token, chat_id, "Only the assigned provider can do this.")
                return
            if not appt_time or now < appt_time + timedelta(minutes=15):
                send_message(bot_token, chat_id, "You can report no-show only 15 minutes after the appointment time.")
                return

            # Record no-show
            record = NoShowRecord(
                reported_by_id=user.id,
                no_show_user_id=client_id,
                role='client',
                reason='Client did not show up',
            )
            if atype == 'appt':
                record.appointment_id = obj_id
            else:
                record.request_id = obj_id

            client = User.query.get(client_id)
            if client:
                client.no_show_count = (client.no_show_count or 0) + 1

            obj.status = 'no_show'
            db.session.add(record)
            db.session.commit()

            send_message(bot_token, chat_id,
                         f"\U0001f6ab Client no-show recorded for <b>{svc_name}</b>.")
            send_user_telegram(client_id,
                               f"<b>No-show recorded</b>\n\n"
                               f"You were marked as no-show for: {svc_name}\n"
                               f"If this is a mistake, please contact support.")
            return

        # ── Client: Provider No-Show ──
        if action == 'prov_noshow':
            if user.id != client_id:
                send_message(bot_token, chat_id, "Only the client can do this.")
                return
            if not appt_time or now < appt_time + timedelta(minutes=15):
                send_message(bot_token, chat_id, "You can report no-show only 15 minutes after the appointment time.")
                return

            record = NoShowRecord(
                reported_by_id=user.id,
                no_show_user_id=provider_id,
                role='provider',
                reason='Provider did not show up',
            )
            if atype == 'appt':
                record.appointment_id = obj_id
            else:
                record.request_id = obj_id

            provider = User.query.get(provider_id)
            if provider:
                provider.no_show_count = (provider.no_show_count or 0) + 1

            obj.status = 'no_show'
            db.session.add(record)
            db.session.commit()

            send_message(bot_token, chat_id,
                         f"\U0001f6ab Provider no-show recorded for <b>{svc_name}</b>.\n"
                         f"Any pre-authorized payment will be refunded.")
            send_user_telegram(provider_id,
                               f"<b>No-show recorded</b>\n\n"
                               f"You were marked as no-show for: {svc_name}\n"
                               f"If this is a mistake, please contact support.")
            return

        # ── Client: Approve & Complete ──
        if action == 'complete':
            if user.id != client_id:
                send_message(bot_token, chat_id, "Only the client can do this.")
                return
            if obj.status != 'work_submitted':
                send_message(bot_token, chat_id, f"Cannot complete for status: {obj.status}")
                return

            obj.status = 'completed'
            db.session.commit()

            send_message(bot_token, chat_id,
                         f"\u2705 <b>{svc_name}</b> marked as completed! Thank you.")
            send_user_telegram(provider_id,
                               f"<b>Work approved!</b>\n\n"
                               f"Service: {svc_name}\n"
                               f"The client has approved your work. Payment will be released.")
            return

        # ── Client: Report Issue (Dispute) ──
        if action == 'dispute':
            if user.id != client_id:
                send_message(bot_token, chat_id, "Only the client can do this.")
                return
            if obj.status not in ('work_submitted', 'completed'):
                send_message(bot_token, chat_id, f"Cannot report issue for status: {obj.status}")
                return

            # Start conversation to collect dispute details
            conversation_manager.start(telegram_id, 'create_dispute', {
                'atype': atype, 'obj_id': obj_id, 'svc_name': svc_name, 'provider_id': provider_id
            })
            send_message(bot_token, chat_id,
                         f"What is the issue with <b>{svc_name}</b>?\n\n"
                         f"1. Not completed\n"
                         f"2. Quality issue\n"
                         f"3. Other\n\n"
                         f"Enter 1, 2, or 3:")
            return

        send_message(bot_token, chat_id, "Unknown action.")

    except Exception:
        db.session.rollback()
        logger.exception("Error handling action %s for telegram_id=%s", data, telegram_id)
        send_message(bot_token, chat_id, "Something went wrong. Please try again.")


# ── Command handlers ───────────────────────────────────────────────

def handle_cancel(telegram_id, chat_id, bot_token, from_data):
    if conversation_manager.is_active(telegram_id):
        conversation_manager.end(telegram_id)
        send_message(bot_token, chat_id, "Cancelled. /help for commands.")
    else:
        send_message(bot_token, chat_id, "Nothing to cancel. /help for commands.")


def handle_start(telegram_id, chat_id, bot_token, from_data):
    try:
        user = User.query.filter_by(telegram_id=telegram_id).first()
        first_name = from_data.get('first_name', '')

        if user:
            role_label = 'Client' if user.role == 'client' else 'Provider'
            menu = keyboards.main_menu(user.role)
            send_message(bot_token, chat_id,
                         f"Welcome back, <b>{user.full_name or user.user_name}</b>!\n"
                         f"Role: <b>{role_label}</b>\n\n"
                         f"Choose an action:",
                         menu)
        else:
            send_message(bot_token, chat_id,
                         f"Hello, <b>{first_name}</b>! Welcome to Human-me.\n\n"
                         f"Find help or offer your services — all in one place.\n\n"
                         f"To get started, register or link your existing account:",
                         keyboards.unregistered_menu())
    except Exception:
        logger.exception("Error in handle_start for telegram_id=%s", telegram_id)
        send_message(bot_token, chat_id, "Something went wrong. Please try again.")


def handle_help(telegram_id, chat_id, bot_token, from_data):
    try:
        user = User.query.filter_by(telegram_id=telegram_id).first()

        if not user:
            send_message(bot_token, chat_id,
                         "<b>Available commands:</b>\n\n"
                         "/register — Create account\n"
                         "/link — Link existing account\n"
                         "/cancel — Cancel current operation\n"
                         "/help — This message",
                         keyboards.unregistered_menu())
            return

        role_label = 'Client' if user.role == 'client' else 'Provider'
        base = (
            f"<b>You are logged in as {role_label}</b>\n\n"
            "/appointments — Your upcoming appointments\n"
            "/notifications — Toggle notifications\n"
        )
        if user.role == 'client':
            base += "/create_request — Post a new service request\n"
        elif user.role == 'provider':
            base += (
                "/open_requests — Browse open requests\n"
                "/my_offers — View your sent offers\n"
            )
        base += "/switch_role — Switch between Client / Provider\n"
        base += "/cancel — Cancel current operation\n"
        base += "/help — This message"

        menu = keyboards.main_menu(user.role)
        send_message(bot_token, chat_id, base, menu)
    except Exception:
        logger.exception("Error in handle_help for telegram_id=%s", telegram_id)
        send_message(bot_token, chat_id, "Something went wrong. Please try again.")


def handle_register(telegram_id, chat_id, bot_token, from_data):
    try:
        user = User.query.filter_by(telegram_id=telegram_id).first()
        if user:
            send_message(bot_token, chat_id,
                         f"You already have an account: <b>@{user.user_name}</b>")
            return

        conversation_manager.start(telegram_id, 'register')
        send_message(bot_token, chat_id,
                     "Let's create your account!\n\nAre you a <b>Client</b> or a <b>Provider</b>?",
                     keyboards.role_select())
    except Exception:
        logger.exception("Error in handle_register for telegram_id=%s", telegram_id)
        send_message(bot_token, chat_id, "Something went wrong. Please try again.")


def handle_link(telegram_id, chat_id, bot_token, from_data):
    try:
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
    except Exception:
        logger.exception("Error in handle_link for telegram_id=%s", telegram_id)
        send_message(bot_token, chat_id, "Something went wrong. Please try again.")


def _status_label(status):
    """Human-readable status label."""
    labels = {
        'pending': 'Pending',
        'scheduled': 'Pending',
        'has_offers': 'Has Offers',
        'confirmed': 'Accepted',
        'confirmed_paid': 'Paid',
        'in_progress': 'In Progress',
        'work_submitted': 'Work Submitted',
        'completed': 'Completed',
        'cancelled': 'Cancelled',
        'no_show': 'No-Show',
        'disputed': 'Disputed',
    }
    return labels.get(status, status)


def _is_no_show_eligible(appt_time):
    """True if appointment time + 15 min has passed."""
    if not appt_time:
        return False
    return datetime.now() >= appt_time + timedelta(minutes=15)


def handle_appointments(telegram_id, chat_id, bot_token, from_data):
    try:
        user = User.query.filter_by(telegram_id=telegram_id).first()
        if not user:
            send_message(bot_token, chat_id, "Please /register or /link first.")
            return

        now = datetime.now()

        if user.role == 'client':
            appts = Appointment.query.filter(
                Appointment.client_id == user.id,
                Appointment.appointment_time >= now - timedelta(hours=24),
                Appointment.status.notin_(['cancelled', 'completed', 'no_show']),
            ).order_by(Appointment.appointment_time).limit(10).all()

            reqs = ClientSelfCreatedAppointment.query.filter(
                ClientSelfCreatedAppointment.patient_id == user.id,
                ClientSelfCreatedAppointment.appointment_start_time >= now - timedelta(hours=24),
                ClientSelfCreatedAppointment.status.notin_(['cancelled', 'completed', 'no_show']),
            ).order_by(ClientSelfCreatedAppointment.appointment_start_time).limit(10).all()

        else:  # provider
            appts = Appointment.query.filter(
                Appointment.provider_id == user.id,
                Appointment.appointment_time >= now - timedelta(hours=24),
                Appointment.status.notin_(['cancelled', 'completed', 'no_show']),
            ).order_by(Appointment.appointment_time).limit(10).all()

            reqs = ClientSelfCreatedAppointment.query.filter(
                ClientSelfCreatedAppointment.provider_id == user.id,
                ClientSelfCreatedAppointment.appointment_start_time >= now - timedelta(hours=24),
                ClientSelfCreatedAppointment.status.notin_(['cancelled', 'completed', 'no_show']),
            ).order_by(ClientSelfCreatedAppointment.appointment_start_time).limit(10).all()

        if not appts and not reqs:
            send_message(bot_token, chat_id, "No upcoming appointments.")
            return

        # Send each appointment as a separate message with action buttons
        for a in appts:
            dt = a.appointment_time.strftime('%d.%m.%Y %H:%M')
            svc = a.provider_service.name if a.provider_service else 'Service'
            late_info = f"\n\u23f0 Late by {a.provider_late_minutes} min" if a.provider_late_minutes else ''
            text = (
                f"<b>{svc}</b>\n"
                f"Date: {dt}\n"
                f"Status: {_status_label(a.status)}{late_info}"
            )
            no_show_ok = _is_no_show_eligible(a.appointment_time)
            if user.role == 'provider':
                kb = keyboards.provider_appointment_actions(a.id, 'appt', a.status, no_show_ok)
            else:
                kb = keyboards.client_appointment_actions(a.id, 'appt', a.status, no_show_ok)
            send_message(bot_token, chat_id, text, kb)

        for r in reqs:
            dt = r.appointment_start_time.strftime('%d.%m.%Y %H:%M')
            svc = r.service_name or 'Request'
            late_info = f"\n\u23f0 Late by {r.provider_late_minutes} min" if r.provider_late_minutes else ''
            text = (
                f"<b>{svc}</b>\n"
                f"Date: {dt}\n"
                f"Status: {_status_label(r.status)}{late_info}"
            )
            no_show_ok = _is_no_show_eligible(r.appointment_start_time)
            if user.role == 'provider':
                kb = keyboards.provider_appointment_actions(r.id, 'req', r.status, no_show_ok)
            else:
                kb = keyboards.client_appointment_actions(r.id, 'req', r.status, no_show_ok)
            send_message(bot_token, chat_id, text, kb)

    except Exception:
        logger.exception("Error in handle_appointments for telegram_id=%s", telegram_id)
        send_message(bot_token, chat_id, "Something went wrong. Please try again.")


def handle_create_request(telegram_id, chat_id, bot_token, from_data):
    try:
        user = User.query.filter_by(telegram_id=telegram_id).first()
        if not user:
            send_message(bot_token, chat_id, "Please /register or /link first.")
            return
        if user.role != 'client':
            send_message(bot_token, chat_id, "Only clients can create requests.")
            return

        conversation_manager.start(telegram_id, 'create_request')
        send_message(bot_token, chat_id, "What service do you need?")
    except Exception:
        logger.exception("Error in handle_create_request for telegram_id=%s", telegram_id)
        send_message(bot_token, chat_id, "Something went wrong. Please try again.")


def handle_open_requests(telegram_id, chat_id, bot_token, from_data):
    try:
        user = User.query.filter_by(telegram_id=telegram_id).first()
        if not user:
            send_message(bot_token, chat_id, "Please /register or /link first.")
            return
        if user.role != 'provider':
            send_message(bot_token, chat_id, "Only providers can browse requests.")
            return

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
            area = r.district or '—'
            text = (
                f"<b>{r.service_name or 'Request'}</b>\n"
                f"Date: {dt}\n"
                f"Budget: {budget}\n"
                f"Area: {area}"
            )
            send_message(bot_token, chat_id, text, keyboards.offer_button(r.id))
    except Exception:
        logger.exception("Error in handle_open_requests for telegram_id=%s", telegram_id)
        send_message(bot_token, chat_id, "Something went wrong. Please try again.")


def handle_my_offers(telegram_id, chat_id, bot_token, from_data):
    try:
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
    except Exception:
        logger.exception("Error in handle_my_offers for telegram_id=%s", telegram_id)
        send_message(bot_token, chat_id, "Something went wrong. Please try again.")


def handle_notifications(telegram_id, chat_id, bot_token, from_data):
    try:
        user = User.query.filter_by(telegram_id=telegram_id).first()
        if not user:
            send_message(bot_token, chat_id, "Please /register or /link first.")
            return

        status = 'ON' if user.telegram_notifications else 'OFF'
        send_message(bot_token, chat_id,
                     f"Notifications are currently <b>{status}</b>.",
                     keyboards.notification_toggle(user.telegram_notifications))
    except Exception:
        logger.exception("Error in handle_notifications for telegram_id=%s", telegram_id)
        send_message(bot_token, chat_id, "Something went wrong. Please try again.")


def handle_switch_role(telegram_id, chat_id, bot_token, from_data):
    try:
        user = User.query.filter_by(telegram_id=telegram_id).first()
        if not user:
            send_message(bot_token, chat_id, "Please /register or /link first.")
            return

        new_role = 'provider' if user.role == 'client' else 'client'
        user.role = new_role
        db.session.commit()

        menu = keyboards.main_menu(new_role)
        send_message(bot_token, chat_id,
                     f"Role switched to <b>{new_role}</b>!",
                     menu)
    except Exception:
        logger.exception("Error in handle_switch_role for telegram_id=%s", telegram_id)
        send_message(bot_token, chat_id, "Something went wrong. Please try again.")
