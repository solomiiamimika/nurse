from flask import Blueprint
from . import auth, nurse, main, client

auth_bp = Blueprint('auth',__name__,url_prefix='/auth')

main_bp = Blueprint('main',__name__)

nurse_bp = Blueprint('nurse',__name__)


client_bp = Blueprint('client',__name__)

