from flask import Flask, app, session, request
from wtforms.csrf.core import CSRF
from .extensions import db, bcrypt, login_manager, migrate, google_blueprint, babel
from app.models import User, Message, Service, Appointment, Payment, MedicalRecord, Prescription, Review
from app.routes import auth_bp, main_bp, client_bp, nurse_bp
from flask_wtf.csrf import CSRFProtect
from .extensions import socketio
import os
from dotenv import load_dotenv






load_dotenv()
def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv ('DATABASE_URL')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['GOOGLE_OAUTH_CLIENT_ID'] = os.getenv ('GOOGLE_OAUTH_CLIENT_ID')
    app.config['GOOGLE_OAUTH_CLIENT_SECRET'] = os.getenv ('GOOGLE_OAUTH_CLIENT_SECRET')
    app.config['BABEL_DEFAULT_LOCALE'] = 'en'
    app.config['BABEL_SUPPORTED_LOCALES'] = ['de', 'uk', 'pl', 'cz-CN']
    csrf=CSRFProtect()

    app.config["BABEL_TRANSLATION_DIRECTORIES"] = os.path.join(
        os.path.dirname(__file__), "..", "translations"
    )
#banking
    app.config['STRIPE_PUBLIC_KEY']= os.getenv ('STRIPE_PUBLIC_KEY')
    app.config['STRIPE_SECRET_KEY']= os.getenv ('STRIPE_SECRET_KEY')

    # Initializing extensions
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    migrate.init_app(app, db)
    csrf.init_app(app)
    socketio.init_app(app)

    def get_locale():
        if 'lang' in session:
            return session.get('lang', 'en')
        return request.accept_languages.best_match(['en', 'uk'])

    babel.init_app(app, locale_selector=get_locale)

    # Registering blueprints
    from app.routes.auth import auth_bp
    from app.routes.main import main_bp
    from app.routes.client import client_bp
    from app.routes.nurse import nurse_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(client_bp,url_prefix='/client')
    app.register_blueprint(nurse_bp,url_prefix='/nurse')
    app.register_blueprint(google_blueprint)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Additional configuration for Google OAuth
    @app.context_processor
    def inject_google_oauth():
        return dict(
            google_oauth_enabled=app.config.get('GOOGLE_OAUTH_CLIENT_ID') is not None
        )

    with app.app_context():
        db.create_all()

    return app
    



