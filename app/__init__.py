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
from datetime import datetime
from flask import Flask, session, request
from .config import Config
from .extensions import db, bcrypt, login_manager, migrate, google_blueprint, babel, mail, socketio, csrf
from flask_jwt_extended import JWTManager
from flask_cors import CORS

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
        return request.accept_languages.best_match(['en', 'uk'])
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

    csrf.exempt(api_auth_bp)   # mobile API uses JWT, not CSRF tokens

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(client_bp,   url_prefix='/client')
    app.register_blueprint(provider_bp, url_prefix='/provider')
    app.register_blueprint(owner_bp)
    app.register_blueprint(google_blueprint)
    app.register_blueprint(api_auth_bp, url_prefix='/auth/api')

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

    # ── 5. Make google_oauth_enabled available in every template ──
    @app.context_processor
    def inject_globals():
        return dict(
            google_oauth_enabled=app.config.get('GOOGLE_OAUTH_CLIENT_ID') is not None
        )

    # ── 5. Create tables if they don't exist yet ──────────────────
    with app.app_context():
        db.create_all()

    return app
    



