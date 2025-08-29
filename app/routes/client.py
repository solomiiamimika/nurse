from flask import render_template, redirect, url_for, flash, request,abort,jsonify,current_app
from flask_login import login_user, logout_user, current_user, login_required
from sqlalchemy.sql.sqltypes import DateTime
from app.extensions import db, bcrypt
from app.models import Appointment, NurseService, User,Message,Payment, ClientSelfCreatedAppointment, Review
from . import client_bp
from app.supabase_storage import get_file_url,delete_from_supabase,upload_to_supabase,buckets
from datetime import datetime, timedelta
import os 
from werkzeug.utils import secure_filename
import json
from dotenv import load_dotenv
import stripe

from app.extensions import socketio, db
from flask import current_app, request
from flask_socketio import join_room, leave_room, emit
from app.models import Message, db,User
from datetime import datetime

from flask_cors import cross_origin
load_dotenv()
stripe.api_key=os.getenv('STRIPE_SECRET_KEY')

stripe_public_key = os.getenv('STRIPE_PUBLIC_KEY')


BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'app', 'static', 'uploads')
DOCUMENTS_FOLDER = os.path.join(UPLOAD_FOLDER, 'documents')
PROFILE_PICTURES_FOLDER = os.path.join(UPLOAD_FOLDER, 'profile_pictures')


os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DOCUMENTS_FOLDER, exist_ok=True)
os.makedirs(PROFILE_PICTURES_FOLDER, exist_ok=True)


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif', 'pdf'}

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

        # Видалення з Supabase Storage
        delete_from_supabase(doc_name, buckets['documents'])
        
        # Оновлення БД
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




    
@client_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if current_user.role != 'client':
        return redirect(url_for('auth.login'))
    
    formatted_date = current_user.date_birth.strftime('%Y-%m-%d') if current_user.date_birth else ''
    
    if request.method == 'POST':
        try:
            current_user.full_name = request.form.get('full_name')
            current_user.phone_number = request.form.get('phone_number')
            current_user.about_me = request.form.get('about_me')
            current_user.address = request.form.get('address')
            
            date_birth = request.form.get('date_birth')
            if date_birth:
                current_user.date_birth = datetime.strptime(date_birth, '%Y-%m-%d')
            
            # Обробка фото профілю
            if 'profile_picture' in request.files:
                file = request.files['profile_picture']
                if file and file.filename != '' and allowed_file(file.filename):
                    # Видалення старого фото
                    if current_user.photo:
                        delete_from_supabase(current_user.profile_picture, buckets['profile_pictures'])
                    
                    # Завантаження нового фото
                    filename, file_url = upload_to_supabase(
                        file, 
                        buckets['profile_pictures'], 
                        current_user.id,
                        'profile'
                    )
                    if filename:
                        current_user.photo = filename
            
            # Обробка документів
            if 'documents' in request.files:
                documents = request.files.getlist('documents')
                saved_docs = []
                for doc in documents:
                    if doc and doc.filename != '' and allowed_file(doc.filename):
                        filename, file_url = upload_to_supabase(
                            doc, 
                            buckets['documents'], 
                            current_user.id,
                            'document'
                        )
                        if filename:
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
    profile_photo = None
    if current_user.photo:
        profile_photo = get_file_url(current_user.photo,buckets['profile_pictures'])
    documents_urls = {}
    if current_user.documents:
        documents = json.loads(current_user.documents)
        for i in documents:
            documents_urls[i] = get_file_url(i,buckets['documents'])
    return render_template('client/profile.html',profile_photo = profile_photo,documents_urls=documents_urls,user = current_user)


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
    return render_template('client/appointments.html', stripe_public_key = stripe_public_key)


@client_bp.route('/get_appointments')
@login_required
def get_appointments():
    if current_user.role != 'client':
        return jsonify({'error': 'Доступ заборонено'}), 403
    
    try:
        start_date = request.args.get('start')
        end_date = request.args.get('end')
        
        query = Appointment.query.filter_by(client_id=current_user.id)
        
        if start_date and end_date:
            try:
                start = datetime.fromisoformat(start_date)
                end = datetime.fromisoformat(end_date)
                query = query.filter(
                    Appointment.appointment_time >= start,
                    Appointment.appointment_time <= end
                )
            except ValueError as e:
                current_app.logger.error(f"Помилка формату дати: {e}")
        
        appointments = query.order_by(Appointment.appointment_time.asc()).all()
        
        result = []
        for app in appointments:
            service_name = app.nurse_service.name if app.nurse_service else "Послуга"
            nurse_name = app.nurse.user_name if app.nurse else "Медсестра"
            
            result.append({
                'id': app.id,
                'title': f"{service_name} - {nurse_name}",
                'start': app.appointment_time.isoformat(),
                'end': app.end_time.isoformat(),
                'color': get_appointment_color(app.status),
                'extendedProps': {
                    'status': app.status,
                    'notes': app.notes or '',
                    'nurse_name': nurse_name,
                    'service_name': service_name
                }
            })
        
        return jsonify(result)
    
    except Exception as e:
        current_app.logger.error(f"Помилка у get_appointments: {str(e)}")
        return jsonify({'error': 'Внутрішня помилка сервера'}), 500
def get_appointment_color(status):
    colors = {
        'scheduled': 'gray',
        'confirmed': 'blue',
        'completed': 'green',
        'cancelled': 'red'
    }
    return colors.get(status, 'gray')
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
        




@client_bp.route('/get_nurse_services')
@login_required
def get_nurse_services():
    if current_user.role != 'client':
        return jsonify({'error': 'Доступ заборонено'}), 403
    
    nurse_id = request.args.get('nurse_id')
    if not nurse_id:
        return jsonify({'error': 'Не вказано медсестру'}), 400
    
    try:
        services = NurseService.query.filter_by(
            nurse_id=nurse_id,
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
        return jsonify({'error': 'Помилка сервера'}), 500



@client_bp.route('/create_appointment', methods=['POST'])
@login_required
def create_appointment():
    if current_user.role != 'client':
        return jsonify({'success': False, 'message': 'Доступ заборонено'}), 403
    
    try:
        data = request.get_json()
        nurse_id = data.get('nurse_id')
        service_id = data.get('service_id')
        date_time = data.get('date_time')
        notes = data.get('notes')
        
        if not all([nurse_id, service_id, date_time]):
            return jsonify({'success': False, 'message': 'Необхідно заповнити всі поля'}), 400
        
    
        nurse = User.query.get(nurse_id)
        if not nurse or nurse.role != 'nurse':
            return jsonify({'success': False, 'message': 'Медсестру не знайдено'}), 404
        
        service = NurseService.query.get(service_id)
        if not service or service.nurse_id != int(nurse_id):
            return jsonify({'success': False, 'message': 'Послугу не знайдено'}), 404
        

        appointment_time = datetime.strptime(date_time, '%Y-%m-%dT%H:%M')
        end_time = appointment_time + timedelta(minutes=service.duration)
        
        conflicting_appointments = Appointment.query.filter(
            Appointment.nurse_id == nurse_id,
            Appointment.status == 'scheduled',
            ((Appointment.appointment_time <= appointment_time) & (Appointment.end_time > appointment_time)) |
            ((Appointment.appointment_time < end_time) & (Appointment.end_time >= end_time)) |
            ((Appointment.appointment_time >= appointment_time) & (Appointment.end_time <= end_time))
        ).count()
        
        if conflicting_appointments > 0:
            return jsonify({'success': False, 'message': 'Цей час вже зайнятий'}), 400
        

        new_appointment = Appointment(
            client_id=current_user.id,
            nurse_id=nurse_id,
            nurse_service_id=service_id,
            appointment_time=appointment_time,
            end_time=end_time,
            notes=notes,
            status='scheduled',

        )
        
        db.session.add(new_appointment)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Запис успішно створено',
            'appointment_id': new_appointment.id
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating appointment: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

            
    

    
@client_bp.route('/create_apple_pay_session', methods=['POST'])
@login_required
def create_apple_pay_session():
    try:
        appointment_id = request.json.get('appointment_id')
        appointment = Appointment.query.get_or_404(appointment_id)
        
        if appointment.client_id != current_user.id:
            abort(403)

        # Створюємо сесію оплати Stripe
        session = stripe.checkout.Session.create(
            payment_method_types=['card', 'apple_pay'],
            line_items=[{
                'price_data': {
                    'currency': 'uah',
                    'product_data': {
                        'name': appointment.nurse_service.name,
                    },
                    'unit_amount': int(appointment.nurse_service.price * 100),  # В копійках
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=url_for('client.payment_success', appointment_id=appointment_id, _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=url_for('client.payment_cancel', _external=True),
            customer_email=current_user.email,
            metadata={
                'appointment_id': appointment_id,
                'user_id': current_user.id
            }
        )

        return jsonify({'sessionId': session.id})
    
    except Exception as e:
        current_app.logger.error(f"Apple Pay error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@client_bp.route('/payment_success/<int:appointment_id>')
@login_required
def payment_success(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)
    session_id = request.args.get('session_id')
    
    try:
        if session_id:
            # Verify the payment with Stripe
            session = stripe.checkout.Session.retrieve(session_id)
            
            if session.payment_status == 'paid' and session.metadata.get('appointment_id') == str(appointment_id):
                payment = Payment(
                    user_id=current_user.id,
                    appointment_id=appointment_id,
                    amount=float(session.amount_total) / 100,
                    payment_date=datetime.utcnow(),
                    status='completed',
                    transaction_id=session.payment_intent,
                    payment_method=session.payment_method_types[0] if session.payment_method_types else 'card'
                )
                
                db.session.add(payment)
                appointment.status = 'confirmed_paid'
                db.session.commit()
                
                flash('Оплата успішна!', 'success')
            else:
                flash('Оплата не підтверджена', 'warning')
        else:
            flash('Інформація про оплату відсутня', 'warning')
    
    except stripe.error.StripeError as e:
        current_app.logger.error(f"Stripe verification error: {str(e)}")
        flash('Помилка при перевірці платежу', 'danger')
    except Exception as e:
        current_app.logger.error(f"Error in payment_success: {str(e)}")
        flash('Помилка сервера', 'danger')
    
    return redirect(url_for('client.appointments'))

@client_bp.route('/stripe_webhook', methods=['POST'])
@cross_origin()
def stripe_webhook():
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get('Stripe-Signature')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, current_app.config['STRIPE_WEBHOOK_SECRET']
        )
    except ValueError as e:
        return jsonify({'error': 'Invalid payload'}), 400
    except stripe.error.SignatureVerificationError as e:
        return jsonify({'error': 'Invalid signature'}), 400

    # Обробка події успішної оплати
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        handle_successful_payment(session)

    return jsonify({'status': 'success'})

def handle_successful_payment(session):
    try:
        appointment_id = session['metadata'].get('appointment_id')
        user_id = session['metadata'].get('user_id')
        
        if appointment_id and user_id:
            payment = Payment(
                user_id=user_id,
                appointment_id=appointment_id,
                amount=float(session['amount_total']) / 100,
                payment_date=datetime.now(),
                status='completed',
                transaction_id=session['payment_intent'],
                payment_method=session['payment_method_types'][0]
            )
            
            db.session.add(payment)
            
            appointment = Appointment.query.get(appointment_id)
            if appointment:
                appointment.status = 'confirmed_paid'
            
            db.session.commit()
    except Exception as e:
        current_app.logger.error(f"Webhook error: {str(e)}")





@client_bp.route('/create_payment_session', methods=['POST'])
@login_required
def create_payment_session():
    try:
        data = request.get_json()
        appointment_id = data.get('appointment_id')
        
        if not appointment_id:
            return jsonify({'error': 'Appointment ID is required'}), 400
            
        appointment = Appointment.query.get_or_404(appointment_id)
        
        if appointment.client_id != current_user.id:
            return jsonify({'error': 'Unauthorized'}), 403
            
        if appointment.status == 'confirmed_paid':
            return jsonify({'error': 'Appointment already paid'}), 400

        # Create Stripe Checkout session
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'uah',
                    'product_data': {
                        'name': appointment.nurse_service.name,
                    },
                    'unit_amount': int(appointment.nurse_service.price * 100),  # Convert to cents
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=url_for('client.payment_success', appointment_id=appointment_id, _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=url_for('client.payment_cancel', _external=True),
            customer_email=current_user.email,
            metadata={
                'appointment_id': appointment_id,
                'user_id': current_user.id
            }
        )

        return jsonify({'sessionId': session.id})
        
    except stripe.error.StripeError as e:
        current_app.logger.error(f"Stripe error in create_payment_session: {str(e)}")
        return jsonify({'error': 'Payment service error'}), 500
    except Exception as e:
        current_app.logger.error(f"Error in create_payment_session: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500



@client_bp.route('/payment_cancel')
@login_required
def payment_cancel():
    try:
        session_id = request.args.get('session_id')
        
        if session_id:
            # Отримуємо сесію Stripe для логування
            session = stripe.checkout.Session.retrieve(session_id)
            
            # Логуємо скасування
            current_app.logger.info(f"Payment canceled - Session ID: {session_id}, Status: {session.payment_status}")
            
            # Якщо є appointment_id в metadata, можемо оновити статус
            if 'appointment_id' in session.metadata:
                appointment = Appointment.query.get(session.metadata['appointment_id'])
                if appointment and appointment.client_id == current_user.id:
                    appointment.status = 'payment_canceled'
                    db.session.commit()
        
        # Створюємо запис про скасування платежу
        payment_record = Payment(
            user_id=current_user.id,
            status='canceled',
            payment_date=datetime.utcnow(),
            payment_method='stripe',
            amount=0,
            transaction_id=session_id or 'manual_cancel'
        )
        db.session.add(payment_record)
        db.session.commit()
        
    except stripe.error.StripeError as e:
        current_app.logger.error(f"Stripe error in payment_cancel: {str(e)}")
    except Exception as e:
        current_app.logger.error(f"Error in payment_cancel: {str(e)}")
        db.session.rollback()
    
    flash('Оплату скасовано. Ви можете спробувати ще раз.', 'warning')
    return redirect(url_for('client.appointments'))



@client_bp.route('/cancel_appointment', methods=['POST'])
@login_required
def cancel_appointment():
    if current_user.role != 'client':
        return jsonify({'success': False, 'message': 'Доступ заборонено'}), 403
    
    try:
        data = request.get_json()
        appointment_id = data.get('appointment_id')
        reason = data.get('reason', '')
        
        if not appointment_id:
            return jsonify({'success': False, 'message': 'Не вказано ID запису'}), 400
        
        appointment = Appointment.query.filter_by(
            id=appointment_id,
            client_id=current_user.id
        ).first()
        
        if not appointment:
            return jsonify({'success': False, 'message': 'Запис не знайдено'}), 404
        
        # Check if it's too late to cancel (e.g., less than 24 hours before)
        if appointment.appointment_time - datetime.utcnow() < timedelta(hours=24):
            return jsonify({
                'success': False,
                'message': 'Скасування менш ніж за 24 години до запису неможливе'
            }), 400
        
        appointment.status = 'cancelled'
        appointment.cancellation_reason = reason
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Запис скасовано'})
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error cancelling appointment: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500
    
@client_bp.route('/client_self_create_appointment', methods=['POST'])
@login_required
def client_self_create_appointment():
    if current_user.role != 'client':
        return jsonify({'success': False, 'message': 'Доступ заборонено'}), 403
    
    try:
        data = request.get_json()
        
        required_fields = ['latitude', 'longitude', 'appointment_start_time']
        
        if not all(field in data for field in required_fields):
            return jsonify({'success': False, 'error': 'Не всі обов\'язкові поля заповнені'}), 400
        
        appointment_start_time = datetime.fromisoformat(data['appointment_start_time'].replace('Z', '+00:00'))
        
        end_time = data.get('end_time')
        if end_time:
            end_time = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        else:
            end_time = appointment_start_time + timedelta(hours=1)
        
        appointment = ClientSelfCreatedAppointment(
            patient_id=current_user.id,
            appointment_start_time=appointment_start_time,
            end_time=end_time,
            latitude=data['latitude'],
            longitude=data['longitude'],
            status='pending',
            notes=data.get('notes', ''),
            service_name=data.get('service_name', ''),
            service_description=data.get('service_description', ''),
            payment=data.get('payment', 0),
            created_at=datetime.now()
        )
        
        db.session.add(appointment)
        db.session.commit()
        
        # Сповіщення медсестер про новий запит
        #notify_nurses_about_new_appointment(appointment)
        
        return jsonify({
            'success': True,
            'message': 'Запит успішно створено',
            'appointment_id': appointment.id
        }), 201
        
    except Exception as e:
        current_app.logger.error(f"Помилка створення запиту: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': 'Внутрішня помилка сервера'}), 500
        







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






@client_bp.route('/client_get_requests', methods=['GET'])
@login_required
def client_get_requests():
    if current_user.role != 'client':
        return jsonify({'success': False, 'message': 'Доступ заборонено'}), 403
    
    try:
        requests = ClientSelfCreatedAppointment.query.filter_by(
            patient_id=current_user.id
        ).order_by(ClientSelfCreatedAppointment.created_appo.desc()).all()
        
        result = []
        for req in requests:
            result.append({
                'id': req.id,
                'service_name': req.service_name,
                'status': req.status,
                'appointment_start_time': req.appointment_start_time.isoformat(),
                'created_appo': req.created_appo.isoformat(),
                'latitude': req.latitude,
                'longitude': req.longitude,
                'notes': req.notes,
                'payment': req.payment,
                'doctor_id': req.doctor_id,
                'nurse_name': req.doctor.full_name if req.doctor else None
            })
        
        return jsonify({'success': True, 'requests': result}), 200
        
    except Exception as e:
        current_app.logger.error(f"Помилка отримання запитів: {str(e)}")
        return jsonify({'success': False, 'error': 'Внутрішня помилка сервера'}), 500

@client_bp.route('/client_cancel_request/<int:request_id>', methods=['POST'])
@login_required
def client_cancel_request(request_id):
    if current_user.role != 'client':
        return jsonify({'success': False, 'message': 'Доступ заборонено'}), 403
    
    try:
        request = ClientSelfCreatedAppointment.query.filter_by(
            id=request_id, 
            patient_id=current_user.id
        ).first()
        
        if not request:
            return jsonify({'success': False, 'message': 'Запит не знайдено'}), 404
        
        if request.status not in ['pending', 'accepted']:
            return jsonify({'success': False, 'message': 'Неможливо скасувати цей запит'}), 400
        
        request.status = 'cancelled'
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Запит скасовано'}), 200
        
    except Exception as e:
        current_app.logger.error(f"Помилка скасування запиту: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': 'Внутрішня помилка сервера'}), 500







@client_bp.route('/leave_review', methods=['POST'])
@login_required
def leave_review():
    if current_user.role != 'client':
        return jsonify({'success': False, 'message': 'Доступ заборонено'}), 403

    data = request.get_json() or {}
    appointment_id = data.get('appointment_id')
    rating = data.get('rating')
    comment = data.get('comment', '').strip()

    if not appointment_id or rating is None:
        return jsonify({'success': False, 'message': 'Необхідно вказати appointment_id і rating'}), 400

    try:
        rating = int(rating)
        if rating < 1 or rating > 5:
            raise ValueError
    except Exception:
        return jsonify({'success': False, 'message': 'Рейтинг має бути цілим від 1 до 5'}), 400

    appo = Appointment.query.filter_by(id=appointment_id, client_id=current_user.id).first()
    if not appo:
        return jsonify({'success': False, 'message': 'Запис не знайдено'}), 404

    if appo.status != 'confirmed_paid':
        return jsonify({'success': False, 'message': 'Відгук можна залишити лише після завершення візиту'}), 400

    # Перевірка: щоб на один appointment не було дубля відгуку
    existing = Review.query.filter_by(patient_id=current_user.id, doctor_id=appo.nurse_id, appointment_id=appo.id).first()
    if existing:
        return jsonify({'success': False, 'message': 'Відгук вже залишено'}), 400

    review = Review(
        patient_id=current_user.id,
        doctor_id=appo.nurse_id,     # nurse
        appointment_id=appo.id,
        rating=rating,
        comment=comment
    )
    db.session.add(review)
    db.session.commit()

    return jsonify({'success': True, 'message': 'Дякуємо за відгук!'})









@client_bp.route('/get_reviews/<int:nurse_id>')
@login_required
def get_nurse_reviews(nurse_id):
    reviews = Review.query.filter_by(doctor_id=nurse_id).order_by(
        Review.created_at.desc()
    ).all()
    
    return jsonify({
        'reviews': [{
            'id': r.id,
            'patient_name': r.patient.full_name,
            'rating': r.rating,
            'comment': r.comment,
            'created_at': r.created_at.isoformat(),
            'appointment_date': r.appointment.appointment_time.isoformat() if r.appointment else None
        } for r in reviews]
    })
@client_bp.route('/get_review/<int:appointment_id>')
@login_required
def get_review(appointment_id):
    review = Review.query.filter_by(
        appointment_id=appointment_id,
        patient_id=current_user.id
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
    else:
        return jsonify({'success': False, 'message': 'Відгук не знайдено'}), 404

@client_bp.route('/can_review/<int:appointment_id>')
@login_required
def can_review_appointment(appointment_id):
    appointment = Appointment.query.filter_by(
        id=appointment_id, 
        client_id=current_user.id
    ).first()
    
    if not appointment:
        return jsonify({'can_review': False, 'reason': 'Запис не знайдено'})
    
    if appointment.status != 'completed':
        return jsonify({'can_review': False, 'reason': 'Запис ще не завершено'})
    
    existing_review = Review.query.filter_by(
        appointment_id=appointment_id,
        patient_id=current_user.id
    ).first()
    
    if existing_review:
        return jsonify({'can_review': False, 'review_exists': True})
    
    return jsonify({'can_review': True, 'review_exists': False})
@client_bp.route("/services")
@login_required
def services():
    return render_template("client/services.html")


# @client_bp.route('/generate_qr_data')
# @login_required
# def generate_qr_data():
#     user=current_user
#     list_of_documents=[]
#     if user.documents: 
#         documents=user.documents.split(',')

#     QR_data={
#         'id':user.id,
#         'full_name':user.full_name or '',
#         'documents':list_of_documents or '',
#         'date_birth':user.date_birth.strftime('%Y-%m-%d') or '',
#         'about_me':user.about_me or '',
#         'photo':user.photo or '',
#         'date':datetime.utcnow().isoformat()

#     }    

#     return jsonify(QR_data)




@client_bp.route('/generate_qr_data')
@login_required
def generate_qr_data():
    user=current_user
    url = url_for("main.patient_info",user_id=user.id,_external = True)

    return jsonify({'profile_url':url})

    