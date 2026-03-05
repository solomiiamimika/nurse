from flask import Blueprint

provider_bp = Blueprint('provider', __name__)

from . import dashboard, appointments, profile, services, finances
