from . import client_bp
from flask import render_template, redirect, url_for, flash, request, abort, jsonify, current_app, Blueprint
from sqlalchemy.sql.sqltypes import DateTime
from app.extensions import db, bcrypt, socketio, db, mail
from app.models import Appointment, ProviderService, User, Message, Payment, ClientSelfCreatedAppointment, Review, RequestOfferResponse, ServiceHistory, CancellationPolicy
from app.utils import fuzz_coordinates, validate_coordinates
from app.supabase_storage import get_file_url, delete_from_supabase, upload_to_supabase, buckets
from datetime import datetime, timedelta
import os
from werkzeug.utils import secure_filename
import json
from dotenv import load_dotenv
import stripe
import supabase
import base64
from flask_mail import Message as MailMessage
from threading import Thread
from flask import current_app, request
from flask_socketio import join_room, leave_room, emit
from app.models import Message, db, User
from datetime import datetime
from app.supabase_storage import upload_to_supabase, supabase
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

    search_query = request.args.get('q', '').strip()
    nurses = []

    if search_query:
        nurses = User.query.filter(User.role == 'provider').outerjoin(ProviderService).filter(
            (User.full_name.ilike(f'%{search_query}%')) |
            (User.user_name.ilike(f'%{search_query}%')) |
            (ProviderService.name.ilike(f'%{search_query}%')) |
            (User.address.ilike(f'%{search_query}%'))
        ).distinct().all()
    else:
        nurses = User.query.filter_by(role='provider').all()

    return render_template('client/dashboard.html', nurses=nurses, search_query=search_query, stripe_public_key=stripe_public_key)


@client_bp.route('/get_nurses_locations')
@login_required
def get_nurses_locations():
    if current_user.role != 'client':
        return jsonify({'error': 'Entrance not allowed'}), 403

    nurses = User.query.filter(
        User.role == 'provider',
        User.location_approved == True,
        User.latitude.isnot(None),
        User.longitude.isnot(None)
    ).all()

    nurses_data = []
    for nurse in nurses:
        # Фаззимо ±100м — клієнт бачить район де живе медсестра, не точну адресу
        f_lat, f_lng = fuzz_coordinates(nurse.latitude, nurse.longitude, meters=100)
        nurses_data.append({
            'id': nurse.id,
            'name': nurse.user_name,
            'lat': f_lat,
            'lng': f_lng,
            'online': nurse.online
        })

    return jsonify(nurses_data)


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

    nurse_id = request.args.get('nurse_id')
    service_id = request.args.get('service_id')
    date_work = request.args.get('date')
    if not service_id or service_id or nurse_id:
        return jsonify({'error': 'data is not here'}), 400

    service = ProviderService.query.get(service_id)
    date = datetime.strptime(date_work, '%Y-%m-%d').date()
    start_working_hours_nurse = 9
    end_working_hours_nurse = 17

    appointments_active = Appointment.query.filter(Appointment.nurse_id == nurse_id, db.func.date(Appointment.appointment_time) == date).all()


@client_bp.route('/get_available_times')
@login_required
def get_available_times():
    if current_user.role != 'client':
        return jsonify({'error': 'access denied'}), 403

    nurse_id = request.args.get('nurse_id')
    service_id = request.args.get('service_id')
    date_str = request.args.get('date')

    if not all([nurse_id, service_id, date_str]):
        return jsonify({'error': 'Service provider, service and date must be specified'}), 400

    try:
        date = datetime.strptime(date_str, '%Y-%m-%d').date()
        service = ProviderService.query.get(service_id)

        if not service or service.provider_id != int(nurse_id):
            return jsonify({'error': 'Service provider not found'}), 404

        # working hours
        work_start = 9
        work_end = 18

        # getting all scheduled appointments for this day
        appointments = Appointment.query.filter(
            Appointment.provider_id == nurse_id,
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
    servises = ProviderService.query.filter_by(nurse_id=provider.id, is_available=True).all()
    photo = None
    if provider.photo:
        photo = get_file_url(provider.photo, buckets['profile_pictures'])
    return render_template("client/provider_public_profile.html", provider=provider, reviews=reviews, services=servises, photo=photo)


@client_bp.route('/get_nurse_services')
@login_required
def get_nurse_services():
    if current_user.role != 'client':
        return jsonify({'error': 'access denied'}), 403

    nurse_id = request.args.get('nurse_id')
    if not nurse_id:
        return jsonify({'error': 'No services specified'}), 400

    try:
        services = ProviderService.query.filter_by(
            provider_id=nurse_id,
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
        current_app.logger.error(f"Error getting nurse services: {str(e)}")
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
