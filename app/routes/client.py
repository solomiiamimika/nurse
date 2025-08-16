from flask import render_template, redirect, url_for, flash, request,abort,jsonify,current_app
from flask_login import login_user, logout_user, current_user, login_required
from sqlalchemy.sql.sqltypes import DateTime
from app. extensions import db, bcrypt
from app.models import Appointment, NurseService, User,Message,Payment, ClientSelfCreatedAppointment
from . import client_bp
from datetime import datetime, timedelta
import os 
from werkzeug.utils import secure_filename
import json
from dotenv import load_dotenv
import stripe
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
        data=request.get_json()
        
        check = ['latitude','longitude', 'appointment_start_time']
        
        appointment_start_time=data['appointment_start_time']
        
        if not all(i in data for i in check):
            return jsonify({'error':'Not all fields are filled'})
        
        client_self_create_appointment = ClientSelfCreatedAppointment(
            
            patient_id=current_user.id,
            appointment_start_time=data['appointment_start_time'],
            end_time = data['end_time'] or appointment_start_time + timedelta(hours=1),
            latitude=data['latitude'],
            longitude=data['longtitude'],
            status = 'pending',
            notes= data['notes'] or '',
            service_name=data['service_name'] or '',
            service_description =data['service_description'] or '',
            payment = data['payment'] or '0',
            
            )
        db.session.add(client_self_create_appointment)
        db.session.commit()
    except Exception as e:
        current_app.logger.error(f"cant create client_self_create_appointment: {str(e)}")
        
        
        
@client_bp.route('/', methods=['POST'])
@login_required
def client_self_create_appointment():
    if current_user.role != 'client':
       return jsonify({'success': False, 'message': 'Доступ заборонено'}), 403
    try:
        data=request.get_json()
        
        check = ['latitude','longitude', 'appointment_start_time']
        
        appointment_start_time=data['appointment_start_time']
        
        if not all(i in data for i in check):
            return jsonify({'error':'Not all fields are filled'})
        
        client_self_create_appointment = ClientSelfCreatedAppointment(
            
            patient_id=current_user.id,
            appointment_start_time=data['appointment_start_time'],
            end_time = data['end_time'] or appointment_start_time + timedelta(hours=1),
            latitude=data['latitude'],
            longitude=data['longtitude'],
            status = 'pending',
            notes= data['notes'] or '',
            service_name=data['service_name'] or '',
            service_description =data['service_description'] or '',
            payment = data['payment'] or '0'
            
            )
        db.session.add(client_self_create_appointment)
        db.session.commit()
    except Exception as e:
        current_app.logger.error(f"cant create client_self_create_appointment: {str(e)}")        
    
    
    
   