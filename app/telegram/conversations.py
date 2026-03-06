"""
Multi-step conversation state machine for the Telegram bot.

Flows:
  - register:       new user picks role → email → username → account created
  - create_request: client creates a service request step by step
  - send_offer:     provider sends a price offer on an open request
"""
from datetime import datetime, timedelta
from app.extensions import db
from app.models import User, ClientSelfCreatedAppointment, RequestOfferResponse
import secrets


class ConversationManager:
    """In-memory state tracker for multi-step Telegram conversations."""

    def __init__(self):
        self._sessions = {}  # telegram_id -> {flow, step, data}

    def start(self, telegram_id, flow_name, initial_data=None):
        self._sessions[telegram_id] = {
            'flow': flow_name,
            'step': 0,
            'data': initial_data or {},
        }

    def is_active(self, telegram_id):
        return telegram_id in self._sessions

    def get(self, telegram_id):
        return self._sessions.get(telegram_id)

    def end(self, telegram_id):
        self._sessions.pop(telegram_id, None)

    def process(self, telegram_id, text, bot_token, chat_id):
        session = self._sessions.get(telegram_id)
        if not session:
            return

        if text == '/cancel':
            self.end(telegram_id)
            from .handlers import send_message
            send_message(bot_token, chat_id, "Cancelled. /help for commands.")
            return

        flow = session['flow']
        if flow == 'register':
            _process_register(self, telegram_id, text, bot_token, chat_id, session)
        elif flow == 'create_request':
            _process_create_request(self, telegram_id, text, bot_token, chat_id, session)
        elif flow == 'send_offer':
            _process_send_offer(self, telegram_id, text, bot_token, chat_id, session)

    def process_callback(self, telegram_id, data, bot_token, chat_id):
        """Handle inline button presses during a conversation."""
        session = self._sessions.get(telegram_id)
        if not session:
            return False

        if data == 'conv_confirm':
            self.process(telegram_id, '__confirm__', bot_token, chat_id)
            return True
        elif data == 'conv_cancel':
            self.end(telegram_id)
            from .handlers import send_message
            send_message(bot_token, chat_id, "Cancelled.")
            return True

        # Role selection during register flow
        if data.startswith('role_') and session['flow'] == 'register':
            role = data.replace('role_', '')
            self.process(telegram_id, role, bot_token, chat_id)
            return True

        return False


conversation_manager = ConversationManager()


# ── Register flow ──────────────────────────────────────────────────

def _process_register(cm, telegram_id, text, bot_token, chat_id, session):
    from .handlers import send_message
    from . import keyboards
    step = session['step']

    if step == 0:
        # Waiting for role selection
        if text not in ('client', 'provider'):
            send_message(bot_token, chat_id, "Please choose:", keyboards.role_select())
            return
        session['data']['role'] = text
        session['step'] = 1
        send_message(bot_token, chat_id,
                     "Enter your email (or type <b>skip</b>):")
        return

    if step == 1:
        # Email
        email = text.strip()
        if email.lower() == 'skip':
            email = f"tg_{telegram_id}@telegram.placeholder"
        elif '@' not in email or '.' not in email:
            send_message(bot_token, chat_id, "Invalid email. Try again or type <b>skip</b>:")
            return
        else:
            # Check if email already exists
            existing = User.query.filter_by(email=email).first()
            if existing:
                # Link telegram to existing account
                existing.telegram_id = telegram_id
                existing.telegram_notifications = True
                db.session.commit()
                cm.end(telegram_id)
                send_message(bot_token, chat_id,
                             f"Email found! Your Telegram is now linked to <b>@{existing.user_name}</b>.\n"
                             f"Role: {existing.role}\nUse /help for commands.")
                return

        session['data']['email'] = email
        session['step'] = 2
        send_message(bot_token, chat_id, "Choose a username:")
        return

    if step == 2:
        # Username
        username = text.strip()
        if len(username) < 2:
            send_message(bot_token, chat_id, "Username must be at least 2 characters:")
            return
        if User.query.filter_by(user_name=username).first():
            send_message(bot_token, chat_id, "Username taken. Try another:")
            return
        session['data']['username'] = username
        session['step'] = 3

        role = session['data']['role']
        email_display = session['data']['email']
        if email_display.endswith('@telegram.placeholder'):
            email_display = '(not set)'
        send_message(bot_token, chat_id,
                     f"<b>Confirm registration:</b>\n"
                     f"Role: {role}\n"
                     f"Email: {email_display}\n"
                     f"Username: {username}",
                     keyboards.confirm_cancel())
        return

    if step == 3:
        # Confirm
        if text != '__confirm__':
            send_message(bot_token, chat_id, "Press Confirm or Cancel.",
                         keyboards.confirm_cancel())
            return

        d = session['data']
        user = User(
            user_name=d['username'],
            email=d['email'],
            role=d['role'],
            telegram_id=telegram_id,
            telegram_notifications=True,
            password_hash=secrets.token_urlsafe(32),
            referral_code=secrets.token_urlsafe(6)[:8],
            terms_accepted=True,
        )
        db.session.add(user)
        db.session.commit()
        cm.end(telegram_id)

        menu = keyboards.client_menu() if d['role'] == 'client' else keyboards.provider_menu()
        send_message(bot_token, chat_id,
                     f"Account created! Welcome, <b>@{d['username']}</b> ({d['role']}).\n"
                     f"You can switch role anytime with /switch_role.\n"
                     f"Use /help for commands.",
                     menu)


# ── Create request flow (client) ──────────────────────────────────

def _process_create_request(cm, telegram_id, text, bot_token, chat_id, session):
    from .handlers import send_message
    from . import keyboards
    step = session['step']

    prompts = [
        "What service do you need?",
        "Describe what you need (or type <b>skip</b>):",
        "When? (format: <b>YYYY-MM-DD HH:MM</b>):",
        "Duration in minutes (e.g. 60):",
        "Address:",
        "Budget in EUR (0 = open/free):",
    ]
    keys = ['service_name', 'description', 'datetime', 'duration', 'address', 'budget']

    if step < len(prompts):
        # Validate specific steps
        if step == 2:
            # Parse datetime
            try:
                dt = datetime.strptime(text.strip(), '%Y-%m-%d %H:%M')
                if dt < datetime.now():
                    send_message(bot_token, chat_id, "Date must be in the future. Try again:")
                    return
                session['data']['datetime'] = dt
            except ValueError:
                send_message(bot_token, chat_id, "Invalid format. Use <b>YYYY-MM-DD HH:MM</b>:")
                return
        elif step == 3:
            try:
                dur = int(text.strip())
                if dur < 15 or dur > 480:
                    send_message(bot_token, chat_id, "Duration must be 15-480 minutes:")
                    return
                session['data']['duration'] = dur
            except ValueError:
                send_message(bot_token, chat_id, "Enter a number (minutes):")
                return
        elif step == 5:
            try:
                budget = float(text.strip())
                if budget < 0:
                    send_message(bot_token, chat_id, "Budget can't be negative:")
                    return
                session['data']['budget'] = budget
            except ValueError:
                send_message(bot_token, chat_id, "Enter a number:")
                return
        else:
            val = text.strip()
            if step == 1 and val.lower() == 'skip':
                val = ''
            session['data'][keys[step]] = val

        session['step'] += 1

        # If more prompts, show next one
        if session['step'] < len(prompts):
            send_message(bot_token, chat_id, prompts[session['step']])
            return

        # All info collected — show summary
        d = session['data']
        dt = d['datetime']
        session['step'] = len(prompts)  # summary step
        send_message(bot_token, chat_id,
                     f"<b>Your request:</b>\n\n"
                     f"Service: {d['service_name']}\n"
                     f"Description: {d.get('description') or '—'}\n"
                     f"Date: {dt.strftime('%d.%m.%Y %H:%M')}\n"
                     f"Duration: {d['duration']} min\n"
                     f"Address: {d['address']}\n"
                     f"Budget: {d['budget']:.2f} EUR",
                     keyboards.confirm_cancel())
        return

    # Confirmation step
    if text != '__confirm__':
        send_message(bot_token, chat_id, "Press Confirm or Cancel.",
                     keyboards.confirm_cancel())
        return

    user = User.query.filter_by(telegram_id=telegram_id).first()
    if not user:
        cm.end(telegram_id)
        send_message(bot_token, chat_id, "Error: account not found.")
        return

    d = session['data']
    dt = d['datetime']
    dur = d['duration']

    appt = ClientSelfCreatedAppointment(
        patient_id=user.id,
        appointment_start_time=dt,
        end_time=dt + timedelta(minutes=dur),
        status='pending',
        service_name=d['service_name'],
        service_description=d.get('description') or None,
        address=d['address'],
        payment=d['budget'],
        latitude=user.latitude,
        longitude=user.longitude,
    )
    db.session.add(appt)
    db.session.commit()
    cm.end(telegram_id)

    send_message(bot_token, chat_id,
                 f"Request <b>#{appt.id}</b> created!\n"
                 f"Providers near you will see it and send offers.")


# ── Send offer flow (provider) ────────────────────────────────────

def _process_send_offer(cm, telegram_id, text, bot_token, chat_id, session):
    from .handlers import send_message
    from . import keyboards
    step = session['step']

    if step == 0:
        # Waiting for price
        try:
            price = float(text.strip())
            if price < 0:
                send_message(bot_token, chat_id, "Price can't be negative:")
                return
            session['data']['price'] = price
        except ValueError:
            send_message(bot_token, chat_id, "Enter a price (number):")
            return

        req_id = session['data']['request_id']
        req = ClientSelfCreatedAppointment.query.get(req_id)
        svc = req.service_name if req else 'Service'

        session['step'] = 1
        send_message(bot_token, chat_id,
                     f"Send offer of <b>{price:.2f} EUR</b> for <b>{svc}</b>?",
                     keyboards.confirm_cancel())
        return

    if step == 1:
        if text != '__confirm__':
            send_message(bot_token, chat_id, "Press Confirm or Cancel.",
                         keyboards.confirm_cancel())
            return

        user = User.query.filter_by(telegram_id=telegram_id).first()
        if not user:
            cm.end(telegram_id)
            send_message(bot_token, chat_id, "Error: account not found.")
            return

        req_id = session['data']['request_id']
        price = session['data']['price']
        req = ClientSelfCreatedAppointment.query.get(req_id)

        if not req or req.status in ('completed', 'cancelled'):
            cm.end(telegram_id)
            send_message(bot_token, chat_id, "This request is no longer available.")
            return

        # Check if provider already sent an offer
        existing = RequestOfferResponse.query.filter_by(
            request_id=req_id, provider_id=user.id
        ).first()
        if existing:
            cm.end(telegram_id)
            send_message(bot_token, chat_id, "You already sent an offer for this request.")
            return

        offer = RequestOfferResponse(
            request_id=req_id,
            provider_id=user.id,
            proposed_price=price,
            status='pending',
        )
        db.session.add(offer)

        if req.status == 'pending':
            req.status = 'has_offers'

        db.session.commit()
        cm.end(telegram_id)

        # Notify client
        from .notifications import notify_new_offer
        try:
            notify_new_offer(req, offer)
        except Exception:
            pass

        send_message(bot_token, chat_id,
                     f"Offer of <b>{price:.2f} EUR</b> sent for <b>{req.service_name}</b>!")
