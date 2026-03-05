from . import provider_bp
from flask import Blueprint, jsonify, request, current_app, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models import User, Message, db, Service, ProviderService, Appointment, ClientSelfCreatedAppointment, RequestOfferResponse, ServiceHistory, CancellationPolicy
from app.utils import fuzz_coordinates, haversine_distance, validate_coordinates
from datetime import datetime
import json
from app.supabase_storage import get_file_url, delete_from_supabase, upload_to_supabase, buckets, supabase
import os
from werkzeug.utils import secure_filename
from math import radians, sin, cos, sqrt, atan2
import stripe
from app.extensions import socketio, db
from flask import current_app, request
from flask_socketio import join_room, leave_room, emit
from app.models import Message, db, User
from datetime import datetime
from sqlalchemy import func
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'app', 'static', 'uploads')
DOCUMENTS_FOLDER = os.path.join(UPLOAD_FOLDER, 'documents')
PROFILE_PICTURES_FOLDER = os.path.join(UPLOAD_FOLDER, 'profile_pictures')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx'}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DOCUMENTS_FOLDER, exist_ok=True)
os.makedirs(PROFILE_PICTURES_FOLDER, exist_ok=True)


def calendar_appointment_color(Status):
    colors_dictionary = {
        'scheduled': 'gray',
        'request_sended': 'yellow',
        'nurse_confirmed': 'green',
        'completed': 'blue',
        'cancelled': 'red'
    }
    return colors_dictionary.get(Status)


@provider_bp.route('/appointments')
@login_required
def appointments():
    if current_user.role != 'provider':
        return jsonify({'error': 'Access denied'}), 403
    return render_template('provider/appointments.html')


@provider_bp.route('/get_appointments')
@login_required
def get_appointments():
    print("Received request to /nurse/get_appointments")  # Logging
    if current_user.role != 'provider':
        return jsonify({'error': 'Access denied'}), 403

    try:
        start_date = request.args.get('start')
        end_date = request.args.get('end')
        query = Appointment.query.filter_by(provider_id=current_user.id)

        if start_date and end_date:
            try:
                start = datetime.fromisoformat(start_date)

                end = datetime.fromisoformat(end_date)
                query = query.filter(
                    Appointment.appointment_time >= start,
                    Appointment.appointment_time <= end
                )
            except ValueError as e:
                print(f"Error parsing date format: {e}")

        appointments = query.all()
        result = []

        for app in appointments:
            service_name = app.nurse_service.name if app.nurse_service else "Service"
            result.append({
                'id': app.id,
                'title': f"{service_name} - {app.client.user_name}",
                'start': app.appointment_time.isoformat(),
                'end': app.end_time.isoformat(),
                'color': calendar_appointment_color(app.status),
                'extendedProps': {
                    'client_name': app.client.user_name,
                    'nurse_name': app.provider.user_name,
                    'status': app.status,
                    'notes': app.notes,
                    'photo': app.client.photo if app.client.photo else None
                }
            })

        print(f"Returning {len(result)} records")  # Logging
        return jsonify(result)

    except Exception as e:
        print(f"Error in get_appointments: {str(e)}")  # Logging
        return jsonify({'error': 'Internal server error'}), 500


@provider_bp.route('/get_my_appointments')
@login_required
def get_my_appointments():
    if current_user.role != 'provider':
        return jsonify({'error': 'Access denied'}), 403

    try:
        # Беремо тільки майбутні та підтверджені записи
        # Можна додати status='confirmed' або 'paid', залежно від вашої логіки
        appointments = Appointment.query.filter(
            Appointment.provider_id == current_user.id,
            Appointment.appointment_time >= datetime.utcnow(),
            Appointment.status.in_(['confirmed', 'confirmed_paid', 'scheduled'])  # Додайте ваші статуси
        ).order_by(Appointment.appointment_time.asc()).all()

        result = []
        for app in appointments:
            # Отримуємо назву сервісу та ціну
            service_name = app.nurse_service.name if app.nurse_service else "Service"
            price = app.nurse_service.price if app.nurse_service else 0

            result.append({
                'id': app.id,
                'service_name': service_name,
                'patient_name': app.client.full_name or app.client.user_name,
                'appointment_start_time': app.appointment_time.isoformat(),
                'payment': price,
                'notes': app.notes,
                # ВАЖЛИВО: Координати клієнта для карти
                'latitude': app.client.latitude,
                'longitude': app.client.longitude,
                'type': 'appointment',
                'client_id': app.client.id
            })

        return jsonify(result)

    except Exception as e:
        print(f"Error in get_my_appointments: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


@provider_bp.route('/update_appointment_status', methods=['POST'])
@login_required
def update_appointment_status():
    data = request.get_json()
    appointment_id = data.get('appointment_id')
    new_status = data.get('status')

    appointment = Appointment.query.get_or_404(appointment_id)
    if appointment.provider_id != current_user.id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    # Logic: Nurse Marks Job as Done
    if new_status == 'work_submitted':
        if appointment.status != 'confirmed_paid':
            return jsonify({'success': False, 'message': 'Cannot submit work for unpaid appointment'}), 400

        appointment.status = 'work_submitted'
        db.session.commit()
        return jsonify({'success': True, 'message': 'Work submitted! Waiting for client approval.'})

    # Logic: Nurse Accepts/Declines
    elif new_status in ['confirmed', 'cancelled']:
        appointment.status = new_status
        db.session.commit()
        return jsonify({'success': True})

    return jsonify({'success': False, 'message': 'Invalid status update for Nurse'}), 400


@provider_bp.route('/nurse_get_requests', methods=['GET'])
@login_required
def nurse_get_requests():
    if current_user.role != 'provider':
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    try:
        nurse_lat = current_user.latitude
        nurse_lng = current_user.longitude

        # Already-bid request IDs for this provider
        already_bid_ids = {
            o.request_id for o in RequestOfferResponse.query.filter_by(
                provider_id=current_user.id
            ).all()
        }

        requests = ClientSelfCreatedAppointment.query.filter(
            ClientSelfCreatedAppointment.status.in_(('pending', 'has_offers'))
        ).all()

        result = []
        for req in requests:
            if req.id in already_bid_ids:
                continue
            if not req.latitude or not req.longitude:
                continue

            # Для перегляду запиту: відстань + розмиті координати для карти
            # Точна адреса буде видна тільки після прийняття
            distance_km = None
            if nurse_lat and nurse_lng:
                distance_km = round(haversine_distance(
                    nurse_lat, nurse_lng, req.latitude, req.longitude
                ), 1)
                # Only show requests within 50 km radius
                if distance_km > 50:
                    continue

            f_lat, f_lng = fuzz_coordinates(req.latitude, req.longitude, meters=300)

            result.append({
                'id': req.id,
                'patient_name': req.patient.full_name if req.patient else "Client",
                'service_name': req.service_name,
                'appointment_start_time': req.appointment_start_time.isoformat(),
                'lat': f_lat,          # розмиті координати для карти
                'lng': f_lng,
                'distance_km': distance_km,  # відстань для рішення
                'notes': req.notes,
                'payment': req.payment
            })

        return jsonify({'success': True, 'requests': result}), 200

    except Exception as e:
        print(e)
        return jsonify({'success': False, 'error': 'Server Error'}), 500


@provider_bp.route('/nurse_accept_request/<int:request_id>', methods=['POST'])
@login_required
def nurse_accept_request(request_id):
    if current_user.role != 'provider':
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    try:
        data = request.get_json() or {}
        price = data.get('price')

        req = ClientSelfCreatedAppointment.query.get(request_id)

        if not req:
            return jsonify({'success': False, 'message': 'Request not found'}), 404

        if req.status not in ('pending', 'has_offers'):
            return jsonify({'success': False, 'message': 'Request already processed'}), 400

        # Prevent duplicate offer from same provider
        existing = RequestOfferResponse.query.filter_by(
            request_id=req.id, provider_id=current_user.id
        ).first()
        if existing:
            return jsonify({'success': False, 'message': 'You already sent an offer for this request'}), 400

        # Mark request as having offers (stays visible to other providers)
        req.status = 'has_offers'

        new_offer = RequestOfferResponse(request_id=req.id, provider_id=current_user.id, proposed_price=price)
        db.session.add(new_offer)
        db.session.commit()
        return jsonify({'success': True})

    except Exception as e:
        current_app.logger.error(f"Error accepting request: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


@provider_bp.route('/nurse_get_accepted_requests', methods=['GET'])
@login_required
def nurse_get_accepted_requests():
    if current_user.role != 'provider':
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    try:
        # All offers this provider sent, joined with the request
        my_offers = RequestOfferResponse.query.filter_by(
            provider_id=current_user.id
        ).order_by(RequestOfferResponse.created_at.desc()).all()

        result = []
        for offer in my_offers:
            req = offer.appointment_requests  # backref on ClientSelfCreatedAppointment
            if not req:
                continue
            # Show address only when client accepted this provider's offer
            show_address = (offer.status == 'accepted')
            result.append({
                'id': req.id,
                'offer_id': offer.id,
                'offer_status': offer.status,   # pending | accepted | rejected
                'patient_name': req.patient.full_name if req.patient else '',
                'service_name': req.service_name,
                'status': req.status,
                'appointment_start_time': req.appointment_start_time.isoformat(),
                'created_appo': req.created_appo.isoformat(),
                'latitude': req.latitude if show_address else None,
                'longitude': req.longitude if show_address else None,
                'address': req.address if show_address else None,
                'notes': req.notes,
                'payment': offer.proposed_price,
            })

        return jsonify({'success': True, 'requests': result}), 200

    except Exception as e:
        current_app.logger.error(f"Error retrieving accepted requests: {str(e)}")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500
