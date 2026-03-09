from flask import Blueprint, jsonify, request, current_app, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models import User, Message, db, Service, NurseService, Appointment, ClientSelfCreatedAppointment, RequestOfferResponse, ServiceHistory, CancellationPolicy
from app.utils import fuzz_coordinates, haversine_distance, validate_coordinates
from datetime import datetime
import json
from app.supabase_storage import get_file_url,delete_from_supabase,upload_to_supabase,buckets,supabase
import os
from werkzeug.utils import secure_filename
from math import radians, sin, cos, sqrt, atan2
nurse_bp = Blueprint('nurse', __name__)
import stripe
from app.extensions import socketio, db
from flask import current_app, request
from flask_socketio import join_room, leave_room, emit
from app.models import Message, db,User
from datetime import datetime
from sqlalchemy import func
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'app', 'static', 'uploads')
DOCUMENTS_FOLDER = os.path.join(UPLOAD_FOLDER, 'documents')
PROFILE_PICTURES_FOLDER = os.path.join(UPLOAD_FOLDER, 'profile_pictures')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx'}


os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DOCUMENTS_FOLDER, exist_ok=True)
os.makedirs(PROFILE_PICTURES_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@nurse_bp.route('/dashboard')
@login_required
def dashboard():
    if current_user.role != 'nurse':
        return redirect(url_for('auth.login'))
    return render_template('provider/dashboard.html')

@nurse_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if current_user.role != 'nurse':
        return redirect(url_for('auth.login'))
    
    formatted_date = current_user.date_birth.strftime('%Y-%m-%d') if current_user.date_birth else ''
    
    if request.method == 'POST':
        try:
            current_user.full_name = request.form.get('full_name')
            current_user.phone_number = request.form.get('phone_number')
            current_user.about_me = request.form.get('about_me')
            current_user.address = request.form.get('address')
            current_user.password_hash = request.form.get('password')
            
            date_birth_str = request.form.get('date_birth')
            if date_birth_str:
                current_user.date_birth = datetime.strptime(date_birth_str, '%Y-%m-%d').date()
            
            if 'profile_picture' in request.files:
                file = request.files['profile_picture']
                if file and file.filename != '' and allowed_file(file.filename):
                    if current_user.photo:
                        delete_from_supabase(current_user.photo, buckets['profile_pictures'])
                    
                    filename, file_url = upload_to_supabase(
                        file, 
                        buckets['profile_pictures'], 
                        current_user.id, 
                        'nurse_profile'
                    )
                    if filename:
                        current_user.photo = filename

            if 'documents' in request.files:
                documents = request.files.getlist('documents')
                saved_docs = []
                for doc in documents:
                    if doc and doc.filename != '' and allowed_file(doc.filename):
                        filename, file_url = upload_to_supabase(
                            doc, 
                            buckets['documents'], 
                            current_user.id, 
                            'nurse_doc'
                        )
                        if filename:
                            saved_docs.append(filename)
                
                if saved_docs:
                    current_docs = json.loads(current_user.documents) if current_user.documents else []
                    current_docs.extend(saved_docs)
                    current_user.documents = json.dumps(current_docs)
            
            db.session.commit()
            flash('Profile successfully updated!', 'success')
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating profile: {str(e)}")
            flash(f'Error updating profile: {str(e)}', 'danger')
        
        return redirect(url_for('nurse.profile'))
    
    profile_photo = None
    if current_user.photo:
        profile_photo = get_file_url(current_user.photo, buckets['profile_pictures'])
        
    documents_urls = {}
    if current_user.documents:
        try:
            documents_list = json.loads(current_user.documents)
            for doc_name in documents_list:
                documents_urls[doc_name] = get_file_url(doc_name, buckets['documents'])
        except json.JSONDecodeError:
            documents_urls = {}

    return render_template('provider/profile.html',
                           formatted_date=formatted_date,
                           documents_urls=documents_urls, 
                           profile_photo=profile_photo,   
                           user=current_user)
@nurse_bp.route('/delete_document', methods=['POST'])
@login_required
def delete_document():
    try:
        data = request.get_json() 
        doc_name = data.get('doc_name')

        delete_from_supabase(doc_name, buckets['documents'])
        
        if current_user.documents:
            docs = json.loads(current_user.documents)
            if doc_name in docs:
                docs.remove(doc_name)
                current_user.documents = json.dumps(docs) if docs else None
                db.session.commit()
                return jsonify({'success': True})
        
        return jsonify({'success': False, 'message': 'Doc not found'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
@nurse_bp.route('/appointments')
@login_required
def appointments():
    if current_user.role != 'nurse':
        return jsonify({'error': 'Access denied'}), 403
    return render_template('provider/appointments.html')

@nurse_bp.route('/update_location', methods=['POST'])
@login_required
def update_location():
    if current_user.role != 'nurse':
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

@nurse_bp.route('/toggle_online', methods=['POST'])
@login_required
def toggle_online():
    if current_user.role != 'nurse':
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

CLIENTS_MAP_RADIUS_KM = 30  # показуємо запити тільки в межах 30 км

@nurse_bp.route('/get_clients_locations')
@login_required
def get_clients_locations():
    if current_user.role != 'nurse':
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
    
    
    
@nurse_bp.route('/services', methods=['GET', 'POST'])
@login_required
def manage_services():
    if current_user.role != 'nurse':
        return redirect(url_for('auth.login'))

    standard_services = Service.query.filter_by(is_standart=True).all()
    nurse_services = NurseService.query.filter_by(provider_id=current_user.id).all()

    if request.method == 'POST':
        try:
            action = request.form.get('action')
            
            if action == 'add_custom':
                new_service = NurseService(
                    provider_id=current_user.id,
                    service_id=None,
                    name=request.form.get('name'),
                    price=float(request.form.get('price')),
                    duration=int(request.form.get('duration')),
                    description=request.form.get('description', ''),
                    is_available='is_available' in request.form
                )
                db.session.add(new_service)
                flash('Custom service added successfully', 'success')
            
            elif action == 'add':
                service_id = request.form.get('service_id')
                if not service_id:
                    flash('No service selected', 'danger')
                    return redirect(url_for('nurse.manage_services'))
                
                new_service = NurseService(
                    provider_id=current_user.id,
                    service_id=service_id,
                    name=None,
                    price=float(request.form.get('price')),
                    duration=int(request.form.get('duration')),
                    description=request.form.get('description', ''),
                    is_available='is_available' in request.form
                )
                db.session.add(new_service)
                flash('Standard service added successfully', 'success')
            
            elif action == 'update':
                service_id = request.form.get('service_id')
                is_custom = request.form.get('is_custom') == 'true'
                
                if is_custom:
                    service = NurseService.query.filter_by(
                        id=service_id,
                        provider_id=current_user.id
                    ).first()
                    if service:
                        service.name = request.form.get('name')
                else:
                    service = NurseService.query.filter_by(
                        service_id=service_id,
                        provider_id=current_user.id
                    ).first()
                
                if service:
                    service.price = float(request.form.get('price'))
                    service.duration = int(request.form.get('duration'))
                    service.description = request.form.get('description', '')
                    service.is_available = 'is_available' in request.form
                    flash('Service updated successfully', 'success')
                else:
                    flash('Service not found', 'danger')
            
            elif action == 'remove':
                service_id = request.form.get('service_id')
                service = NurseService.query.filter_by(
                    service_id=service_id,
                    provider_id=current_user.id
                ).first()
                
                if service:
                    db.session.delete(service)
                    flash('Standard service removed successfully', 'success')
                else:
                    flash('Service not found', 'danger')
            
            elif action == 'remove_custom':
                service_id = request.form.get('service_id')
                service = NurseService.query.filter_by(
                    id=service_id,
                    provider_id=current_user.id
                ).first()
                
                if service:
                    db.session.delete(service)
                    flash('Custom service removed successfully', 'success')
                else:
                    flash('Service not found', 'danger')

            db.session.commit()
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error managing services: {str(e)}")
            flash(f'Error processing request: {str(e)}', 'danger')
        
        return redirect(url_for('nurse.manage_services'))

    return render_template('provider/services.html',
                         standard_services=standard_services,
                         nurse_services=nurse_services)


@nurse_bp.route('/service_history', methods=['GET'])
@login_required
def get_service_history():
    if current_user.role != 'nurse':
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    try:
        history = ServiceHistory.query.filter_by(
            provider_id=current_user.id
        ).order_by(ServiceHistory.created_at.desc()).all()

        result = []
        for h in history:
            result.append({
                'id': h.id,
                'service_name': h.service_name,
                'service_description': h.service_description,
                'price': h.price,
                'appointment_time': h.appointment_time.isoformat(),
                'end_time': h.end_time.isoformat(),
                'status': h.status,
                'created_at': h.created_at.isoformat(),
                'client_name': h.client.full_name or h.client.user_name if h.client else None,
            })

        return jsonify({'success': True, 'history': result}), 200

    except Exception as e:
        current_app.logger.error(f"Error getting service history: {str(e)}")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


@nurse_bp.route('/promote_from_history/<int:history_id>', methods=['POST'])
@login_required
def promote_from_history(history_id):
    """Перенести сервіс з ServiceHistory в постійний NurseService."""
    if current_user.role != 'nurse':
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    try:
        history_entry = ServiceHistory.query.filter_by(
            id=history_id,
            provider_id=current_user.id
        ).first()

        if not history_entry:
            return jsonify({'success': False, 'message': 'History entry not found'}), 404

        data = request.get_json() or {}
        price = float(data.get('price', history_entry.price))
        duration_minutes = int(data.get('duration', 60))
        name = data.get('name', history_entry.service_name)
        description = data.get('description', history_entry.service_description or '')

        # Перевіряємо чи вже є такий самий кастомний сервіс
        existing = NurseService.query.filter_by(
            provider_id=current_user.id,
            name=name,
            service_id=None
        ).first()

        if existing:
            return jsonify({'success': False, 'message': 'Service with this name already exists'}), 400

        new_service = NurseService(
            provider_id=current_user.id,
            service_id=None,
            name=name,
            price=price,
            duration=duration_minutes,
            description=description,
            is_available=True
        )
        db.session.add(new_service)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Service added to your permanent services',
            'nurse_service_id': new_service.id
        }), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error promoting from history: {str(e)}")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


@nurse_bp.route('/get_my_appointments')
@login_required
def get_my_appointments():
    if current_user.role != 'nurse':
        return jsonify({'error': 'Access denied'}), 403
    
    try:
        # Беремо тільки майбутні та підтверджені записи
        # Можна додати status='confirmed' або 'paid', залежно від вашої логіки
        appointments = Appointment.query.filter(
            Appointment.provider_id == current_user.id,
            Appointment.appointment_time >= datetime.utcnow(),
            Appointment.status.in_(['confirmed', 'confirmed_paid', 'scheduled']) # Додайте ваші статуси
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
                'type': 'appointment' ,
                'client_id':app.client.id
            })

        return jsonify(result)

    except Exception as e:
        print(f"Error in get_my_appointments: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500













@nurse_bp.route('/get_appointments')
@login_required
def get_appointments():
    print("Received request to /nurse/get_appointments")  # Logging
    if current_user.role != 'nurse':
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

def calendar_appointment_color(Status):
    colors_dictionary={
        'scheduled':'gray',
        'request_sended':'yellow',
        'nurse_confirmed':'green',
        'completed':'blue',
        'cancelled':'red'

    }
    return colors_dictionary.get(Status) 


@nurse_bp.route('/update_appointment_status', methods=['POST'])
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
        
        appointment.set_status('work_submitted')
        db.session.commit()
        return jsonify({'success': True, 'message': 'Work submitted! Waiting for client approval.'})

    # Logic: Nurse Accepts/Declines
    elif new_status in ['confirmed', 'cancelled']:
        appointment.set_status(new_status)
        db.session.commit()
        return jsonify({'success': True})

    return jsonify({'success': False, 'message': 'Invalid status update for Nurse'}), 400


@nurse_bp.route('/cancellation_policy', methods=['GET', 'POST'])
@login_required
def cancellation_policy():
    if current_user.role != 'nurse':
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    policy = CancellationPolicy.query.filter_by(provider_id=current_user.id).first()

    if request.method == 'GET':
        if policy:
            return jsonify({
                'has_policy': True,
                'free_cancel_hours': policy.free_cancel_hours,
                'late_cancel_fee_percent': policy.late_cancel_fee_percent,
                'no_show_client_fee_percent': policy.no_show_client_fee_percent,
            })
        return jsonify({
            'has_policy': False,
            'free_cancel_hours': None,
            'late_cancel_fee_percent': 0,
            'no_show_client_fee_percent': 0,
        })

    # POST — зберегти або оновити
    try:
        data = request.get_json()

        free_cancel_hours = data.get('free_cancel_hours')
        if free_cancel_hours is not None:
            free_cancel_hours = int(free_cancel_hours)

        late_fee = int(data.get('late_cancel_fee_percent', 0))
        no_show_fee = int(data.get('no_show_client_fee_percent', 0))

        if not (0 <= late_fee <= 100) or not (0 <= no_show_fee <= 100):
            return jsonify({'success': False, 'message': 'Fee percent must be between 0 and 100'}), 400

        if policy:
            policy.free_cancel_hours = free_cancel_hours
            policy.late_cancel_fee_percent = late_fee
            policy.no_show_client_fee_percent = no_show_fee
            policy.updated_at = datetime.now()
        else:
            policy = CancellationPolicy(
                provider_id=current_user.id,
                free_cancel_hours=free_cancel_hours,
                late_cancel_fee_percent=late_fee,
                no_show_client_fee_percent=no_show_fee,
            )
            db.session.add(policy)

        db.session.commit()
        return jsonify({'success': True, 'message': 'Policy saved'})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error saving cancellation policy: {str(e)}")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


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

        # Forward to Telegram if recipient has it linked
        try:
            recipient = User.query.get(int(data['recipient_id']))
            if recipient and recipient.telegram_id and recipient.telegram_notifications:
                from app.telegram.notifications import send_user_telegram
                sender_display = sender.full_name or sender.user_name if sender else 'Unknown'
                base_url = current_app.config.get('BASE_URL', 'https://human-me.com')
                tg_text = f"<b>{sender_display}:</b>\n{data['text']}"
                send_user_telegram(recipient.id, tg_text, reply_markup={
                    'inline_keyboard': [[
                        {'text': 'Reply on website', 'url': f"{base_url}/chat/{int(data['sender_id'])}"}
                    ]]
                })
        except Exception:
            current_app.logger.error("Failed to forward chat message to Telegram")

    except Exception as e:
        print(f"Error: {str(e)}")
        emit('Error', {'message': str(e)}, room=request.sid)
        db.session.rollback()


@nurse_bp.route('/stats')
@login_required
def nurse_stats():
    if current_user.role != 'nurse':
        return jsonify({'error': 'Access denied'}), 403

    accepted_statuses = ['confirmed', 'confirmed_paid', 'nurse_confirmed']
    accepted_count = Appointment.query.filter(
        Appointment.provider_id == current_user.id,
        Appointment.status.in_(accepted_statuses)
    ).count()

    completed_count = Appointment.query.filter(
        Appointment.provider_id == current_user.id,
        Appointment.status == 'completed'
    ).count()

    avg_rating = current_user.average_nurse_rating  # with hybrid_property
    reviews_count = current_user.reviews_nurse_count

    # Additionally: how many upcoming active requests
    upcoming_count = Appointment.query.filter(
        Appointment.provider_id == current_user.id,
        Appointment.appointment_time >= datetime.utcnow(),
        Appointment.status.in_(accepted_statuses)
    ).count()

    return jsonify({
        'nurse_id': current_user.id,
        'accepted': accepted_count,
        'completed': completed_count,
        'upcoming': upcoming_count,
        'average_rating': avg_rating,
        'reviews_count': reviews_count
    })




@nurse_bp.route('/nurse_get_requests', methods=['GET'])
@login_required
def nurse_get_requests():
    if current_user.role != 'nurse':
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    try:
        nurse_lat = current_user.latitude
        nurse_lng = current_user.longitude
        
        query = ClientSelfCreatedAppointment.query.filter_by(status='pending')

        requests = query.all()
        
        result = []
        for req in requests:
            if not req.latitude or not req.longitude:
                continue

            # Для перегляду запиту: відстань + розмиті координати для карти
            # Точна адреса буде видна тільки після прийняття
            distance_km = None
            if nurse_lat and nurse_lng:
                distance_km = round(haversine_distance(
                    nurse_lat, nurse_lng, req.latitude, req.longitude
                ), 1)

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

@nurse_bp.route('/nurse_accept_request/<int:request_id>', methods=['POST'])
@login_required
def nurse_accept_request(request_id):
    if current_user.role != 'nurse':
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    try:
        data=request.get_json()
        price=data.get('price')
        
        req = ClientSelfCreatedAppointment.query.get(request_id) # змінив назву змінної request на req, щоб не плутати з flask.request
        
        if not req:
            return jsonify({'success': False, 'message': 'Request not found'}), 404
        
        if req.status != 'pending':
            return jsonify({'success': False, 'message': 'Request already processed'}), 400
        
        req.set_status('accepted')
        req.provider_id = current_user.id

        new_offer=RequestOfferResponse(request_id=req.id, provider_id=current_user.id, proposed_price=price)
        db.session.add(new_offer)
        db.session.commit()
    
       
    except Exception as e:
        current_app.logger.error(f"Error accepting request: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': 'Internal server error'}), 500
@nurse_bp.route('/nurse_get_accepted_requests', methods=['GET'])
@login_required
def nurse_get_accepted_requests():
    if current_user.role != 'nurse':
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    try:
        requests = ClientSelfCreatedAppointment.query.filter_by(
            provider_id=current_user.id
        ).order_by(ClientSelfCreatedAppointment.created_appo.desc()).all()
        
        result = []
        for req in requests:
            result.append({
                'id': req.id,
                'patient_name': req.patient.full_name,
                'service_name': req.service_name,
                'status': req.status,
                'appointment_start_time': req.appointment_start_time.isoformat(),
                'created_appo': req.created_appo.isoformat(),
                # Точні координати — провайдер вже прийняв замовлення, потрібна навігація
                'latitude': req.latitude,
                'longitude': req.longitude,
                'notes': req.notes,
                'payment': req.payment
            })
        
        return jsonify({'success': True, 'requests': result}), 200
        
    except Exception as e:
        current_app.logger.error(f"Error retrieving accepted requests: {str(e)}")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500




def notify_nurses_about_new_appointment(appointment):
    """Notify service provider about a new request"""
    # Find all services nearby
    nurses = User.query.filter_by(role='nurse').all()
    
    for nurse in nurses:
        if nurse.latitude and nurse.longitude:
            # Calculate distance
            distance = calculate_distance(
                nurse.latitude, nurse.longitude,
                appointment.latitude, appointment.longitude
            )
            
            if distance <= 50:  # 50 km radius
                # TODO: Implement notifications (email, push, etc.)
                pass

def calculate_distance(lat1, lng1, lat2, lng2):

    
    R = 6371  # Earth’s radius in km
    
    lat1_rad = radians(lat1)
    lng1_rad = radians(lng1)
    lat2_rad = radians(lat2)
    lng2_rad = radians(lng2)
    
    dlng = lng2_rad - lng1_rad
    dlat = lat2_rad - lat1_rad
    
    a = sin(dlat/2)**2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlng/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    
    return R * c

@nurse_bp.route('/connect_stripe', methods=['GET','POST'])
@login_required
def connect_stripe():
    try:
        country = request.args.get('country', 'DE')
        account = stripe.Account.create(
            type='express',
            country=country,
            email=current_user.email,
            capabilities={
                'card_payments': {'requested': True},
                'transfers': {'requested': True},
            },
        )
        current_user.stripe_account_id = account.id
        db.session.commit()
        account_link = stripe.AccountLink.create(
            account=account.id,
            refresh_url=url_for('nurse.connect_stripe', _external=True),
            return_url=url_for('nurse.dashboard', _external=True),
            type='account_onboarding',
        )
        return redirect(account_link.url)
    except Exception as e:
        current_app.logger.error(f"Stripe connection error: {str(e)}")
        flash('Error connecting to Stripe', 'danger')
        return redirect(url_for('provider.dashboard'))
    

@nurse_bp.route('/finances')
@login_required
def provider_finances_management():
    if current_user.role != 'nurse':
        return redirect(url_for('auth.login'))
    if not current_user.stripe_account_id:
        flash('Please connect your Stripe account first.', 'warning')
        return redirect(url_for('nurse.connect_stripe'))
    try:
        stripe_account = stripe.Account.retrieve(current_user.stripe_account_id)
        balance = stripe.Balance.retrieve(stripe_account=stripe_account.id)
        payouts = stripe.Payout.list(stripe_account=stripe_account.id)
        transactions = stripe.BalanceTransaction.list(stripe_account=stripe_account.id)
        return render_template('provider/finances.html',
                               balance=balance,
                               payouts=payouts,
                               transactions=transactions)
    except Exception as e:
        current_app.logger.error(f"Error retrieving finances: {str(e)}")
        flash('Error retrieving financial data from Stripe', 'danger')
        return redirect(url_for('provider.dashboard'))
    
    
    
@socketio.on('start_trip')
def handle_start_trip(data):
    # data = {'appointment_id': 123, 'client_id': 45}
    client_id = data.get('client_id')
    print(f"Nurse {current_user.id} started trip to Client {client_id}")
    
    # Відправляємо клієнту сигнал, що медсестра виїхала
    emit('trip_started', {
        'message': f"{current_user.full_name} is on the way!",
        'nurse_id': current_user.id
    }, room=f"user_{client_id}") # Переконайтесь, що клієнт приєднався до кімнати "user_ID"

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