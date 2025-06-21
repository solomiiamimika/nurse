from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_migrate import Migrate
from flask_socketio import SocketIO
from flask_dance.contrib.google import make_google_blueprint

db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()
migrate = Migrate()
socket_io = SocketIO()




google_blueprint = make_google_blueprint(
    client_id="563510051014-l1hhcimduh37tsgtq860po82hk2c2r7m.apps.googleusercontent.com",
    client_secret="YOUGOCSPX--KMnpVDzFxHBWiX31k2_lD1WH7g-",
    scope=["profile", "email"],
    redirect_to="auth.google_login",
    offline=True,
    reprompt_consent=True
)



login_manager.login_view = 'auth.login'