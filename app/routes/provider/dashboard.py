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

CLIENTS_MAP_RADIUS_KM = 30  # показуємо запити тільки в межах 30 км


@provider_bp.route('/dashboard')
@login_required
def dashboard():
    if current_user.role != 'provider':
        return redirect(url_for('auth.login'))
    return render_template('provider/dashboard.html')


@provider_bp.route('/get_clients_locations')
@login_required
def get_clients_locations():
    if current_user.role != 'provider':
        return jsonify({'error': 'Access denied'}), 403

    try:
        nurse_lat = current_user.latitude
        nurse_lng = current_user.longitude

        # Показуємо тільки клієнтів з відкритими запитами (pending)
        open_request_patient_ids = db.session.query(
            ClientSelfCreatedAppointment.patient_id
        ).filter(
            ClientSelfCreatedAppointment.status == 'pending'
        ).subquery()

        clients = User.query.filter(
            User.id.in_(open_request_patient_ids),
            User.location_approved == True,
            User.latitude.isnot(None),
            User.longitude.isnot(None)
        ).all()

        clients_data = []
        for client in clients:
            # Фільтр по радіусу (якщо знаємо де провайдер)
            if nurse_lat and nurse_lng:
                dist = haversine_distance(nurse_lat, nurse_lng, client.latitude, client.longitude)
                if dist > CLIENTS_MAP_RADIUS_KM:
                    continue

            # Фаззимо ±500м — провайдер бачить район, не точну адресу
            f_lat, f_lng = fuzz_coordinates(client.latitude, client.longitude, meters=500)
            clients_data.append({
                'id': client.id,
                'lat': f_lat,
                'lng': f_lng,
            })

        return jsonify(clients_data)
    except Exception as e:
        current_app.logger.error(f"Error getting clients locations: {str(e)}")
        return jsonify({'error': 'Server error'}), 500


@provider_bp.route('/update_location', methods=['POST'])
@login_required
def update_location():
    if current_user.role != 'provider':
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


@provider_bp.route('/toggle_online', methods=['POST'])
@login_required
def toggle_online():
    if current_user.role != 'provider':
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    try:
        current_user.online = not current_user.online
        db.session.commit()
        return jsonify({
            'success': True,
            'online': current_user.online
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@socketio.on('connect')
def handle_connect():
    print(f"Client connected: {request.sid}")
    emit('connection_response', {'status': 'connected'})


@socketio.on('disconnect')
def handle_disconnect():
    print(f"Client disconnected: {request.sid}")


@socketio.on('join')
def handle_join(data):
    user_id = data.get('user_id')
    if user_id:
        join_room(f"user_{user_id}")
        current_app.logger.info(f'User {user_id} joined the room')


@socketio.on('send_message')
def handle_send_message(data):
    try:
        print(f"Received data: {data}")  # Logging incoming data

        if not all(key in data for key in ['text', 'sender_id', 'recipient_id']):
            raise ValueError("Not enough data")

        # Create a message
        message = Message(
            sender_id=int(data['sender_id']),
            recipient_id=int(data['recipient_id']),
            text=data['text']
        )

        # Save in DB
        db.session.add(message)
        db.session.commit()

        # get the senders name
        sender = User.query.get(message.sender_id)
        sender_name = sender.user_name if sender else "Unknown"

        # Send to the recipient
        emit('new_message', {
            'id': message.id,
            'sender_id': message.sender_id,
            'sender_name': sender_name,
            'text': message.text,
            'timestamp': message.timestamp.isoformat()
        }, room=f"user_{message.recipient_id}")

        # Confirmation to the sender
        emit('message_sent', {
            'id': message.id,
            'status': 'delivered'
        }, room=request.sid)

    except Exception as e:
        print(f"Error: {str(e)}")
        emit('Error', {'message': str(e)}, room=request.sid)
        db.session.rollback()


@socketio.on('start_trip')
def handle_start_trip(data):
    # data = {'appointment_id': 123, 'client_id': 45}
    client_id = data.get('client_id')
    print(f"Nurse {current_user.id} started trip to Client {client_id}")

    # Відправляємо клієнту сигнал, що медсестра виїхала
    emit('trip_started', {
        'message': f"{current_user.full_name} is on the way!",
        'nurse_id': current_user.id
    }, room=f"user_{client_id}")  # Переконайтесь, що клієнт приєднався до кімнати "user_ID"


@socketio.on('update_location')
def handle_location_update(data):
    # data = {'client_id': 45, 'lat': 50.0, 'lng': 30.0}
    client_id = data.get('client_id')

    # Пересилаємо точні координати клієнту
    emit('nurse_location_update', {
        'lat': data['lat'],
        'lng': data['lng']
    }, room=f"user_{client_id}")


@socketio.on('end_trip')
def handle_end_trip(data):
    client_id = data.get('client_id')
    emit('trip_ended', {'message': "Arrived!"}, room=f"user_{client_id}")
