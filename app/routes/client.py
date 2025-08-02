from flask import render_template, redirect, url_for, flash, request,abort,jsonify,current_app
from flask_login import login_user, logout_user, current_user, login_required
from sqlalchemy.sql.sqltypes import DateTime
from app. extensions import db, bcrypt
from app.models import Appointment, NurseService, User,Message
from . import client_bp
from datetime import datetime, timedelta
import os 
from werkzeug.utils import secure_filename
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'app', 'static', 'uploads')
DOCUMENTS_FOLDER = os.path.join(UPLOAD_FOLDER, 'documents')
PROFILE_PICTURES_FOLDER = os.path.join(UPLOAD_FOLDER, 'profile_pictures')


os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DOCUMENTS_FOLDER, exist_ok=True)
os.makedirs(PROFILE_PICTURES_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@client_bp.route('/dashboard')
@login_required
def dashboard():
    if current_user.role!='client':
        return redirect(url_for('auth.login'))
    return render_template('client/dashboard.html')



@client_bp.route('/delete_document', methods=['POST'])
@login_required
def delete_document():
    if current_user.role != 'client':
        return jsonify({'success': False, 'message': 'Доступ заборонено'}), 403
    
    try:
        data = request.get_json()
        doc_name = data.get('doc_name')
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

#################################################33

@client_bp.route('/update_location', methods=['POST'])
@login_required
def update_location():
    if current_user.role != 'client':
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
@client_bp.route('/get_nurses_locations')
@login_required
def get_nurses_locations():
    if current_user.role != 'client':
        return jsonify({'error': 'Доступ заборонено'}), 403
    
    nurses = User.query.filter(
        User.role == 'nurse',
        User.location_approved == True,
        User.latitude.isnot(None),
        User.longitude.isnot(None)
    ).all()
    
    nurses_data = [{
        'id': nurse.id,
        'name': nurse.user_name,
        'lat': nurse.latitude,
        'lng': nurse.longitude,
        'online': nurse.online
    } for nurse in nurses]
    
    return jsonify(nurses_data)



@client_bp.route('/send_message', methods=['POST'])
@login_required
def send_message():
    if current_user.role != 'client':
        return jsonify({'success': False, 'message': 'Доступ заборонено'}), 403
    
    try:
        data = request.get_json()
        recipient_id = data.get('recipient_id')
        text = data.get('text')
        
        if not recipient_id or not text:
            return jsonify({'success': False, 'message': 'Необхідно вказати отримувача та текст'}), 400
        
        # Перевірка, що отримувач - медсестра
        recipient = User.query.filter_by(id=recipient_id, role='nurse').first()
        if not recipient:
            return jsonify({'success': False, 'message': 'Медсестру не знайдено'}), 404
        
        message = Message(
            sender_id=current_user.id,
            recipient_id=recipient_id,
            text=text,
            timestamp=datetime.utcnow()
        )
        db.session.add(message)
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    
    
@client_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if current_user.role != 'client':
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        try:
            # Update basic info
            current_user.full_name = request.form.get('full_name')
            current_user.phone_number = request.form.get('phone_number')
            
            # Handle profile picture
            if 'profile_picture' in request.files:
                file = request.files['profile_picture']
                if file and allowed_file(file.filename):
                    filename = secure_filename(f"client_{current_user.id}_{datetime.now().timestamp()}.{file.filename.rsplit('.', 1)[1].lower()}")
                    file_path = os.path.join(PROFILE_PICTURES_FOLDER, filename)
                    file.save(file_path)
                    current_user.profile_picture = filename
            
            # Handle documents
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
        
        return redirect(url_for('client.profile'))
    
    user_documents = json.loads(current_user.documents) if current_user.documents else []
    return render_template('client/profile.html', 
                         user=current_user,
                         user_documents=user_documents)


@client_bp.route('/get_chat_messages')
@login_required
def get_chat_messages():
    if current_user.role != 'client':
        return jsonify({'error': 'Доступ заборонено'}), 403
    
    recipient_id = request.args.get('recipient_id')
    if not recipient_id:
        return jsonify({'error': 'Не вказано отримувача'}), 400
    
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


@client_bp.route('/appointments')
@login_required
def appointments():
    if current_user.role != 'client':
        return jsonify({'error': 'Доступ заборонено'}), 403
    return render_template('client/appointments.html')


@client_bp.route('/get_appointments')
@login_required
def get_appointments():
    if current_user.role != 'client':
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
            'photo':app.nurse.photo,
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

@client_bp.route('/working_hours')
@login_required
def working_hours():
    if current_user.role != 'client':
        return jsonify({'error': 'Доступ заборонено'}), 403

    nurse_id = request.args.get('nurse_id')
    service_id = request.args.get('service_id')
    date_work = request.args.get('date')
    if not service_id or service_id or nurse_id:
        return jsonify({'error': 'data is not here'}), 400

    service=NurseService.query.get(service_id)
    date=datetime.strptime(date_work, '%Y-%m-%d').date()
    start_working_hours_nurse=9
    end_working_hours_nurse=17

    appointments_active=Appointment.query.filter(Appointment.nurse_id==nurse_id, db.func.date(Appointment.appointment_time)==date).all()


@client_bp.route('/get_available_times')
@login_required
def get_available_times():
    if current_user.role != 'client':
        return jsonify({'error': 'Доступ заборонено'}), 403

    nurse_id = request.args.get('nurse_id')
    service_id = request.args.get('service_id')
    date_str = request.args.get('date')

    if not all([nurse_id, service_id, date_str]):
        return jsonify({'error': 'Необхідно вказати медсестру, послугу та дату'}), 400

    try:
        date = datetime.strptime(date_str, '%Y-%m-%d').date()
        service = NurseService.query.get(service_id)

        if not service or service.nurse_id != int(nurse_id):
            return jsonify({'error': 'Послугу не знайдено'}), 404

        # Робочий час медсестри (приклад: з 9 до 18)
        work_start = 9
        work_end = 18

        # Отримуємо всі заплановані записи на цей день
        appointments = Appointment.query.filter(
            Appointment.nurse_id == nurse_id,
            db.func.date(Appointment.appointment_time) == date,
            Appointment.status.in_(['scheduled', 'confirmed'])
        ).all()
    # Генеруємо доступні слоти
        available_slots = []
        current_time = datetime.combine(date, datetime.min.time()) + timedelta(hours=work_start)
        end_time = datetime.combine(date, datetime.min.time()) + timedelta(hours=work_end)

        while current_time + timedelta(minutes=service.duration) <= end_time:
            slot_end = current_time + timedelta(minutes=service.duration)

            # Перевіряємо чи цей слот не перетинається з існуючими записами
            is_available = True
            for app in appointments:
                if (current_time < app.end_time) and (slot_end > app.appointment_time):
                    is_available = False
                    break

            if is_available:
                available_slots.append(current_time.strftime('%H:%M'))

            current_time += timedelta(minutes=30)  # Крок 30 хвилин

        return jsonify(available_slots)

    except Exception as e:
        current_app.logger.error(f"Error getting available times: {str(e)}")
        return jsonify({'error': 'Помилка сервера'}), 500
        






            
    

    

