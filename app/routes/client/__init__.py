from flask import Blueprint

client_bp = Blueprint('client', __name__)

from . import dashboard, appointments, profile, payments
