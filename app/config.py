"""
config.py — all app settings in one place.

Why? Instead of hunting for app.config['...'] scattered across __init__.py,
every setting lives here. Just import Config and pass it to Flask.

Environment variables are loaded from the .env file.
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # ── Security ───────────────────────────────────────────────────
    SECRET_KEY = os.getenv('SECRET_KEY', 'change-me-in-production')

    # ── Database ───────────────────────────────────────────────────
    SQLALCHEMY_DATABASE_URI      = os.getenv('DATABASE_URL')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ── Google OAuth ───────────────────────────────────────────────
    GOOGLE_OAUTH_CLIENT_ID     = os.getenv('GOOGLE_OAUTH_CLIENT_ID')
    GOOGLE_OAUTH_CLIENT_SECRET = os.getenv('GOOGLE_OAUTH_CLIENT_SECRET')

    # ── Email (Brevo / SMTP) ───────────────────────────────────────
    MAIL_SERVER         = os.getenv('MAIL_SERVER')
    MAIL_PORT           = int(os.getenv('MAIL_PORT', 587))
    MAIL_USE_TLS        = os.getenv('MAIL_USE_TLS', 'True').lower() == 'true'
    MAIL_USERNAME       = os.getenv('MAIL_USERNAME')
    MAIL_PASSWORD       = os.getenv('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.getenv('MAIL_DEFAULT_SENDER')

    # ── Stripe payments ────────────────────────────────────────────
    STRIPE_PUBLIC_KEY = os.getenv('STRIPE_PUBLIC_KEY')
    STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY')

    # ── Telegram notifications ───────────────────────────────────────
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    TELEGRAM_CHAT_ID   = os.getenv('TELEGRAM_CHAT_ID')
    TELEGRAM_BOT_NAME  = os.getenv('TELEGRAM_BOT_NAME')   # without @
    BASE_URL           = os.getenv('BASE_URL', 'http://127.0.0.1:5000')

    # ── JWT (mobile API) ───────────────────────────────────────────
    JWT_SECRET_KEY           = os.getenv('JWT_SECRET_KEY', 'change-jwt-secret')
    JWT_ACCESS_TOKEN_EXPIRES = 86400   # 24 hours

    # ── Internationalisation ───────────────────────────────────────
    BABEL_DEFAULT_LOCALE      = 'en'
    BABEL_SUPPORTED_LOCALES   = ['en', 'uk', 'de', 'pl']
    BABEL_TRANSLATION_DIRECTORIES = os.path.join(
        os.path.dirname(__file__), '..', 'translations'
    )
