from flask import Blueprint, jsonify, request, current_app, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models import User, Message, db, Service, NurseService, Appointment, ClientSelfCreatedAppointment
from datetime import datetime
import json
import os
from werkzeug.utils import secure_filename
from math import radians, sin, cos, sqrt, atan2
nurse_bp = Blueprint('nurse', __name__)

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
    return render_template('nurse/dashboard.html')

@nurse_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if current_user.role != 'nurse':
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        try:
            # Оновлюємо основну інформацію
            current_user.full_name = request.form.get('full_name')
            current_user.phone_number = request.form.get('phone_number')
            current_user.about_me = request.form.get('about_me')
            current_user.address = request.form.get('address')
            
            date_birth_str = request.form.get('date_birth')
            if date_birth_str:
                current_user.date_birth = datetime.strptime(date_birth_str, '%Y-%m-%d').date()
                
            if 'profile_picture' in request.files:
                file = request.files['profile_picture']
                if file and allowed_file(file.filename):
                    filename = secure_filename(f"nurse_{current_user.id}_{datetime.now().timestamp()}.{file.filename.rsplit('.', 1)[1].lower()}")
                    file_path = os.path.join(PROFILE_PICTURES_FOLDER, filename)
                    file.save(file_path)
                    current_user.profile_picture = filename
            

            if 'documents' in request.files:
                documents = request.files.getlist('documents')
                saved_docs = []
                for doc in documents:
                    if doc and allowed_file(doc.filename):
                        filename = secure_filename(f"doc_{current_user.id}_{datetime.now().timestamp()}_{doc.filename}")
                        file_path = os.path.join(DOCUMENTS_FOLDER, filename)
                        doc.save(file_path)
                        saved_docs.append(filename)
                
                if saved_docs:
                    current_docs = json.loads(current_user.documents) if current_user.documents else []
                    current_docs.extend(saved_docs)
                    current_user.documents = json.dumps(current_docs)
            
            db.session.commit()
            flash('Профіль успішно оновлено!', 'success')
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating profile: {str(e)}")
            flash('Помилка при оновленні профілю', 'danger')
        
        return redirect(url_for('nurse.profile'))
    
    formatted_date = current_user.date_birth.strftime('%Y-%m-%d') if current_user.date_birth else ''
    user_documents = json.loads(current_user.documents) if current_user.documents else []
    
    return render_template('nurse/profile.html', 
                         formatted_date=formatted_date,
                         user_documents=user_documents,
                         user=current_user)

@nurse_bp.route('/delete_document', methods=['POST'])
@login_required
def delete_document():
    if current_user.role != 'nurse':
        return jsonify({'success': False, 'message': 'Доступ заборонено'}), 403
    
    try:
        doc_name = request.json.get('doc_name')
        if not doc_name:
            return jsonify({'success': False, 'message': 'Не вказано назву документа'})

        doc_path = os.path.join(DOCUMENTS_FOLDER, doc_name)
        if os.path.exists(doc_path):
            os.remove(doc_path)
        

        if current_user.documents:
            documents = json.loads(current_user.documents)
            if doc_name in documents:
                documents.remove(doc_name)
                current_user.documents = json.dumps(documents) if documents else None
                db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
@nurse_bp.route('/appointments')
@login_required
def appointments():
    if current_user.role != 'nurse':
        return jsonify({'error': 'Доступ заборонено'}), 403
    return render_template('nurse/appointments.html')

@nurse_bp.route('/update_location', methods=['POST'])
@login_required
def update_location():
    if current_user.role != 'nurse':
        return jsonify({'success': False, 'message': 'Доступ заборонено'}), 403
    
    try:
        data = request.get_json()
        if not data or 'latitude' not in data or 'longitude' not in data:
            return jsonify({'success': False, 'message': 'Необхідно надати координати'}), 400
        
        current_user.latitude = float(data['latitude'])
        current_user.longitude = float(data['longitude'])
        current_user.location_approved = True
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Локація оновлена',
            'latitude': current_user.latitude,
            'longitude': current_user.longitude
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@nurse_bp.route('/toggle_online', methods=['POST'])
@login_required
def toggle_online():
    if current_user.role != 'nurse':
        return jsonify({'success': False, 'message': 'Доступ заборонено'}), 403
    
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

@nurse_bp.route('/get_clients_locations')
@login_required
def get_clients_locations():
    if current_user.role != 'nurse':
        return jsonify({'error': 'Доступ заборонено'}), 403
    
    try:
        clients = User.query.filter(
            User.role == 'client',
            User.location_approved == True,
            User.latitude.isnot(None),
            User.longitude.isnot(None)
        ).all()
        
        clients_data = [{
            'id': client.id,
            'name': client.user_name,
            'lat': client.latitude,
            'lng': client.longitude
        } for client in clients]
        
        return jsonify(clients_data)
    except Exception as e:
        current_app.logger.error(f"Error getting clients locations: {str(e)}")
        return jsonify({'error': 'Помилка сервера'}), 500
    
    
@nurse_bp.route('/get_chat_messages')
@login_required
def get_chat_messages():
    if current_user.role != 'nurse':
        return jsonify({'error': 'Доступ заборонено'}), 403
    
    recipient_id = request.args.get('recipient_id')
    if not recipient_id:
        return jsonify({'error': 'Не вказано отримувача'}), 400
    
    try:
        messages = Message.query.filter(
            ((Message.sender_id == current_user.id) & (Message.recipient_id == recipient_id)) |
            ((Message.sender_id == recipient_id) & (Message.recipient_id == current_user.id))
        ).order_by(Message.timestamp.asc()).all()
        
        messages_data = [{
            'id': msg.id,
            'sender_id': msg.sender_id,
            'sender_name': msg.sender.user_name if msg.sender_id != current_user.id else 'Ви',
            'text': msg.text,
            'timestamp': msg.timestamp.isoformat()
        } for msg in messages]
        
        return jsonify(messages_data)
    except Exception as e:
        current_app.logger.error(f"Error getting chat messages: {str(e)}")
        return jsonify({'error': 'Помилка сервера'}), 500
    
@nurse_bp.route('/services', methods=['GET', 'POST'])
@login_required
def manage_services():
    if current_user.role != 'nurse':
        return redirect(url_for('auth.login'))

    standard_services = Service.query.filter_by(is_standart=True).all()
    nurse_services = NurseService.query.filter_by(nurse_id=current_user.id).all()

    if request.method == 'POST':
        try:
            action = request.form.get('action')
            
            if action == 'add_custom':
                new_service = NurseService(
                    nurse_id=current_user.id,
                    service_id=None,
                    name=request.form.get('name'),
                    price=float(request.form.get('price')),
                    duration=int(request.form.get('duration')),
                    description=request.form.get('description', ''),
                    is_available='is_available' in request.form
                )
                db.session.add(new_service)
                flash('Власну послугу додано успішно', 'success')
            
            elif action == 'add':
                service_id = request.form.get('service_id')
                if not service_id:
                    flash('Не обрано послугу', 'danger')
                    return redirect(url_for('nurse.manage_services'))
                
                new_service = NurseService(
                    nurse_id=current_user.id,
                    service_id=service_id,
                    name=None,
                    price=float(request.form.get('price')),
                    duration=int(request.form.get('duration')),
                    description=request.form.get('description', ''),
                    is_available='is_available' in request.form
                )
                db.session.add(new_service)
                flash('Стандартну послугу додано успішно', 'success')
            
            elif action == 'update':
                service_id = request.form.get('service_id')
                is_custom = request.form.get('is_custom') == 'true'
                
                if is_custom:
                    service = NurseService.query.filter_by(
                        id=service_id,
                        nurse_id=current_user.id
                    ).first()
                    if service:
                        service.name = request.form.get('name')
                else:
                    service = NurseService.query.filter_by(
                        service_id=service_id,
                        nurse_id=current_user.id
                    ).first()
                
                if service:
                    service.price = float(request.form.get('price'))
                    service.duration = int(request.form.get('duration'))
                    service.description = request.form.get('description', '')
                    service.is_available = 'is_available' in request.form
                    flash('Послугу оновлено успішно', 'success')
                else:
                    flash('Послугу не знайдено', 'danger')
            
            elif action == 'remove':
                service_id = request.form.get('service_id')
                service = NurseService.query.filter_by(
                    service_id=service_id,
                    nurse_id=current_user.id
                ).first()
                
                if service:
                    db.session.delete(service)
                    flash('Стандартну послугу видалено успішно', 'success')
                else:
                    flash('Послугу не знайдено', 'danger')
            
            elif action == 'remove_custom':
                service_id = request.form.get('service_id')
                service = NurseService.query.filter_by(
                    id=service_id,
                    nurse_id=current_user.id
                ).first()
                
                if service:
                    db.session.delete(service)
                    flash('Власну послугу видалено успішно', 'success')
                else:
                    flash('Послугу не знайдено', 'danger')
            
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error managing services: {str(e)}")
            flash(f'Помилка при обробці запиту: {str(e)}', 'danger')
        
        return redirect(url_for('nurse.manage_services'))

    return render_template('nurse/services.html',
                         standard_services=standard_services,
                         nurse_services=nurse_services)
                         
@nurse_bp.route('/get_appointments')
@login_required
def get_appointments():
    print("Отримано запит до /nurse/get_appointments")  # Логування
    if current_user.role != 'nurse':
        return jsonify({'error': 'Доступ заборонено'}), 403
    
    try:
        start_date = request.args.get('start')
        end_date = request.args.get('end')
        query = Appointment.query.filter_by(nurse_id=current_user.id)
        
        if start_date and end_date:
            try:
                start = datetime.fromisoformat(start_date)
                end = datetime.fromisoformat(end_date)
                query = query.filter(
                    Appointment.appointment_time >= start,
                    Appointment.appointment_time <= end
                )
            except ValueError as e:
                print(f"Помилка формату дати: {e}")
        
        appointments = query.all()
        result = []
        
        for app in appointments:
            service_name = app.nurse_service.name if app.nurse_service else "Послуга"
            result.append({
                'id': app.id,
                'title': f"{service_name} - {app.client.user_name}",
                'start': app.appointment_time.isoformat(),
                'end': app.end_time.isoformat(),
                'color': calendar_appointment_color(app.status),
                'extendedProps': {
                    'client_name': app.client.user_name,
                    'nurse_name': app.nurse.user_name,
                    'status': app.status,
                    'notes': app.notes,
                    'photo': app.client.photo if app.client.photo else None
                }
            })
        
        print(f"Повертаємо {len(result)} записів")  # Логування
        return jsonify(result)
    
    except Exception as e:
        print(f"Помилка у get_appointments: {str(e)}")  # Логування
        return jsonify({'error': 'Внутрішня помилка сервера'}), 500

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
    if current_user.role != 'nurse':
        return jsonify({'success': False, 'message': 'Доступ заборонено'}), 403

    try:
        data = request.get_json()
        appointment_id = data.get('appointment_id')
        status = data.get('status')

        if not appointment_id or not status:
            return jsonify({'success': False, 'message': 'Необхідно вказати запис та статус'}), 400

        appointment = Appointment.query.filter_by(
            id=appointment_id,
            nurse_id=current_user.id
        ).first()

        if not appointment:
            return jsonify({'success': False, 'message': 'Запис не знайдено'}), 404

        appointment.status = status
        db.session.commit()

        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating appointment status: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500












@socketio.on('connect')
def handle_connect():
    print(f"Клієнт підключився: {request.sid}")
    emit('connection_response', {'status': 'connected'})

@socketio.on('disconnect')
def handle_disconnect():
    print(f"Клієнт відключився: {request.sid}")

@socketio.on('join')
def handle_join(data):
    user_id = data.get('user_id')
    if user_id:
        join_room(f"user_{user_id}")
        current_app.logger.info(f'Користувач {user_id} приєднався до кімнати')

@socketio.on('send_message')
def handle_send_message(data):
    try:
        print(f"Отримано дані: {data}")  # Логування вхідних даних
        
        if not all(key in data for key in ['text', 'sender_id', 'recipient_id']):
            raise ValueError("Недостатньо даних")
            
        # Створення повідомлення
        message = Message(
            sender_id=int(data['sender_id']),
            recipient_id=int(data['recipient_id']),
            text=data['text']
        )
        
        # Збереження в БД
        db.session.add(message)
        db.session.commit()
        
        # Отримання імені відправника
        sender = User.query.get(message.sender_id)
        sender_name = sender.user_name if sender else "Невідомий"
        
        # Відправка отримувачу
        emit('new_message', {
            'id': message.id,
            'sender_id': message.sender_id,
            'sender_name': sender_name,
            'text': message.text,
            'timestamp': message.timestamp.isoformat()
        }, room=f"user_{message.recipient_id}")
        
        # Підтвердження відправнику
        emit('message_sent', {
            'id': message.id,
            'status': 'delivered'
        }, room=request.sid)
        
    except Exception as e:
        print(f"Помилка: {str(e)}")
        emit('error', {'message': str(e)}, room=request.sid)
        db.session.rollback()


@nurse_bp.route('/stats')
@login_required
def nurse_stats():
    if current_user.role != 'nurse':
        return jsonify({'error': 'Доступ заборонено'}), 403

    accepted_statuses = ['confirmed', 'confirmed_paid', 'nurse_confirmed']
    accepted_count = Appointment.query.filter(
        Appointment.nurse_id == current_user.id,
        Appointment.status.in_(accepted_statuses)
    ).count()

    completed_count = Appointment.query.filter(
        Appointment.nurse_id == current_user.id,
        Appointment.status == 'completed'
    ).count()

    avg_rating = current_user.average_nurse_rating  # з hybrid_property
    reviews_count = current_user.reviews_nurse_count

    # Додатково: скільки майбутніх активних
    upcoming_count = Appointment.query.filter(
        Appointment.nurse_id == current_user.id,
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
    """Отримати всі запити для медсестри (для карти)"""
    if current_user.role != 'nurse':
        return jsonify({'success': False, 'message': 'Доступ заборонено'}), 403
    
    try:
        nurse_lat = current_user.latitude
        nurse_lng = current_user.longitude
        
        # Базовий запит
        query = ClientSelfCreatedAppointment.query.filter(
            ClientSelfCreatedAppointment.status == 'pending'
        )
        

        if nurse_lat and nurse_lng:
            distance_formula = func.acos(
                func.sin(func.radians(nurse_lat)) * func.sin(func.radians(ClientSelfCreatedAppointment.latitude)) +
                func.cos(func.radians(nurse_lat)) * func.cos(func.radians(ClientSelfCreatedAppointment.latitude)) *
                func.cos(func.radians(ClientSelfCreatedAppointment.longitude) - func.radians(nurse_lng))
            ) * 6371  # Радіус Землі в км
            
            query = query.filter(distance_formula <= 50)  # 50 км радіус
        
        requests = query.all()
        
        result = []
        for req in requests:
            result.append({
                'id': req.id,
                'patient_name': req.patient.full_name,
                'service_name': req.service_name,
                'service_description': req.service_description,
                'appointment_start_time': req.appointment_start_time.isoformat(),
                'latitude': req.latitude,
                'longitude': req.longitude,
                'notes': req.notes,
                'payment': req.payment,
                'created_appo': req.created_appo.isoformat(),
                'patient_id': req.patient_id
            })
        
        return jsonify({'success': True, 'requests': result}), 200
        
    except Exception as e:
        current_app.logger.error(f"Помилка отримання запитів: {str(e)}")
        return jsonify({'success': False, 'error': 'Внутрішня помилка сервера'}), 500

@nurse_bp.route('/nurse_accept_request/<int:request_id>', methods=['POST'])
@login_required
def nurse_accept_request(request_id):
    if current_user.role != 'nurse':
        return jsonify({'success': False, 'message': 'Доступ заборонено'}), 403
    
    try:
        request = ClientSelfCreatedAppointment.query.get(request_id)
        
        if not request:
            return jsonify({'success': False, 'message': 'Запит не знайдено'}), 404
        
        if request.status != 'pending':
            return jsonify({'success': False, 'message': 'Запит вже оброблений'}), 400
        
        request.status = 'accepted'
        request.doctor_id = current_user.id
        
        appointment = Appointment(
            client_id=request.patient_id,
            nurse_id=current_user.id,
            nurse_service_id=request.nurse_service_id,
            appointment_time=request.appointment_start_time,
            end_time=request.end_time,
            status='scheduled',
            notes=request.notes
        )
        
        db.session.add(appointment)
        db.session.commit()
        
        # TODO: Надіслати сповіщення клієнту
        
        return jsonify({
            'success': True, 
            'message': 'Запит прийнято',
            'appointment_id': appointment.id
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Помилка прийняття запиту: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': 'Внутрішня помилка сервера'}), 500

@nurse_bp.route('/nurse_get_accepted_requests', methods=['GET'])
@login_required
def nurse_get_accepted_requests():
    if current_user.role != 'nurse':
        return jsonify({'success': False, 'message': 'Доступ заборонено'}), 403
    
    try:
        requests = ClientSelfCreatedAppointment.query.filter_by(
            doctor_id=current_user.id
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
                'latitude': req.latitude,
                'longitude': req.longitude,
                'notes': req.notes,
                'payment': req.payment
            })
        
        return jsonify({'success': True, 'requests': result}), 200
        
    except Exception as e:
        current_app.logger.error(f"Помилка отримання прийнятих запитів: {str(e)}")
        return jsonify({'success': False, 'error': 'Внутрішня помилка сервера'}), 500




def notify_nurses_about_new_appointment(appointment):
    """Сповістити медсестер про новий запит"""
    # Знаходимо всіх медсестер поблизу
    nurses = User.query.filter_by(role='nurse').all()
    
    for nurse in nurses:
        if nurse.latitude and nurse.longitude:
            # Розрахунок відстані
            distance = calculate_distance(
                nurse.latitude, nurse.longitude,
                appointment.latitude, appointment.longitude
            )
            
            if distance <= 50:  # 50 км радіус
                # TODO: Реалізувати сповіщення (email, push, etc.)
                pass

def calculate_distance(lat1, lng1, lat2, lng2):

    
    R = 6371  # Радіус Землі в км
    
    lat1_rad = radians(lat1)
    lng1_rad = radians(lng1)
    lat2_rad = radians(lat2)
    lng2_rad = radians(lng2)
    
    dlng = lng2_rad - lng1_rad
    dlat = lat2_rad - lat1_rad
    
    a = sin(dlat/2)**2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlng/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    
    return R * c
