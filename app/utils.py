import random
import math


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
