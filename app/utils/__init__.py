import random
import math
from functools import wraps
from flask import jsonify, request, g
from flask_login import current_user as flask_current_user


def fuzz_coordinates(lat, lng, meters=300):
    """
    Додає випадковий шум до координат в межах ±meters.
    Використовується щоб не показувати точну адресу на загальній карті.
    """
    # 1 градус широти ≈ 111 000 м
    lat_offset = (random.uniform(-meters, meters)) / 111_000
    # 1 градус довготи залежить від широти
    lng_offset = (random.uniform(-meters, meters)) / (111_000 * math.cos(math.radians(lat)))
    return round(lat + lat_offset, 6), round(lng + lng_offset, 6)


def haversine_distance(lat1, lng1, lat2, lng2):
    """
    Відстань між двома точками в кілометрах (формула Гаверсинуса).
    """
    R = 6371  # радіус Землі в км
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (math.sin(d_lat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(d_lng / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def validate_coordinates(lat, lng):
    """
    Перевіряє що координати є реальними.
    Повертає (True, None) або (False, повідомлення про помилку).
    """
    try:
        lat = float(lat)
        lng = float(lng)
    except (TypeError, ValueError):
        return False, 'Coordinates must be numbers'

    if not (-90 <= lat <= 90):
        return False, 'Latitude must be between -90 and 90'
    if not (-180 <= lng <= 180):
        return False, 'Longitude must be between -180 and 180'

    return True, None


def api_login_required(f):
    """
    Decorator that accepts both Flask-Login sessions (web) and JWT Bearer tokens (mobile).
    Sets flask_login.current_user in both cases so route handlers work unchanged.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        # 1. Check if already authenticated via Flask-Login session
        if flask_current_user.is_authenticated:
            return f(*args, **kwargs)

        # 2. Check for JWT Bearer token
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            try:
                from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
                from flask_login import login_user
                from app.models import User

                verify_jwt_in_request()
                user_id = get_jwt_identity()
                user = User.query.get(int(user_id))
                if user:
                    login_user(user)
                    return f(*args, **kwargs)
            except Exception:
                pass

        return jsonify({'error': 'Authentication required'}), 401

    return decorated
