from flask import Blueprint, jsonify, request, current_app, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models import User, Message, db, Service, NurseService, Appointment
from datetime import datetime
import json
import os
from werkzeug.utils import secure_filename

nurse_bp = Blueprint('nurse', __name__)


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
    if current_user.role != 'nurse':
        return jsonify({'error': 'Доступ заборонено'}), 403
    appoint_information = Appointment.query.filter_by(client_id=current_user.id).all()
    appoint_list=[]
    for app in appoint_information:
        appoint_list.append({
            'id':app.id,
            'name':app.nurse_service.name,
            'start':app.appointment_time,
            'end':app.end_time,
            'color':calendar_appointment_color(app.status),
            'photo':app.client.photo,
            'extended':{
                'client_name':app.client.user_name,
                'nurse_name':app.nurse.user_name,
                'status':app.stauts,
                'notes':app.notes
            

            }

        })   
    return jsonify(appoint_list)

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
