from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_migrate import Migrate
from flask_dance.contrib.google import make_google_blueprint
import os
from flask_socketio import SocketIO
from flask_babel import Babel
from flask_mail import Mail

babel = Babel()
mail=Mail()

db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()
migrate = Migrate()
socketio = SocketIO(async_mode='eventlet', cors_allowed_origins="*")
from supabase import create_client,Client





SUPABASE_URL = "https://mjmndbunrynhdtzxteit.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1qbW5kYnVucnluaGR0enh0ZWl0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTQ2NDYwNTMsImV4cCI6MjA3MDIyMjA1M30.QL3pqprmqzcE4I6r0zWTESHJ1G_Ab6hvevxh26XXJ-U"
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
    client_id="739082915470-dm5ppev70pv4169eoo890rm61ahhae6s.apps.googleusercontent.com",
    client_secret="YGOCSPX-TpamlrYN42BnaffhyMQTStKZi81J",
    scope=["https://www.googleapis.com/auth/userinfo.profile", "https://www.googleapis.com/auth/userinfo.email", "openid"],
    redirect_to="auth.google_login",
    offline=True,
    reprompt_consent=True  
)



login_manager.login_view = 'auth.login'
login_manager.login_message = ("Будь ласка, увійдіть для доступу до цієї сторінки.")
login_manager.login_message_category = 'danger'