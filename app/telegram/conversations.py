"""
Multi-step conversation state machine for the Telegram bot.

State is persisted to the database (TelegramSession model)
so conversations survive server restarts.

Flows:
  - register:       new user picks role → email → username → account created
  - create_request: client creates a service request step by step
  - send_offer:     provider sends a price offer on an open request
"""
import re
import logging
from datetime import datetime, timedelta
from app.extensions import db
from app.models import User, ClientSelfCreatedAppointment, RequestOfferResponse
from app.models.telegram_session import TelegramSession
import secrets

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
USERNAME_RE = re.compile(r'^[a-zA-Z0-9_.\-]{2,30}$')

SESSION_TIMEOUT_MINUTES = 30


class ConversationManager:
    """DB-backed state tracker for multi-step Telegram conversations."""

    def start(self, telegram_id, flow_name, initial_data=None):
        try:
            TelegramSession.query.filter_by(telegram_id=telegram_id).delete()
            session = TelegramSession(
                telegram_id=telegram_id,
                flow=flow_name,
                step=0,
            )
            session.data = initial_data or {}
            db.session.add(session)
            db.session.commit()
            logger.info("Started flow=%s for telegram_id=%s", flow_name, telegram_id)
        except Exception:
            db.session.rollback()
            logger.exception("Failed to start conversation for telegram_id=%s", telegram_id)

    def is_active(self, telegram_id):
        return TelegramSession.query.filter_by(telegram_id=telegram_id).first() is not None

    def get(self, telegram_id):
        ts = TelegramSession.query.filter_by(telegram_id=telegram_id).first()
        if not ts:
            return None
        return {'flow': ts.flow, 'step': ts.step, 'data': ts.data}

    def _save(self, telegram_id, session_dict):
        ts = TelegramSession.query.filter_by(telegram_id=telegram_id).first()
        if ts:
            ts.step = session_dict['step']
            ts.data = session_dict['data']
            ts.updated_at = datetime.utcnow()
            db.session.commit()

    def end(self, telegram_id):
        try:
            TelegramSession.query.filter_by(telegram_id=telegram_id).delete()
            db.session.commit()
            logger.info("Ended conversation for telegram_id=%s", telegram_id)
        except Exception:
            db.session.rollback()
            logger.exception("Failed to end conversation for telegram_id=%s", telegram_id)

    def process(self, telegram_id, text, bot_token, chat_id):
        from .handlers import send_message

        # Check for timeout
        ts = TelegramSession.query.filter_by(telegram_id=telegram_id).first()
        if not ts:
            return
        if ts.updated_at and datetime.utcnow() - ts.updated_at > timedelta(minutes=SESSION_TIMEOUT_MINUTES):
            self.end(telegram_id)
            send_message(bot_token, chat_id,
                         "Your session expired. Please start again. /help for commands.")
            return

        session = {'flow': ts.flow, 'step': ts.step, 'data': ts.data}

        if text == '/cancel':
            self.end(telegram_id)
            send_message(bot_token, chat_id, "Cancelled. /help for commands.")
            return

        flow = session['flow']
        if flow == 'register':
            _process_register(self, telegram_id, text, bot_token, chat_id, session)
        elif flow == 'create_request':
            _process_create_request(self, telegram_id, text, bot_token, chat_id, session)
        elif flow == 'send_offer':
            _process_send_offer(self, telegram_id, text, bot_token, chat_id, session)
        elif flow == 'revise_offer':
            _process_revise_offer(self, telegram_id, text, bot_token, chat_id, session)
        elif flow == 'report_late':
            _process_report_late(self, telegram_id, text, bot_token, chat_id, session)
        elif flow == 'create_dispute':
            _process_create_dispute(self, telegram_id, text, bot_token, chat_id, session)

        # Save if still active (flow handler may have called end())
        if self.is_active(telegram_id):
            self._save(telegram_id, session)

    def process_callback(self, telegram_id, data, bot_token, chat_id):
        """Handle inline button presses during a conversation."""
        if not self.is_active(telegram_id):
            return False

        session = self.get(telegram_id)
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

    def cleanup_expired(self, timeout_minutes=SESSION_TIMEOUT_MINUTES):
        """Delete sessions older than timeout_minutes."""
        cutoff = datetime.utcnow() - timedelta(minutes=timeout_minutes)
        try:
            count = TelegramSession.query.filter(
                TelegramSession.updated_at < cutoff
            ).delete()
            db.session.commit()
            if count:
                logger.info("Cleaned up %d expired conversation sessions", count)
        except Exception:
            db.session.rollback()
            logger.exception("Failed to clean up expired sessions")


conversation_manager = ConversationManager()


# ── Register flow ──────────────────────────────────────────────────

def _process_register(cm, telegram_id, text, bot_token, chat_id, session):
    from .handlers import send_message
    from . import keyboards

    try:
        step = session['step']

        if step == 0:
            if text not in ('client', 'provider'):
                send_message(bot_token, chat_id, "Please choose:", keyboards.role_select())
                return
            session['data']['role'] = text
            session['step'] = 1
            send_message(bot_token, chat_id,
                         "Enter your email (or type <b>skip</b>):")
            return

        if step == 1:
            email = text.strip()
            if email.lower() == 'skip':
                email = f"tg_{telegram_id}@telegram.placeholder"
            elif not EMAIL_RE.match(email):
                send_message(bot_token, chat_id, "Invalid email. Try again or type <b>skip</b>:")
                return
            else:
                existing = User.query.filter_by(email=email).first()
                if existing:
                    existing.telegram_id = telegram_id
                    existing.telegram_notifications = True
                    existing.phone_verified = True  # Telegram requires phone → auto-verify
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
            username = text.strip()
            if not USERNAME_RE.match(username):
                send_message(bot_token, chat_id,
                             "Username must be 2-30 characters (letters, numbers, _ . -):")
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
                phone_verified=True,  # Telegram requires phone → auto-verify
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

    except Exception:
        logger.exception("Error in register flow step=%s for telegram_id=%s",
                         session.get('step'), telegram_id)
        cm.end(telegram_id)
        send_message(bot_token, chat_id,
                     "Something went wrong during registration. Please /register to start again.")


# ── Create request flow (client) ──────────────────────────────────

def _process_create_request(cm, telegram_id, text, bot_token, chat_id, session):
    from .handlers import send_message
    from . import keyboards

    try:
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
            if step == 2:
                try:
                    dt = datetime.strptime(text.strip(), '%Y-%m-%d %H:%M')
                    if dt < datetime.now():
                        send_message(bot_token, chat_id, "Date must be in the future. Try again:")
                        return
                    session['data']['datetime'] = dt.strftime('%Y-%m-%d %H:%M:%S')
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

            if session['step'] < len(prompts):
                send_message(bot_token, chat_id, prompts[session['step']])
                return

            # All info collected — show summary
            d = session['data']
            dt = datetime.strptime(d['datetime'], '%Y-%m-%d %H:%M:%S')
            session['step'] = len(prompts)
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
        dt = datetime.strptime(d['datetime'], '%Y-%m-%d %H:%M:%S')
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

    except Exception:
        logger.exception("Error in create_request flow step=%s for telegram_id=%s",
                         session.get('step'), telegram_id)
        cm.end(telegram_id)
        send_message(bot_token, chat_id,
                     "Something went wrong. Please /create_request to start again.")


# ── Send offer flow (provider) ────────────────────────────────────

def _process_send_offer(cm, telegram_id, text, bot_token, chat_id, session):
    from .handlers import send_message
    from . import keyboards

    try:
        step = session['step']

        if step == 0:
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

            from .notifications import notify_new_offer
            try:
                notify_new_offer(req, offer)
            except Exception:
                logger.exception("Failed to send new-offer notification for request_id=%s", req_id)

            send_message(bot_token, chat_id,
                         f"Offer of <b>{price:.2f} EUR</b> sent for <b>{req.service_name}</b>!")

    except Exception:
        logger.exception("Error in send_offer flow step=%s for telegram_id=%s",
                         session.get('step'), telegram_id)
        cm.end(telegram_id)
        send_message(bot_token, chat_id,
                     "Something went wrong. Please try again.")


# ── Revise offer flow (provider responds to counter-offer) ────────

def _process_revise_offer(cm, telegram_id, text, bot_token, chat_id, session):
    from .handlers import send_message
    from . import keyboards

    try:
        step = session['step']

        if step == 0:
            try:
                price = float(text.strip())
                if price < 0:
                    send_message(bot_token, chat_id, "Price can't be negative:")
                    return
                session['data']['price'] = price
            except ValueError:
                send_message(bot_token, chat_id, "Enter a price (number):")
                return

            offer_id = session['data']['offer_id']
            offer = RequestOfferResponse.query.get(offer_id)
            req = offer.appointment_requests if offer else None
            svc = req.service_name if req else 'Service'

            session['step'] = 1
            send_message(bot_token, chat_id,
                         f"Revise price to <b>{price:.2f} EUR</b> for <b>{svc}</b>?",
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

            offer_id = session['data']['offer_id']
            price = session['data']['price']
            offer = RequestOfferResponse.query.filter_by(
                id=offer_id, provider_id=user.id
            ).first()

            if not offer or offer.status != 'pending':
                cm.end(telegram_id)
                send_message(bot_token, chat_id, "This offer is no longer available.")
                return

            offer.proposed_price = price
            offer.counter_price = None
            offer.last_action_by = 'provider'
            db.session.commit()
            cm.end(telegram_id)

            req = offer.appointment_requests
            svc = req.service_name if req else 'Service'
            send_message(bot_token, chat_id,
                         f"Price revised to <b>{price:.2f} EUR</b> for <b>{svc}</b>!\n"
                         f"Waiting for client response.")

            # Notify client about revised price
            try:
                from .notifications import send_user_telegram
                if req:
                    send_user_telegram(req.patient_id,
                                       f"<b>Provider revised their price</b>\n\n"
                                       f"Service: {svc}\n"
                                       f"New price: {price:.2f} EUR\n\n"
                                       f"Open the app to accept or counter.")
            except Exception:
                logger.exception("Failed to notify client about revised price")

    except Exception:
        logger.exception("Error in revise_offer flow step=%s for telegram_id=%s",
                         session.get('step'), telegram_id)
        cm.end(telegram_id)
        send_message(bot_token, chat_id,
                     "Something went wrong. Please try again.")


# ── Report late flow (provider) ──────────────────────────────────

def _process_report_late(cm, telegram_id, text, bot_token, chat_id, session):
    from .handlers import send_message
    from .notifications import send_user_telegram
    from app.models import Appointment, ClientSelfCreatedAppointment

    try:
        text = text.strip()
        try:
            minutes = int(text)
            if minutes < 1 or minutes > 300:
                send_message(bot_token, chat_id, "Enter a number between 1 and 300:")
                return
        except ValueError:
            send_message(bot_token, chat_id, "Please enter a number (minutes):")
            return

        d = session['data']
        atype = d['atype']
        obj_id = d['obj_id']
        svc_name = d['svc_name']
        client_id = d['client_id']

        if atype == 'appt':
            obj = Appointment.query.get(obj_id)
        else:
            obj = ClientSelfCreatedAppointment.query.get(obj_id)

        if not obj:
            cm.end(telegram_id)
            send_message(bot_token, chat_id, "Appointment not found.")
            return

        from app.extensions import db
        obj.provider_late_minutes = minutes
        db.session.commit()
        cm.end(telegram_id)

        send_message(bot_token, chat_id,
                     f"\u23f0 Reported {minutes} min late for <b>{svc_name}</b>. Client has been notified.")
        send_user_telegram(client_id,
                           f"<b>Provider is running late</b>\n\n"
                           f"Service: {svc_name}\n"
                           f"Estimated delay: ~{minutes} minutes")

    except Exception:
        logger.exception("Error in report_late flow for telegram_id=%s", telegram_id)
        cm.end(telegram_id)
        send_message(bot_token, chat_id, "Something went wrong. Please try again.")


# ── Create dispute flow (client) ─────────────────────────────────

def _process_create_dispute(cm, telegram_id, text, bot_token, chat_id, session):
    from .handlers import send_message
    from .notifications import send_user_telegram
    from app.models import Appointment, ClientSelfCreatedAppointment, Dispute

    try:
        step = session['step']

        if step == 0:
            # Reason selection
            reason_map = {'1': 'not_completed', '2': 'quality_issue', '3': 'other'}
            if text.strip() not in reason_map:
                send_message(bot_token, chat_id, "Enter 1, 2, or 3:")
                return
            session['data']['reason'] = reason_map[text.strip()]
            session['step'] = 1
            send_message(bot_token, chat_id, "Describe the issue (or type <b>skip</b>):")
            return

        if step == 1:
            # Description
            desc = text.strip()
            if desc.lower() == 'skip':
                desc = ''
            session['data']['description'] = desc

            d = session['data']
            atype = d['atype']
            obj_id = d['obj_id']
            svc_name = d['svc_name']
            provider_id = d['provider_id']

            user = User.query.filter_by(telegram_id=telegram_id).first()
            if not user:
                cm.end(telegram_id)
                send_message(bot_token, chat_id, "Error: account not found.")
                return

            if atype == 'appt':
                obj = Appointment.query.get(obj_id)
            else:
                obj = ClientSelfCreatedAppointment.query.get(obj_id)

            if not obj:
                cm.end(telegram_id)
                send_message(bot_token, chat_id, "Appointment not found.")
                return

            from app.extensions import db
            dispute = Dispute(
                reporter_id=user.id,
                reason=d['reason'],
                description=d['description'] or None,
                status='open',
            )
            if atype == 'appt':
                dispute.appointment_id = obj_id
            else:
                dispute.request_id = obj_id

            obj.status = 'disputed'
            db.session.add(dispute)
            db.session.commit()
            cm.end(telegram_id)

            reason_labels = {
                'not_completed': 'Not completed',
                'quality_issue': 'Quality issue',
                'other': 'Other',
            }

            send_message(bot_token, chat_id,
                         f"\u26a0\ufe0f Dispute created for <b>{svc_name}</b>.\n"
                         f"Reason: {reason_labels.get(d['reason'], d['reason'])}\n"
                         f"Our team will review it shortly.")

            send_user_telegram(provider_id,
                               f"<b>Dispute reported</b>\n\n"
                               f"Service: {svc_name}\n"
                               f"Reason: {reason_labels.get(d['reason'], d['reason'])}\n"
                               f"The platform team will review this case.")

    except Exception:
        logger.exception("Error in create_dispute flow step=%s for telegram_id=%s",
                         session.get('step'), telegram_id)
        cm.end(telegram_id)
        send_message(bot_token, chat_id,
                     "Something went wrong. Please try again.")
