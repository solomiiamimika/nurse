from . import client_bp
from flask import render_template, redirect, url_for, flash, request, abort, jsonify, current_app, Blueprint
from app.extensions import db, bcrypt, socketio, mail
from app.models import Appointment, ProviderService, User, Message, Payment, ClientSelfCreatedAppointment, Review, RequestOfferResponse, ServiceHistory, CancellationPolicy
from app.models.service import SERVICE_TAG_CATEGORIES
from app.utils import fuzz_coordinates, validate_coordinates
from app.supabase_storage import get_file_url, delete_from_supabase, upload_to_supabase, buckets
from datetime import datetime, timedelta
import os
from werkzeug.utils import secure_filename
import json
from dotenv import load_dotenv
import stripe
import base64
from flask_mail import Message as MailMessage
from threading import Thread
from flask_socketio import join_room, leave_room, emit
from flask_cors import cross_origin
from flask_login import login_required, current_user
load_dotenv()
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
stripe_public_key = os.getenv('STRIPE_PUBLIC_KEY')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'app', 'static', 'uploads')
DOCUMENTS_FOLDER = os.path.join(UPLOAD_FOLDER, 'documents')
PROFILE_PICTURES_FOLDER = os.path.join(UPLOAD_FOLDER, 'profile_pictures')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DOCUMENTS_FOLDER, exist_ok=True)
os.makedirs(PROFILE_PICTURES_FOLDER, exist_ok=True)


@client_bp.route('/dashboard')
@login_required
def dashboard():
    if current_user.role != 'client':
        return redirect(url_for('auth.login'))

    return render_template('client/dashboard.html', stripe_public_key=stripe_public_key,
                           service_tag_categories=SERVICE_TAG_CATEGORIES)


@client_bp.route('/get_providers_locations')
@login_required
def get_providers_locations():
    if current_user.role != 'client':
        return jsonify({'error': 'Entrance not allowed'}), 403

    providers = User.query.filter(
        User.role == 'provider',
        User.location_approved == True,
        User.latitude.isnot(None),
        User.longitude.isnot(None)
    ).all()

    providers_data = []
    for provider in providers:
        if not ProviderService.query.filter_by(provider_id=provider.id, is_available=True).first():
            continue
        f_lat, f_lng = fuzz_coordinates(provider.latitude, provider.longitude, meters=100)
        providers_data.append({
            'id': provider.id,
            'name': provider.user_name,
            'lat': f_lat,
            'lng': f_lng,
            'online': provider.online
        })

    return jsonify(providers_data)


@client_bp.route('/get_providers_list')
@login_required
def get_providers_list():
    """Return providers with distance, rating, services count for filtered search."""
    if current_user.role != 'client':
        return jsonify({'error': 'Access denied'}), 403

    from math import radians, cos, sin, asin, sqrt

    providers = User.query.filter_by(role='provider').all()
    client_lat = current_user.latitude
    client_lng = current_user.longitude

    providers_data = []
    for p in providers:
        if not ProviderService.query.filter_by(provider_id=p.id, is_available=True).first():
            continue
        distance_km = None
        if client_lat and client_lng and p.latitude and p.longitude:
            lat1, lon1, lat2, lon2 = map(radians, [client_lat, client_lng, p.latitude, p.longitude])
            dlat = lat2 - lat1
            dlon = lon2 - lon1
            a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
            distance_km = round(2 * 6371 * asin(sqrt(a)), 1)

        services = ProviderService.query.filter_by(provider_id=p.id, is_available=True).all()
        service_names = [s.name for s in services if s.name]
        all_tags = set()
        for s in services:
            if s.tags:
                for t in s.tags.split(','):
                    t = t.strip()
                    if t:
                        all_tags.add(t)

        reviews = Review.query.filter_by(provider_id=p.id).all()
        avg_rating = round(sum(r.rating for r in reviews) / len(reviews), 1) if reviews else None

        photo_url = None
        if p.photo:
            try:
                photo_url = get_file_url(p.photo, buckets['profile_pictures'])
            except Exception:
                pass

        providers_data.append({
            'id': p.id,
            'name': p.full_name or p.user_name,
            'username': p.user_name,
            'address': p.address,
            'online': p.online,
            'latitude': p.latitude,
            'longitude': p.longitude,
            'distance_km': distance_km,
            'services_count': len(services),
            'service_names': service_names,
            'avg_rating': avg_rating,
            'review_count': len(reviews),
            'photo': photo_url,
            'verified': p.is_verified,
            'service_tags': list(all_tags),
        })

    return jsonify({'success': True, 'providers': providers_data})


@client_bp.route('/update_location', methods=['POST'])
@login_required
def update_location():
    if current_user.role != 'client':
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    try:
        data = request.get_json()
        if not data or 'latitude' not in data or 'longitude' not in data:
            return jsonify({'success': False, 'message': 'Coordinates are required'}), 400

        ok, err = validate_coordinates(data['latitude'], data['longitude'])
        if not ok:
            return jsonify({'success': False, 'message': err}), 400

        current_user.latitude = float(data['latitude'])
        current_user.longitude = float(data['longitude'])
        current_user.location_approved = True
        db.session.commit()

        return jsonify({'success': True, 'message': 'Location updated'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@client_bp.route('/working_hours')
@login_required
def working_hours():
    if current_user.role != 'client':
        return jsonify({'error': 'access denied'}), 403

    provider_id = request.args.get('provider_id')
    service_id = request.args.get('service_id')
    date_work = request.args.get('date')
    if not service_id or not date_work or not provider_id:
        return jsonify({'error': 'data is not here'}), 400

    service = ProviderService.query.get(service_id)
    date = datetime.strptime(date_work, '%Y-%m-%d').date()
    start_working_hours = 9
    end_working_hours = 17

    appointments_active = Appointment.query.filter(Appointment.provider_id == provider_id, db.func.date(Appointment.appointment_time) == date).all()

    return jsonify({
        'start': start_working_hours,
        'end': end_working_hours,
        'duration': service.duration if service else 60,
        'busy': [{'start': a.appointment_time.isoformat(), 'end': a.end_time.isoformat()} for a in appointments_active if a.end_time]
    })


@client_bp.route('/get_available_times')
@login_required
def get_available_times():
    if current_user.role != 'client':
        return jsonify({'error': 'access denied'}), 403

    provider_id = request.args.get('provider_id')
    service_id = request.args.get('service_id')
    date_str = request.args.get('date')

    if not all([provider_id, service_id, date_str]):
        return jsonify({'error': 'Service provider, service and date must be specified'}), 400

    try:
        date = datetime.strptime(date_str, '%Y-%m-%d').date()
        service = ProviderService.query.get(service_id)

        if not service or service.provider_id != int(provider_id):
            return jsonify({'error': 'Service provider not found'}), 404

        # working hours
        work_start = 9
        work_end = 18

        # getting all scheduled appointments for this day
        appointments = Appointment.query.filter(
            Appointment.provider_id == provider_id,
            db.func.date(Appointment.appointment_time) == date,
            Appointment.status.in_(['scheduled', 'confirmed'])
        ).all()
    # Generate available slots
        available_slots = []
        current_time = datetime.combine(date, datetime.min.time()) + timedelta(hours=work_start)
        end_time = datetime.combine(date, datetime.min.time()) + timedelta(hours=work_end)

        while current_time + timedelta(minutes=service.duration) <= end_time:
            slot_end = current_time + timedelta(minutes=service.duration)

            # Check if this slot does not overlap with existing appointments
            is_available = True
            for app in appointments:
                if (current_time < app.end_time) and (slot_end > app.appointment_time):
                    is_available = False
                    break

            if is_available:
                available_slots.append(current_time.strftime('%H:%M'))

            current_time += timedelta(minutes=30)  # Step 30 minutes

        return jsonify(available_slots)

    except Exception as e:
        current_app.logger.error(f"Error getting available times: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


@client_bp.route("/services")
@login_required
def services():
    return render_template("client/services.html")


@client_bp.route("/provider/<int:provider_id>")
@login_required
def provider_detail(provider_id):
    provider = User.query.filter_by(id=provider_id, role='provider').first_or_404()
    reviews = Review.query.filter_by(provider_id=provider.id).order_by(
        Review.created_at.desc()
    ).all()
    servises = ProviderService.query.filter_by(provider_id=provider.id, is_available=True).all()
    photo = None
    if provider.photo:
        photo = get_file_url(provider.photo, buckets['profile_pictures'])

    portfolio_items = []
    if provider.portfolio:
        try:
            import json as _json
            for item in _json.loads(provider.portfolio):
                portfolio_items.append({
                    'url': get_file_url(item['url'], buckets['profile_pictures']),
                    'type': item.get('type', 'photo'),
                })
        except Exception:
            pass

    return render_template("client/provider_public_profile.html", provider=provider, reviews=reviews, services=servises, photo=photo, portfolio_items=portfolio_items)


@client_bp.route('/history')
@login_required
def history():
    if current_user.role != 'client':
        return redirect(url_for('auth.login'))
    return render_template('client/history.html')


@client_bp.route('/get_provider_services')
@login_required
def get_provider_services():
    if current_user.role != 'client':
        return jsonify({'error': 'access denied'}), 403

    provider_id = request.args.get('provider_id')
    if not provider_id:
        return jsonify({'error': 'No services specified'}), 400

    try:
        services = ProviderService.query.filter_by(
            provider_id=provider_id,
            is_available=True
        ).all()

        services_data = [{
            'id': service.id,
            'name': service.name if service.name else service.base_service.name,
            'price': service.price,
            'duration': service.duration,
            'description': service.description
        } for service in services]

        return jsonify(services_data)
    except Exception as e:
        current_app.logger.error(f"Error getting provider services: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


@client_bp.route('/get_provider_policy')
@login_required
def get_provider_policy():
    if current_user.role != 'client':
        return jsonify({'error': 'access denied'}), 403

    provider_id = request.args.get('provider_id')
    if not provider_id:
        return jsonify({'error': 'provider_id required'}), 400

    policy = CancellationPolicy.query.filter_by(provider_id=provider_id).first()

    if not policy or policy.free_cancel_hours is None:
        return jsonify({
            'has_policy': False,
            'description': 'Free cancellation at any time'
        })

    return jsonify({
        'has_policy': True,
        'free_cancel_hours': policy.free_cancel_hours,
        'late_cancel_fee_percent': policy.late_cancel_fee_percent,
        'no_show_client_fee_percent': policy.no_show_client_fee_percent,
        'description': (
            f'Free cancellation up to {policy.free_cancel_hours}h before. '
            f'Late cancellation fee: {policy.late_cancel_fee_percent}%. '
            f'No-show fee: {policy.no_show_client_fee_percent}%.'
        )
    })
