from flask import Blueprint


auth_bp = Blueprint('auth',__name__,url_prefix='/auth')

main_bp = Blueprint('main',__name__)

nurse_bp = Blueprint('nurse',__name__,url_prefix='/nurse')


client_bp = Blueprint('client',__name__,url_prefix='/client')

from . import auth, nurse, main, client