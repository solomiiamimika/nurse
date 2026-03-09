from . import provider_bp
from flask import Blueprint, jsonify, request, current_app, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models import User, Message, db, Service, ProviderService, Appointment, ClientSelfCreatedAppointment, RequestOfferResponse, ServiceHistory, CancellationPolicy, Review
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
    from flask import make_response
    resp = make_response(render_template('provider/dashboard.html'))
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    return resp


@provider_bp.route('/client/<int:client_id>')
@login_required
def client_profile(client_id):
    if current_user.role != 'provider':
        return redirect(url_for('auth.login'))
    client = User.query.get_or_404(client_id)
    if client.role != 'client':
        return redirect(url_for('provider.dashboard'))

    # Get shared appointment history
    history = ServiceHistory.query.filter_by(
        provider_id=current_user.id, client_id=client_id
    ).order_by(ServiceHistory.appointment_time.desc()).all()

    # Get reviews left by this client for this provider
    reviews = Review.query.filter_by(
        patient_id=client_id, provider_id=current_user.id, review_direction='client_to_provider'
    ).all()

    return render_template('provider/client_profile.html', client=client, history=history, reviews=reviews)


@provider_bp.route('/get_clients_locations')
@login_required
def get_clients_locations():
    if current_user.role != 'provider':
        return jsonify({'error': 'Access denied'}), 403

    try:
        provider_lat = current_user.latitude
        provider_lng = current_user.longitude

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
            if provider_lat and provider_lng:
                dist = haversine_distance(provider_lat, provider_lng, client.latitude, client.longitude)
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
        return jsonify({'success': False, 'message': 'Internal server error'}), 500


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
        return jsonify({'success': False, 'message': 'Internal server error'}), 500


@socketio.on('connect')
def handle_connect():
    if not current_user.is_authenticated:
        return False  # Reject unauthenticated connections
    current_app.logger.info(f"SocketIO connected: user={current_user.id} sid={request.sid}")
    emit('connection_response', {'status': 'connected'})


@socketio.on('disconnect')
def handle_disconnect():
    current_app.logger.info(f"SocketIO disconnected: sid={request.sid}")


@socketio.on('join')
def handle_join(data):
    if not current_user.is_authenticated:
        return
    user_id = data.get('user_id')
    # Only allow joining your own room
    if user_id and int(user_id) == current_user.id:
        join_room(f"user_{user_id}")
        current_app.logger.info(f'User {user_id} joined room')


@socketio.on('send_message')
def handle_send_message(data):
    try:
        if not current_user.is_authenticated:
            emit('error', {'message': 'Not authenticated'}, room=request.sid)
            return

        if not all(key in data for key in ['text', 'recipient_id']):
            emit('error', {'message': 'Missing required fields'}, room=request.sid)
            return

        msg_type = data.get('message_type', 'text')
        proposal_status = 'pending' if msg_type == 'proposal' else None

        # Always use current_user.id as sender (prevents spoofing)
        message = Message(
            sender_id=current_user.id,
            recipient_id=int(data['recipient_id']),
            text=data['text'],
            message_type=msg_type,
            proposal_status=proposal_status
        )

        db.session.add(message)
        db.session.commit()

        sender_name = current_user.user_name

        emit('new_message', {
            'id': message.id,
            'sender_id': message.sender_id,
            'sender_name': sender_name,
            'text': message.text,
            'message_type': msg_type,
            'proposal_status': proposal_status,
            'timestamp': message.timestamp.isoformat()
        }, room=f"user_{message.recipient_id}")

        emit('message_sent', {
            'id': message.id,
            'status': 'delivered'
        }, room=request.sid)

        # Forward to Telegram if recipient has it linked
        try:
            recipient = User.query.get(int(data['recipient_id']))
            if recipient and recipient.telegram_id and recipient.telegram_notifications:
                from app.telegram.notifications import send_user_telegram
                sender_display = current_user.full_name or current_user.user_name
                base_url = current_app.config.get('BASE_URL', 'https://human-me.com')
                tg_text = f"<b>{sender_display}:</b>\n{data['text']}"
                send_user_telegram(recipient.id, tg_text, reply_markup={
                    'inline_keyboard': [[
                        {'text': 'Reply on website', 'url': f"{base_url}/chat/{current_user.id}"}
                    ]]
                })
        except Exception:
            current_app.logger.error("Failed to forward chat message to Telegram")

    except Exception as e:
        current_app.logger.error(f"SocketIO send_message error: {e}")
        emit('error', {'message': 'Failed to send message'}, room=request.sid)
        db.session.rollback()


@socketio.on('start_trip')
def handle_start_trip(data):
    if not current_user.is_authenticated or current_user.role != 'provider':
        return
    client_id = data.get('client_id')
    if not client_id:
        return
    current_app.logger.info(f"Provider {current_user.id} started trip to Client {client_id}")
    emit('trip_started', {
        'message': f"{current_user.full_name} is on the way!",
        'provider_id': current_user.id
    }, room=f"user_{client_id}")


@socketio.on('update_location')
def handle_location_update(data):
    if not current_user.is_authenticated or current_user.role != 'provider':
        return
    client_id = data.get('client_id')
    if not client_id:
        return
    emit('provider_location_update', {
        'lat': data.get('lat'),
        'lng': data.get('lng')
    }, room=f"user_{client_id}")


@socketio.on('end_trip')
def handle_end_trip(data):
    if not current_user.is_authenticated or current_user.role != 'provider':
        return
    client_id = data.get('client_id')
    if not client_id:
        return
    emit('trip_ended', {'message': "Arrived!"}, room=f"user_{client_id}")


@provider_bp.route('/leave_review', methods=['POST'])
@login_required
def provider_leave_review():
    """Provider reviews a client after a completed appointment."""
    if current_user.role != 'provider':
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    data = request.get_json() or {}
    appointment_id = data.get('appointment_id')
    rating = data.get('rating')
    comment = data.get('comment', '').strip()

    if not appointment_id or rating is None:
        return jsonify({'success': False, 'message': 'appointment_id and rating are required'}), 400

    try:
        rating = int(rating)
        if rating < 1 or rating > 5:
            raise ValueError
    except Exception:
        return jsonify({'success': False, 'message': 'Rating must be an integer from 1 to 5'}), 400

    if rating <= 3 and not comment:
        return jsonify({'success': False, 'message': 'Please provide a reason for your low rating'}), 400

    appo = Appointment.query.filter_by(id=appointment_id, provider_id=current_user.id).first()
    if not appo:
        return jsonify({'success': False, 'message': 'Appointment not found'}), 404
    if appo.status not in ('confirmed_paid', 'completed'):
        return jsonify({'success': False, 'message': 'Review can only be left after the appointment is completed'}), 400

    existing = Review.query.filter_by(
        provider_id=current_user.id,
        patient_id=appo.client_id,
        appointment_id=appo.id,
        review_direction='provider_to_client'
    ).first()
    if existing:
        return jsonify({'success': False, 'message': 'Review already left'}), 400

    review = Review(
        patient_id=appo.client_id,
        provider_id=current_user.id,
        appointment_id=appo.id,
        rating=rating,
        comment=comment,
        review_direction='provider_to_client'
    )
    db.session.add(review)
    db.session.commit()

    return jsonify({'success': True, 'message': 'Thank you for your review!'})


@provider_bp.route('/get_provider_review/<int:appointment_id>')
@login_required
def get_provider_review(appointment_id):
    """Check if provider already reviewed the client for this appointment."""
    review = Review.query.filter_by(
        appointment_id=appointment_id,
        provider_id=current_user.id,
        review_direction='provider_to_client'
    ).first()

    if review:
        return jsonify({
            'success': True,
            'review': {
                'rating': review.rating,
                'comment': review.comment,
                'created_at': review.created_at.isoformat()
            }
        })
    return jsonify({'success': False})


@provider_bp.route('/my_reviews')
@login_required
def my_reviews():
    """Get all reviews received by the provider."""
    reviews = Review.query.filter_by(
        provider_id=current_user.id,
        review_direction='client_to_provider'
    ).order_by(Review.created_at.desc()).all()

    return jsonify({
        'reviews': [{
            'id': r.id,
            'patient_name': r.patient.full_name or r.patient.user_name,
            'rating': r.rating,
            'comment': r.comment,
            'response_text': r.response_text,
            'response_at': r.response_at.isoformat() if r.response_at else None,
            'created_at': r.created_at.isoformat(),
        } for r in reviews]
    })
