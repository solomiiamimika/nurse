from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_migrate import Migrate
from flask_dance.contrib.google import make_google_blueprint
import os
from flask_socketio import SocketIO
from flask_babel import Babel
from flask_mail import Mail
from flask_wtf.csrf import CSRFProtect
babel = Babel()
mail=Mail()
csrf = CSRFProtect()
db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()
migrate = Migrate()
socketio = SocketIO(cors_allowed_origins="*")
from supabase import create_client,Client





SUPABASE_URL = os.getenv('SUPABASE_URL', '')
SUPABASE_KEY = os.getenv('SUPABASE_KEY', '')
if SUPABASE_URL and SUPABASE_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    supabase = None
    print("⚠️  Supabase client not initialized - check environment variables")
buckets = {
    'documents':'user-documents',
    'profile_pictures':'profile_pictures',
    'messages':'message-media'
}




google_blueprint = make_google_blueprint(
    client_id=os.getenv('GOOGLE_OAUTH_CLIENT_ID', ''),
    client_secret=os.getenv('GOOGLE_OAUTH_CLIENT_SECRET', ''),
    scope=["https://www.googleapis.com/auth/userinfo.profile", "https://www.googleapis.com/auth/userinfo.email", "openid"],
    redirect_to="auth.google_login",
    offline=True,
    reprompt_consent=True  
)



login_manager.login_view = 'auth.login'
login_manager.login_message = ("Будь ласка, увійдіть для доступу до цієї сторінки.")
login_manager.login_message_category = 'danger'