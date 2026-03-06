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

# Allow OAuth over plain HTTP during local development
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)   # load all settings from config.py

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
        return request.accept_languages.best_match(['en', 'de', 'uk'])
    babel.init_app(app, locale_selector=get_locale)

    JWTManager(app)
    CORS(app)   # allows the mobile app to make requests to this server

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
        return dict(
            google_oauth_enabled=app.config.get('GOOGLE_OAUTH_CLIENT_ID') is not None,
            telegram_bot_name=app.config.get('TELEGRAM_BOT_NAME'),
        )

    # ── 5. Create tables if they don't exist yet ──────────────────
    with app.app_context():
        db.create_all()
        # Add previous_status columns if missing (no migration tool)
        try:
            from sqlalchemy import text, inspect
            insp = inspect(db.engine)
            for tbl, col in [('appointment', 'previous_status'),
                             ('client_self_create_appointment', 'previous_status')]:
                cols = [c['name'] for c in insp.get_columns(tbl)]
                if col not in cols:
                    db.session.execute(text(
                        f'ALTER TABLE {tbl} ADD COLUMN {col} VARCHAR(20)'
                    ))
                    db.session.commit()
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
                except Exception:
                    pass

    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        scheduler = BackgroundScheduler(daemon=True)
        scheduler.add_job(send_payment_reminders, 'cron', hour=9, minute=0)
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
        except Exception:
            pass

    return app
    



