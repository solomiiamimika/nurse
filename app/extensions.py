from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_migrate import Migrate
from flask_socketio import SocketIO
from flask_dance.contrib.google import make_google_blueprint
import os

db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()
migrate = Migrate()
socketio = SocketIO(cors_allowed_origins="*")




google_blueprint = make_google_blueprint(
    client_id="739082915470-dm5ppev70pv4169eoo890rm61ahhae6s.apps.googleusercontent.com",
    client_secret="YGOCSPX-TpamlrYN42BnaffhyMQTStKZi81J",
    scope=["profile", "email", "openid"],
    redirect_to="auth.google_login",
    offline=True,
    reprompt_consent=True  
)



login_manager.login_view = 'auth.login'
login_manager.login_message = 'Будь ласка, увійдіть для доступу до цієї сторінки.'
login_manager.login_message_category = 'danger'