"""
__init__.py — App Factory

This file creates and configures the Flask application.
'App Factory' pattern means we create the app inside a function (create_app),
which makes it easy to create different versions for testing, development, etc.

How it all connects:
  config.py      → all settings (keys, URLs, email config)
  extensions.py  → third-party tools (database, auth, sockets...)
  models/        → database table definitions
  routes/        → URL handlers (what happens at each URL)
  templates/     → HTML pages
  static/        → CSS, JS, images
"""
import os
from datetime import datetime, timedelta
from flask import Flask, session, request
from .config import Config
from .extensions import db, bcrypt, login_manager, migrate, google_blueprint, babel, mail, socketio, csrf
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler

# OAuth: only allow insecure transport in development
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)   # load all settings from config.py

    # ── Logging ─────────────────────────────────────────────────
    import logging
    log_level = logging.DEBUG if app.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('werkzeug').setLevel(logging.WARNING)

    # ── 1. Init extensions (order matters) ────────────────────────
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    migrate.init_app(app, db)
    csrf.init_app(app)
    socketio.init_app(app)
    mail.init_app(app)

    # Babel needs a locale selector function
    def get_locale():
        if 'lang' in session:
            return session.get('lang', 'en')
        return request.accept_languages.best_match(['en', 'uk', 'de', 'pl'])
    babel.init_app(app, locale_selector=get_locale)

    JWTManager(app)
    CORS(app, origins=[
        app.config.get('BASE_URL', 'http://127.0.0.1:5000'),
        'http://localhost:5000',
        'http://127.0.0.1:5000',
    ])

    # ── 2. Register blueprints (URL route groups) ─────────────────
    from app.routes.auth     import auth_bp
    from app.routes.main     import main_bp
    from app.routes.client   import client_bp
    from app.routes.provider import provider_bp
    from app.routes.api_auth import api_auth_bp
    from app.routes.owner    import owner_bp

    from app.telegram import telegram_bp

    csrf.exempt(api_auth_bp)   # mobile API uses JWT, not CSRF tokens
    csrf.exempt(telegram_bp)   # Telegram webhook sends POST without CSRF
    # TODO: Add {{ csrf_token() }} to all web form templates, then remove
    # these blanket exemptions and use per-endpoint @csrf.exempt for mobile API
    csrf.exempt(client_bp)
    csrf.exempt(provider_bp)
    csrf.exempt(main_bp)

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(client_bp,   url_prefix='/client')
    app.register_blueprint(provider_bp, url_prefix='/provider')
    app.register_blueprint(owner_bp)
    app.register_blueprint(google_blueprint)
    app.register_blueprint(api_auth_bp, url_prefix='/auth/api')
    app.register_blueprint(telegram_bp)

    # ── 3. Tell Flask-Login how to load a user from the session ───
    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    @login_manager.request_loader
    def load_user_from_request(req):
        """Load user from JWT Bearer token (mobile app) if no session."""
        auth_header = req.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            try:
                from flask_jwt_extended import decode_token
                token_data = decode_token(auth_header[7:])
                user_id = token_data.get('sub')
                if user_id:
                    return User.query.get(int(user_id))
            except Exception:
                pass
        return None

    @login_manager.unauthorized_handler
    def unauthorized_api():
        """Return JSON 401 for API requests, redirect for web."""
        if (request.accept_mimetypes.best == 'application/json'
                or request.headers.get('Authorization', '').startswith('Bearer ')):
            from flask import jsonify
            return jsonify({'error': 'Authentication required'}), 401
        from flask import redirect, url_for
        return redirect(url_for('auth.login'))

    # ── 4. Jinja2 filters ─────────────────────────────────────────
    @app.template_filter('ts_to_date')
    def ts_to_date(ts):
        if ts is None:
            return 'N/A'
        return datetime.fromtimestamp(int(ts)).strftime('%d.%m.%Y')

    import json as _json
    @app.template_filter('from_json')
    def from_json_filter(value):
        try:
            return _json.loads(value or '{}')
        except Exception:
            return {}

    # ── 5. Make google_oauth_enabled available in every template ──
    @app.context_processor
    def inject_globals():
        from flask_login import current_user as _cu
        profile_incomplete = False
        profile_issues = []
        if _cu and _cu.is_authenticated and not _cu.is_owner:
            if not _cu.full_name:
                profile_issues.append('full_name')
            if not _cu.is_contact_verified:
                profile_issues.append('contact_verification')
            profile_incomplete = len(profile_issues) > 0
        return dict(
            google_oauth_enabled=app.config.get('GOOGLE_OAUTH_CLIENT_ID') is not None,
            telegram_bot_name=app.config.get('TELEGRAM_BOT_NAME'),
            profile_incomplete=profile_incomplete,
            profile_issues=profile_issues,
        )

    # ── 5. Create tables if they don't exist yet ──────────────────
    with app.app_context():
        db.create_all()
        # Add missing columns (no migration tool)
        try:
            from sqlalchemy import text, inspect
            insp = inspect(db.engine)
            new_columns = [
                ('appointment', 'previous_status', 'VARCHAR(20)'),
                ('client_self_create_appointment', 'previous_status', 'VARCHAR(20)'),
                ('appointment', 'provider_arrived_at', 'TIMESTAMP'),
                ('appointment', 'provider_late_minutes', 'INTEGER'),
                ('appointment', 'work_submitted_at', 'TIMESTAMP'),
                ('client_self_create_appointment', 'provider_arrived_at', 'TIMESTAMP'),
                ('client_self_create_appointment', 'provider_late_minutes', 'INTEGER'),
                ('client_self_create_appointment', 'work_submitted_at', 'TIMESTAMP'),
                ('user', 'no_show_count', 'INTEGER DEFAULT 0'),
                ('user', 'iban', 'VARCHAR(34)'),
                ('user', 'phone_verified', 'BOOLEAN DEFAULT FALSE'),
                ('user', 'email_verified', 'BOOLEAN DEFAULT FALSE'),
                ('user', 'id_verified', 'BOOLEAN DEFAULT FALSE'),
                ('appointment', 'payment_method_type', 'VARCHAR(20)'),
                ('appointment', 'deposit_amount', 'FLOAT'),
                ('client_self_create_appointment', 'payment_method_type', 'VARCHAR(20)'),
                ('client_self_create_appointment', 'deposit_amount', 'FLOAT'),
                ('provider_service', 'deposit_percentage', 'INTEGER DEFAULT 0'),
            ]
            for tbl, col, col_type in new_columns:
                try:
                    cols = [c['name'] for c in insp.get_columns(tbl)]
                    if col not in cols:
                        db.session.execute(text(
                            f'ALTER TABLE "{tbl}" ADD COLUMN {col} {col_type}'
                        ))
                        db.session.commit()
                except Exception:
                    db.session.rollback()
        except Exception:
            db.session.rollback()

        # Seed default base services if table is empty
        from app.models import Service
        if Service.query.count() == 0:
            default_services = [
                Service(name='Home Patient Care',        description='In-home care for sick or recovering patients',         base_price=25, base_duration=60),
                Service(name='Elderly Care',             description='Assistance and companionship for elderly people',      base_price=20, base_duration=60),
                Service(name='Overnight Care',           description='Overnight monitoring and care at home',                base_price=80, base_duration=480),
                Service(name='Doctor Visit Escort',      description='Accompanying and assisting during doctor visits',      base_price=30, base_duration=120),
                Service(name='Therapeutic Massage',      description='Professional therapeutic massage session',             base_price=40, base_duration=60),
                Service(name='Rehabilitation Exercises', description='Guided rehabilitation and physical exercises',         base_price=35, base_duration=45),
                Service(name='Post-Surgery Care',        description='Specialized care after surgical procedures',           base_price=30, base_duration=60),
                Service(name='Hygiene Assistance',       description='Help with bathing, grooming, and personal hygiene',    base_price=20, base_duration=45),
                Service(name='Meal Preparation',         description='Cooking and preparing meals at home',                  base_price=15, base_duration=60),
                Service(name='Housekeeping',             description='Light cleaning, tidying, and household tasks',         base_price=15, base_duration=60),
                Service(name='Errands & Shopping',       description='Grocery shopping, pharmacy runs, and other errands',   base_price=15, base_duration=60),
                Service(name='Childcare',                description='Professional childcare and supervision',               base_price=20, base_duration=60),
                Service(name='Babysitting',              description='Short-term babysitting by the hour',                   base_price=15, base_duration=60),
                Service(name='Online Consultation',      description='Remote consultation via video or chat',                base_price=20, base_duration=30),
                Service(name='Companionship',            description='Social companionship, conversation, and activities',   base_price=15, base_duration=60),
                Service(name='Hausmeister',              description='Handyman tasks: minor repairs, furniture assembly, maintenance',  base_price=25, base_duration=60),
            ]
            db.session.add_all(default_services)
            db.session.commit()

    # ── 6. Scheduler: send payment reminder emails 7 days before service ──
    def send_payment_reminders():
        from app.models import ClientSelfCreatedAppointment
        from flask_mail import Message as MailMessage
        from threading import Thread

        with app.app_context():
            now = datetime.utcnow()
            window_start = now + timedelta(days=6, hours=23)
            window_end   = now + timedelta(days=7, hours=1)

            pending = ClientSelfCreatedAppointment.query.filter(
                ClientSelfCreatedAppointment.status == 'accepted',
                ClientSelfCreatedAppointment.appointment_start_time >= window_start,
                ClientSelfCreatedAppointment.appointment_start_time <= window_end,
                ClientSelfCreatedAppointment.payment_intent_id == None,
            ).all()

            for req in pending:
                client = req.patient
                if not client or not client.email:
                    continue
                pay_url = f"{app.config.get('BASE_URL', '')}/client/pay_request/{req.id}"
                msg = MailMessage(
                    subject="Payment reminder — your appointment is in 7 days",
                    sender=os.getenv('MAIL_DEFAULT_SENDER'),
                    recipients=[client.email],
                    body=(
                        f"Hi {client.full_name or client.user_name},\n\n"
                        f"Your appointment for '{req.service_name}' is scheduled for "
                        f"{req.appointment_start_time.strftime('%d %b %Y at %H:%M')}.\n\n"
                        f"Please authorize your payment now so the provider is confirmed:\n"
                        f"{pay_url}\n\n"
                        f"The funds will be held securely and only released after the service.\n\n"
                        f"If you need to cancel, do it before the appointment to avoid any fees.\n\n"
                        f"— The Team"
                    )
                )
                try:
                    Thread(target=lambda m=msg: mail.send(m)).start()
                except Exception as e:
                    app.logger.error(f"Email error for request {req.id}: {e}")

                # Also send Telegram reminder if user has it linked
                try:
                    from app.telegram.notifications import notify_appointment_reminder
                    if client.telegram_id and client.telegram_notifications:
                        notify_appointment_reminder(
                            client.id,
                            req.service_name,
                            req.appointment_start_time.strftime('%d %b %Y'),
                            req.appointment_start_time.strftime('%H:%M'),
                        )
                except Exception as e:
                    app.logger.error(f"Telegram reminder error for request {req.id}: {e}")

    def cleanup_telegram_sessions():
        with app.app_context():
            from app.telegram.conversations import conversation_manager
            conversation_manager.cleanup_expired(timeout_minutes=30)

    def auto_approve_work_submitted():
        """Auto-approve work_submitted appointments after 48 hours."""
        import stripe as _stripe
        _stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

        with app.app_context():
            from app.models import Appointment, ClientSelfCreatedAppointment, Payment, User
            now = datetime.utcnow()
            cutoff = now - timedelta(hours=48)

            # Auto-approve Appointments
            appts = Appointment.query.filter(
                Appointment.status == 'work_submitted',
                Appointment.work_submitted_at.isnot(None),
                Appointment.work_submitted_at <= cutoff,
            ).all()

            for appt in appts:
                try:
                    provider = User.query.get(appt.provider_id)
                    service = appt.provider_service
                    price = service.price if service else 0

                    if price > 0:
                        payment = Payment.query.filter_by(appointment_id=appt.id, status='completed').first()
                        if payment and payment.transaction_id and provider and provider.stripe_account_id:
                            pi = _stripe.PaymentIntent.capture(payment.transaction_id,
                                idempotency_key=f"auto_complete_appt_{appt.id}")
                            amount_cents = pi.amount_received
                            commission_rate = app.config.get('PLATFORM_COMMISSION_RATE', 0.15)
                            platform_fee = int(round(amount_cents * commission_rate))
                            payout = amount_cents - platform_fee
                            _stripe.Transfer.create(
                                amount=payout, currency='eur',
                                destination=provider.stripe_account_id,
                                transfer_group=f"auto_appt_{appt.id}",
                                idempotency_key=f"auto_transfer_appt_{appt.id}",
                            )
                            payment.status = 'paid'
                            payment.platform_fee_cents = platform_fee

                    appt.set_status('completed')
                    from app.routes.provider.appointments import sync_appointment_request_status
                    sync_appointment_request_status(appt, 'completed')
                    db.session.commit()
                    app.logger.info(f"Auto-approved appointment {appt.id}")
                except Exception as e:
                    db.session.rollback()
                    app.logger.error(f"Auto-approve error for appointment {appt.id}: {e}")

            # Auto-approve Requests
            reqs = ClientSelfCreatedAppointment.query.filter(
                ClientSelfCreatedAppointment.status == 'work_submitted',
                ClientSelfCreatedAppointment.work_submitted_at.isnot(None),
                ClientSelfCreatedAppointment.work_submitted_at <= cutoff,
            ).all()

            for req in reqs:
                try:
                    provider = User.query.get(req.provider_id) if req.provider_id else None
                    is_free = (req.payment or 0) == 0

                    if not is_free and req.payment_intent_id and provider and provider.stripe_account_id:
                        pi = _stripe.PaymentIntent.capture(req.payment_intent_id,
                            idempotency_key=f"auto_complete_req_{req.id}")
                        amount_cents = pi.amount_received
                        commission_rate = app.config.get('PLATFORM_COMMISSION_RATE', 0.15)
                        platform_fee = int(round(amount_cents * commission_rate))
                        payout = amount_cents - platform_fee
                        _stripe.Transfer.create(
                            amount=payout, currency='eur',
                            destination=provider.stripe_account_id,
                            transfer_group=f"auto_req_{req.id}",
                            idempotency_key=f"auto_transfer_req_{req.id}",
                        )

                    req.set_status('completed')
                    from app.routes.provider.appointments import sync_request_appointment_status
                    sync_request_appointment_status(req, 'completed')
                    db.session.commit()
                    app.logger.info(f"Auto-approved request {req.id}")
                except Exception as e:
                    db.session.rollback()
                    app.logger.error(f"Auto-approve error for request {req.id}: {e}")

    def remind_work_submitted_approval():
        """Remind client at 24h mark to approve work_submitted."""
        with app.app_context():
            from app.models import Appointment, ClientSelfCreatedAppointment, User
            now = datetime.utcnow()
            window_start = now - timedelta(hours=25)
            window_end = now - timedelta(hours=23)

            # Remind for appointments
            appts = Appointment.query.filter(
                Appointment.status == 'work_submitted',
                Appointment.work_submitted_at.isnot(None),
                Appointment.work_submitted_at >= window_start,
                Appointment.work_submitted_at <= window_end,
            ).all()

            for appt in appts:
                try:
                    from app.telegram.notifications import send_user_telegram
                    svc = appt.provider_service.name if appt.provider_service else 'Service'
                    send_user_telegram(appt.client_id,
                        f"Please confirm that '{svc}' was completed. Auto-approval in 24 hours.")
                except Exception:
                    pass

            # Remind for requests
            reqs = ClientSelfCreatedAppointment.query.filter(
                ClientSelfCreatedAppointment.status == 'work_submitted',
                ClientSelfCreatedAppointment.work_submitted_at.isnot(None),
                ClientSelfCreatedAppointment.work_submitted_at >= window_start,
                ClientSelfCreatedAppointment.work_submitted_at <= window_end,
            ).all()

            for req in reqs:
                try:
                    from app.telegram.notifications import send_user_telegram
                    send_user_telegram(req.patient_id,
                        f"Please confirm that '{req.service_name or 'Service'}' was completed. Auto-approval in 24 hours.")
                except Exception:
                    pass

    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        scheduler = BackgroundScheduler(daemon=True)
        scheduler.add_job(send_payment_reminders, 'cron', hour=9, minute=0)
        scheduler.add_job(cleanup_telegram_sessions, 'interval', minutes=10)
        scheduler.add_job(auto_approve_work_submitted, 'interval', hours=1)
        scheduler.add_job(remind_work_submitted_approval, 'interval', hours=1)
        scheduler.start()

    # ── 7. Set Telegram webhook (production only) ────────────────────
    bot_token = app.config.get('TELEGRAM_BOT_TOKEN')
    base_url = app.config.get('BASE_URL', '')
    if bot_token and base_url and not base_url.startswith('http://127'):
        import requests as _req
        import hashlib as _hl
        try:
            secret = _hl.sha256(f"{bot_token}:webhook".encode()).hexdigest()[:32]
            _req.post(
                f"https://api.telegram.org/bot{bot_token}/setWebhook",
                json={'url': f"{base_url}/telegram/webhook", 'secret_token': secret},
                timeout=5,
            )
            # Set bot menu commands
            _req.post(
                f"https://api.telegram.org/bot{bot_token}/setMyCommands",
                json={'commands': [
                    {'command': 'start', 'description': 'Start the bot'},
                    {'command': 'help', 'description': 'Show available commands'},
                    {'command': 'appointments', 'description': 'My appointments'},
                    {'command': 'create_request', 'description': 'Post a new request'},
                    {'command': 'open_requests', 'description': 'Browse open requests'},
                    {'command': 'my_offers', 'description': 'View sent offers'},
                    {'command': 'favorites', 'description': 'My favorite providers'},
                    {'command': 'notifications', 'description': 'Toggle notifications'},
                    {'command': 'switch_role', 'description': 'Switch Client/Provider'},
                    {'command': 'cancel', 'description': 'Cancel current operation'},
                ]},
                timeout=5,
            )
        except Exception:
            pass

    return app
    



