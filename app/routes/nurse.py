from flask import Blueprint, jsonify, request, current_app, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models import User, Message, db, Service, NurseService, Appointment, ClientSelfCreatedAppointment
from datetime import datetime
import json
from app.supabase_storage import get_file_url,delete_from_supabase,upload_to_supabase,buckets,supabase
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
    
    formatted_date = current_user.date_birth.strftime('%Y-%m-%d') if current_user.date_birth else ''
    
    if request.method == 'POST':
        try:
            current_user.full_name = request.form.get('full_name')
            current_user.phone_number = request.form.get('phone_number')
            current_user.about_me = request.form.get('about_me')
            current_user.address = request.form.get('address')
            
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

    return render_template('nurse/profile.html', 
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
    return render_template('nurse/appointments.html')

@nurse_bp.route('/update_location', methods=['POST'])
@login_required
def update_location():
    if current_user.role != 'nurse':
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    try:
        data = request.get_json()
        if not data or 'latitude' not in data or 'longitude' not in data:
            return jsonify({'success': False, 'message': 'Coordinates are required'}), 400
        
        current_user.latitude = float(data['latitude'])
        current_user.longitude = float(data['longitude'])
        current_user.location_approved = True
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Location updated',
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

@nurse_bp.route('/get_clients_locations')
@login_required
def get_clients_locations():
    if current_user.role != 'nurse':
        return jsonify({'error': 'Access denied'}), 403
    
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
        return jsonify({'error': 'Server error'}), 500
    
    
    
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
                flash('Custom service added successfully', 'success')
            
            elif action == 'add':
                service_id = request.form.get('service_id')
                if not service_id:
                    flash('No service selected', 'danger')
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
                flash('Standard service added successfully', 'success')
            
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
                    flash('Service updated successfully', 'success')
                else:
                    flash('Service not found', 'danger')
            
            elif action == 'remove':
                service_id = request.form.get('service_id')
                service = NurseService.query.filter_by(
                    service_id=service_id,
                    nurse_id=current_user.id
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
                    nurse_id=current_user.id
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

    return render_template('nurse/services.html',
                         standard_services=standard_services,
                         nurse_services=nurse_services)
                         
@nurse_bp.route('/get_appointments')
@login_required
def get_appointments():
    print("Received request to /nurse/get_appointments")  # Logging
    if current_user.role != 'nurse':
        return jsonify({'error': 'Access denied'}), 403
    
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
                    'nurse_name': app.nurse.user_name,
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
    if appointment.nurse_id != current_user.id:
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


@nurse_bp.route('/stats')
@login_required
def nurse_stats():
    if current_user.role != 'nurse':
        return jsonify({'error': 'Access denied'}), 403

    accepted_statuses = ['confirmed', 'confirmed_paid', 'nurse_confirmed']
    accepted_count = Appointment.query.filter(
        Appointment.nurse_id == current_user.id,
        Appointment.status.in_(accepted_statuses)
    ).count()

    completed_count = Appointment.query.filter(
        Appointment.nurse_id == current_user.id,
        Appointment.status == 'completed'
    ).count()

    avg_rating = current_user.average_nurse_rating  # with hybrid_property
    reviews_count = current_user.reviews_nurse_count

    # Additionally: how many upcoming active requests
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
    if current_user.role != 'nurse':
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    try:
        nurse_lat = current_user.latitude
        nurse_lng = current_user.longitude
        
        query = ClientSelfCreatedAppointment.query.filter_by(status='pending')

        requests = query.all()
        
        result = []
        for req in requests:
            result.append({
                'id': req.id,
                'patient_name': req.patient.full_name if req.patient else "Client",
                'service_name': req.service_name,
                'appointment_start_time': req.appointment_start_time.isoformat(),
                'latitude': req.latitude,
                'longitude': req.longitude,
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
        req = ClientSelfCreatedAppointment.query.get(request_id) # змінив назву змінної request на req, щоб не плутати з flask.request
        
        if not req:
            return jsonify({'success': False, 'message': 'Request not found'}), 404
        
        if req.status != 'pending':
            return jsonify({'success': False, 'message': 'Request already processed'}), 400
        
        req.status = 'accepted'
        req.doctor_id = current_user.id
        
    
        service_id_to_use = req.nurse_service_id

        if not service_id_to_use:

            duration_minutes = 60 
            if req.end_time and req.appointment_start_time:
                diff = req.end_time - req.appointment_start_time
                duration_minutes = int(diff.total_seconds() / 60)

        
            new_custom_service = NurseService(
                name=req.service_name if req.service_name else "Individual Request",
                nurse_id=current_user.id,
                price=req.payment if req.payment else 0.0,
                duration=duration_minutes,
                description=f"Auto-generated from client request #{req.id}. {req.service_description or ''}",
                is_available=False 
            )
            
            db.session.add(new_custom_service)
            db.session.flush()
            
            service_id_to_use = new_custom_service.id
            
         
            req.nurse_service_id = service_id_to_use

        appointment = Appointment(
            client_id=req.patient_id,
            nurse_id=current_user.id,
            nurse_service_id=service_id_to_use, 
            appointment_time=req.appointment_start_time,
            end_time=req.end_time,
            status='scheduled',
            notes=req.notes
        )
        
        db.session.add(appointment)
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': 'Request accepted',
            'appointment_id': appointment.id
        }), 200
        
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


