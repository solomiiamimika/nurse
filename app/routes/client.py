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
import supabase
import base64
from app.extensions import socketio, db
from flask import current_app, request
from flask_socketio import join_room, leave_room, emit
from app.models import Message, db,User
from datetime import datetime
from app.supabase_storage import upload_to_supabase,supabase
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
    if current_user.role != 'client':
        return redirect(url_for('auth.login'))
    
    search_query = request.args.get('q', '').strip()
    nurses = []

    if search_query:
        nurses = User.query.filter(User.role == 'nurse', User.location_approved == True).outerjoin(NurseService).filter(
            (User.full_name.ilike(f'%{search_query}%')) | 
            (User.user_name.ilike(f'%{search_query}%')) |
            (NurseService.name.ilike(f'%{search_query}%')) |
            (User.address.ilike(f'%{search_query}%')) 
        ).distinct().all()
    else:
        nurses = User.query.filter_by(role='nurse', location_approved=True).all()

    return render_template('client/dashboard.html', nurses=nurses, search_query=search_query)


@client_bp.route('/delete_document', methods=['POST'])
@login_required
def delete_document():
    if current_user.role != 'client':
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    try:
        data = request.get_json()
        doc_name = data.get('doc_name')
        
        if not doc_name:
            return jsonify({'success': False, 'message': 'Document name is not specified.'})

        try:
            delete_from_supabase(doc_name, buckets['documents'])
        except Exception as e:
            print(f"Supabase Error {e}")

        if current_user.documents:
            documents = json.loads(current_user.documents)
            
            if doc_name in documents:
                documents.remove(doc_name)
                current_user.documents = json.dumps(documents) if documents else None
                db.session.commit()
                return jsonify({'success': True})
            else:
                return jsonify({'success': False, 'message': 'File not found in database record'})
        
        return jsonify({'success': False, 'message': 'User has no documents'})

    except Exception as e:
        print(f"CRITICAL ERROR: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500



@client_bp.route('/update_location', methods=['POST'])
@login_required
def update_location():
    if current_user.role != 'client':
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
@client_bp.route('/get_nurses_locations')
@login_required
def get_nurses_locations():
    if current_user.role != 'client':
        return jsonify({'error': 'Entrance not allowed'}), 403
    
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
            
            # Profile photo processing
            if 'profile_picture' in request.files:
                file = request.files['profile_picture']
                if file and file.filename != '' and allowed_file(file.filename):
                    # deleting old photo
                    if current_user.photo:
                        delete_from_supabase(current_user.photo, buckets['profile_pictures'])
                    
                    # Upload new photo
                    filename, file_url = upload_to_supabase(
                        file, 
                        buckets['profile_pictures'], 
                        current_user.id,
                        'profile'
                    )
                    if filename:
                        current_user.photo = filename
            
            # Documents processing
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
            flash('Profile successfully updated!', 'success')
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating profile: {str(e)}")
            flash('Error updating profile', 'danger')
        
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



@client_bp.route('/appointments')
@login_required
def appointments():
    if current_user.role != 'client':
        return jsonify({'error': 'access denied'}), 403
    return render_template('client/appointments.html', stripe_public_key = stripe_public_key)


@client_bp.route('/get_appointments')
@login_required
def get_appointments():
    if current_user.role != 'client':
        return jsonify({'error': 'access denied'}), 403
    
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
                current_app.logger.error(f"Error parsing date format: {e}")
        
        appointments = query.order_by(Appointment.appointment_time.asc()).all()
        
        result = []
        for app in appointments:
            service_name = app.nurse_service.name if app.nurse_service else "Service"
            nurse_name = app.nurse.user_name if app.nurse else "Nurse"
            
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
        current_app.logger.error(f"error in get_appointments: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500
    
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
        return jsonify({'error': 'access denied'}), 403

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
        return jsonify({'error': 'access denied'}), 403

    nurse_id = request.args.get('nurse_id')
    service_id = request.args.get('service_id')
    date_str = request.args.get('date')

    if not all([nurse_id, service_id, date_str]):
        return jsonify({'error': 'Service provider, service and date must be specified'}), 400

    try:
        date = datetime.strptime(date_str, '%Y-%m-%d').date()
        service = NurseService.query.get(service_id)

        if not service or service.nurse_id != int(nurse_id):
            return jsonify({'error': 'Service provider not found'}), 404

        # working hours
        work_start = 9
        work_end = 18

        # getting all scheduled appointments for this day
        appointments = Appointment.query.filter(
            Appointment.nurse_id == nurse_id,
            db.func.date(Appointment.appointment_time) == date,
            Appointment.status.in_(['scheduled', 'confirmed'])
        ).all()
    # Generate available slots
        available_slots = []
        current_time = datetime.combine(date, datetime.min.time()) + timedelta(hours=work_start)
        end_time = datetime.combine(date, datetime.min.time()) + timedelta(hours=work_end)

        while current_time + timedelta(minutes=service.duration) <= end_time:
            slot_end = current_time + timedelta(minutes=service.duration)

            # Check if this slot does not overlap with existing appointments
            is_available = True
            for app in appointments:
                if (current_time < app.end_time) and (slot_end > app.appointment_time):
                    is_available = False
                    break

            if is_available:
                available_slots.append(current_time.strftime('%H:%M'))

            current_time += timedelta(minutes=30)  # Step 30 minutes

        return jsonify(available_slots)

    except Exception as e:
        current_app.logger.error(f"Error getting available times: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500
        


@client_bp.route('/get_nurse_services')
@login_required
def get_nurse_services():
    if current_user.role != 'client':
        return jsonify({'error': 'access denied'}), 403
    
    nurse_id = request.args.get('nurse_id')
    if not nurse_id:
        return jsonify({'error': 'No services specified'}), 400
    
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
        return jsonify({'error': 'Internal server error'}), 500



@client_bp.route('/create_appointment', methods=['POST'])
@login_required
def create_appointment():
    if current_user.role != 'client':
        return jsonify({'success': False, 'message': 'access denied'}), 403
    
    try:
        data = request.get_json()
        nurse_id = data.get('nurse_id')
        service_id = data.get('service_id')
        date_time = data.get('date_time')
        notes = data.get('notes')
        
        if not all([nurse_id, service_id, date_time]):
            return jsonify({'success': False, 'message': 'All fields must be filled'}), 400
        
    
        nurse = User.query.get(nurse_id)
        if not nurse or nurse.role != 'nurse':
            return jsonify({'success': False, 'message': 'Service provider not found'}), 404
        
        service = NurseService.query.get(service_id)
        if not service or service.nurse_id != int(nurse_id):
            return jsonify({'success': False, 'message': 'Service not found'}), 404
        

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
            return jsonify({'success': False, 'message': 'This time is already taken'}), 400
        

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
            'message': 'Appointment created successfully',
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

        # creating session for Stripe payment
        session = stripe.checkout.Session.create(
            payment_method_types=['card', 'apple_pay'],
            line_items=[{
                'price_data': {
                    'currency': 'eur',
                    'product_data': {
                        'name': appointment.nurse_service.name,
                    },
                    'unit_amount': int(appointment.nurse_service.price * 100),  # in cents
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

                flash('Payment successful!', 'success')
            else:
                flash('Payment not confirmed', 'warning')
        else:
            flash('Payment information is missing', 'warning')
    
    except stripe.StripeError as e:
        current_app.logger.error(f"Stripe verification error: {str(e)}")
        flash('Error during payment verification', 'danger')
    except Exception as e:
        current_app.logger.error(f"Error in payment_success: {str(e)}")
        flash('Server error', 'danger')

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

    # Handling a successful payment event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        handle_successful_payment(session)

    return jsonify({'status': 'success'})

def handle_successful_payment(session):
    try:
        appointment_id = session['metadata'].get('appointment_id')
        user_id = session['metadata'].get('user_id')
        payment_intent_id = session.get('payment_intent')

        if not (appointment_id and user_id and payment_intent_id):
            return

        # 1) анти-дубль: якщо вже є платіж з таким PI — нічого не робимо
        existing = Payment.query.filter_by(transaction_id=payment_intent_id).first()
        if existing:
            return

        # 2) витягнути PI щоб взяти transfer_group + latest_charge (корисно)
        pi = stripe.PaymentIntent.retrieve(payment_intent_id)

        amount_cents = int(session['amount_total'])
        currency = session['currency']

        payment = Payment(
            user_id=int(user_id),
            appointment_id=int(appointment_id),
            amount=float(amount_cents) / 100,  # тимчасово, краще мати amount_cents в моделі
            payment_date=datetime.utcnow(),
            status='completed',
            transaction_id=payment_intent_id,
            payment_method=(session['payment_method_types'][0] if session.get('payment_method_types') else 'card'),
        )

        # якщо додаси ці поля в модель:
        payment.amount_cents = amount_cents
        payment.currency = currency
        payment.stripe_payment_intent_id = payment_intent_id
        payment.stripe_charge_id = pi.get("latest_charge")
        payment.transfer_group = pi.get("transfer_group")

        db.session.add(payment)

        appointment = Appointment.query.get(int(appointment_id))
        if appointment:
            appointment.status = 'confirmed_paid'

        db.session.commit()

    except Exception as e:
        current_app.logger.error(f"Webhook error: {str(e)}")
        db.session.rollback()



# @client_bp.route('/create_payment_session', methods=['POST'])
# @login_required
# def create_payment_session():
#     data = request.get_json()
#     appointment_id = data.get('appointment_id')
#     appointment = Appointment.query.get_or_404(appointment_id)

#     if appointment.client_id != current_user.id:
#         return jsonify({'error': 'Unauthorized'}), 403

#     if appointment.status == 'confirmed_paid':
#         return jsonify({'error': 'Appointment already paid'}), 400

#     amount_cents = int(round(appointment.nurse_service.price * 100))
#     transfer_group = f"appt_{appointment_id}"

#     session = stripe.checkout.Session.create(
#         payment_method_types=['card'],  # Apple Pay включиться як wallet для card
#         line_items=[{
#             'price_data': {
#                 'currency': 'eur',
#                 'product_data': {'name': appointment.nurse_service.name},
#                 'unit_amount': amount_cents,
#             },
#             'quantity': 1,
#         }],
#         mode='payment',
#         success_url=url_for('client.payment_success', appointment_id=appointment_id, _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
#         cancel_url=url_for('client.payment_cancel', _external=True),
#         customer_email=current_user.email,

#         # ВАЖЛИВО: це піде в PaymentIntent
#         payment_intent_data={
#             "transfer_group": transfer_group,
#             "metadata": {
#                 "appointment_id": str(appointment_id),
#                 "user_id": str(current_user.id),
#             }
#         },

#         metadata={
#             'appointment_id': appointment_id,
#             'user_id': current_user.id
#         }
#     )

#     return jsonify({'sessionId': session.id})

   


@client_bp.route('/payment_cancel')
@login_required
def payment_cancel():
    try:
        session_id = request.args.get('session_id')
        
        if session_id:
            # getting Stripe session for logging
            session = stripe.checkout.Session.retrieve(session_id)
            
            # Log cancellation info
            current_app.logger.info(f"Payment canceled - Session ID: {session_id}, Status: {session.payment_status}")
            
            # If there is appointment_id in metadata, we can update the status
            if 'appointment_id' in session.metadata:
                appointment = Appointment.query.get(session.metadata['appointment_id'])
                if appointment and appointment.client_id == current_user.id:
                    appointment.status = 'payment_canceled'
                    db.session.commit()
        
        # Creating a record of the canceled payment
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
    
    flash('Payment canceled. You can try again.', 'warning')
    return redirect(url_for('client.appointments'))


@client_bp.route('/appointments/<int:appointment_id>/payout', methods=['POST'])
@login_required
def payout_after_completion(appointment_id):
    appt = Appointment.query.get_or_404(appointment_id)

    # тут має бути перевірка прав: admin/провайдер/твоя логіка
    if appt.status != "completed":
        return jsonify({"error": "Appointment not completed"}), 400

    payment = Payment.query.filter_by(appointment_id=appointment_id, status="completed").first()
    if not payment:
        return jsonify({"error": "No paid payment found"}), 400

    provider = User.query.get_or_404(appt.nurse_id)  # адаптуй під свою модель
    if not provider.stripe_account_id:
        return jsonify({"error": "Provider not connected to Stripe"}), 400

    amount_cents = int(round(payment.amount * 100))
    platform_fee_cents = int(round(amount_cents * 0.10))# приклад: 10% твоя комісія
    payout_cents = amount_cents - platform_fee_cents

    transfer_group = f"appt_{appointment_id}"

    tr = stripe.Transfer.create(
        amount=payout_cents,
        currency="eur",
        destination=provider.stripe_account_id,  # acct_...
        transfer_group=transfer_group,
        metadata={"appointment_id": str(appointment_id), "payment_intent": payment.transaction_id},
        idempotency_key=f"tr_{appointment_id}",
    )

    # payment.stripe_transfer_id = tr.id  (якщо додаси поле)
    # payment.status = "paid_out"
    # db.session.commit()

    return jsonify({"transferId": tr.id})




@client_bp.route('/cancel_appointment', methods=['POST'])
@login_required
def cancel_appointment():
    if current_user.role != 'client':
        return jsonify({'success': False, 'message': 'access denied'}), 403
    
    try:
        data = request.get_json()
        appointment_id = data.get('appointment_id')
        reason = data.get('reason', '')
        
        if not appointment_id:
            return jsonify({'success': False, 'message': 'ID for Appointment Not Specified'}), 400
        
        appointment = Appointment.query.filter_by(
            id=appointment_id,
            client_id=current_user.id
        ).first()
        
        if not appointment:
            return jsonify({'success': False, 'message': 'Appointment not found'}), 404
        
        # Check if it's too late to cancel (e.g., less than 24 hours before)
        if appointment.appointment_time - datetime.utcnow() < timedelta(hours=24):
            return jsonify({
                'success': False,
                'message': 'Cancellation less than 24 hours before the appointment is not possible'
            }), 400
        
        appointment.status = 'cancelled'
        appointment.cancellation_reason = reason
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Appointment cancelled'})
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error cancelling appointment: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500
    
@client_bp.route('/client_self_create_appointment', methods=['POST'])
@login_required
def client_self_create_appointment():
    if current_user.role != 'client':
        return jsonify({'success': False, 'message': 'access denied'}), 403
    
    try:
        data = request.get_json()
        
        required_fields = ['latitude', 'longitude', 'appointment_start_time']
        
        if not all(field in data for field in required_fields):
            return jsonify({'success': False, 'error': 'Not all required fields are filled'}), 400
        
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
            created_appo=datetime.now()
        )
        
        db.session.add(appointment)
        db.session.commit()
        
        #notify_nurses_about_new_appointment(appointment)
        
        return jsonify({
            'success': True,
            'message': 'Request successfully created',
            'appointment_id': appointment.id
        }), 201
        
    except Exception as e:
        current_app.logger.error(f"Error creating appointment request: {str(e)}")
        db.session.rollback()
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



@client_bp.route('/client_get_requests', methods=['GET'])
@login_required
def client_get_requests():
    if current_user.role != 'client':
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
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
        current_app.logger.error(f"Error retrieving requests: {str(e)}")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500

@client_bp.route('/client_cancel_request/<int:request_id>', methods=['POST'])
@login_required
def client_cancel_request(request_id):
    if current_user.role != 'client':
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    try:
        request = ClientSelfCreatedAppointment.query.filter_by(
            id=request_id, 
            patient_id=current_user.id
        ).first()
        
        if not request:
            return jsonify({'success': False, 'message': 'Request not found'}), 404
        
        if request.status not in ['pending', 'accepted']:
            return jsonify({'success': False, 'message': 'Cannot cancel this request'}), 400

        request.status = 'cancelled'
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Request cancelled'}), 200
        
    except Exception as e:
        current_app.logger.error(f"Error cancelling request: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


@client_bp.route('/leave_review', methods=['POST'])
@login_required
def leave_review():
    if current_user.role != 'client':
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

    appo = Appointment.query.filter_by(id=appointment_id, client_id=current_user.id).first()
    if not appo:
        return jsonify({'success': False, 'message': 'Appointment not found'}), 404
    if appo.status != 'confirmed_paid':
        return jsonify({'success': False, 'message': 'Review can be left only after the visit is completed'}), 400

    # Check to prevent duplicate reviews for the same appointment.
    existing = Review.query.filter_by(patient_id=current_user.id, doctor_id=appo.nurse_id, appointment_id=appo.id).first()
    if existing:
        return jsonify({'success': False, 'message': 'Review already left'}), 400

    review = Review(
        patient_id=current_user.id,
        doctor_id=appo.nurse_id,     # nurse
        appointment_id=appo.id,
        rating=rating,
        comment=comment
    )
    db.session.add(review)
    db.session.commit()

    return jsonify({'success': True, 'message': 'Thank you for your review!'})



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
        return jsonify({'success': False, 'message': 'Review not found'}), 404

@client_bp.route('/can_review/<int:appointment_id>')
@login_required
def can_review_appointment(appointment_id):
    appointment = Appointment.query.filter_by(
        id=appointment_id, 
        client_id=current_user.id
    ).first()
    
    if not appointment:
        return jsonify({'can_review': False, 'reason': 'Appointment not found'})
    
    if appointment.status != 'completed':
        return jsonify({'can_review': False, 'reason': 'Appointment not completed'})

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



@client_bp.route("/provider/<int:provider_id>")
@login_required
def provider_detail(provider_id):
    provider = User.query.filter_by(id=provider_id, role='nurse').first_or_404()
    reviews = Review.query.filter_by(doctor_id=provider.id).order_by(
        Review.created_at.desc()
    ).all()
    servises= NurseService.query.filter_by(nurse_id=provider.id,is_available=True).all()
    photo = None
    if provider.photo:
        photo = get_file_url(provider.photo,buckets['profile_pictures'])
    return render_template("client/provider_public_profile.html", provider=provider, reviews=reviews, services=servises, photo=photo)
    


# @client_bp.route('/complete_appointment', methods=['POST'])
# @login_required
# def complete_appointment():
#     data = request.get_json()
#     appointment_id = data.get('appointment_id')
    
#     appointment = Appointment.query.get_or_404(appointment_id)
    
#     if appointment.client_id != current_user.id:
#         return jsonify({'success': False, 'message': 'Unauthorized'}), 403

#     if appointment.status != 'work_submitted':
#         return jsonify({'success': False, 'message': 'Nurse has not submitted the work yet.'}), 400

#     try:
#         # Шукаємо запис про оплату в БД
#         payment = Payment.query.filter_by(appointment_id=appointment.id, status='completed').first()
#         if not payment:
#             return jsonify({'success': False, 'message': 'Payment record not found'}), 400

#         nurse = User.query.get(appointment.nurse_id)
#         if not nurse.stripe_account_id:
#              return jsonify({'success': False, 'message': 'Nurse has not connected Stripe'}), 400

#         # --- ВИПЛАТА З УРАХУВАННЯМ КОМІСІЇ ---
#         # Вираховуємо суму для медсестри: Загальна сума - Ваша комісія 10%
#         # (Дані беруться з вашої моделі Payment, куди ви мали записати platform_fee_cents при успішній оплаті)
#         amount_to_nurse_cents = int(payment.amount_cents) - int(payment.platform_fee_cents)

#         transfer = stripe.Transfer.create(
#             amount=amount_to_nurse_cents, # Провайдер отримує менше
#             currency=payment.currency,
#             destination=nurse.stripe_account_id,
#             transfer_group=payment.transfer_group,
#             metadata={
#                 "appointment_id": appointment.id,
#                 "type": "payout",
#                 "original_total": payment.amount_cents,
#                 "platform_took": payment.platform_fee_cents
#             }
#         )

#         # Оновлюємо статус в БД
#         payment.stripe_transfer_id = transfer.id
#         payment.status = 'payout_sent'
#         appointment.status = 'completed'
#         db.session.commit()
        
#         return jsonify({'success': True, 'message': 'Appointment completed and payment released!'})

#     except stripe.StripeError as e:
#         current_app.logger.error(f"Stripe Transfer Error: {str(e)}")
#         return jsonify({'success': False, 'message': str(e)}), 500
    
@client_bp.route('/complete_appointment', methods=['POST'])  
@login_required
def complete_appointment():
    data = request.get_json()
    appointment_id = data.get('appointment_id')
    
    appointment = Appointment.query.get_or_404(appointment_id)
    
    if appointment.client_id != current_user.id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    if appointment.status != 'work_submitted':
        return jsonify({'success': False, 'message': 'Nurse has not submitted the work yet.'}), 400

    try:
        # Шукаємо запис про оплату в БД
        payment = Payment.query.filter_by(appointment_id=appointment.id, status='completed').first()
        if not payment:
            return jsonify({'success': False, 'message': 'Payment record not found'}), 400

        nurse = User.query.get(appointment.nurse_id)
        if not nurse.stripe_account_id:
             return jsonify({'success': False, 'message': 'Nurse has not connected Stripe'}), 400

        # --- ВИПЛАТА З УРАХУВАННЯМ КОМІСІЇ ---
        # Вираховуємо суму для медсестри: Загальна сума - Ваша комісія 10%
        # (Дані беруться з вашої моделі Payment, куди ви мали записати platform_fee_cents при успішній оплаті)
        amount_to_nurse_cents = int(payment.amount_cents) - int(payment.platform_fee_cents)

        transfer = stripe.Transfer.create(
            amount=amount_to_nurse_cents, # Провайдер отримує менше
            currency=payment.currency,
            destination=nurse.stripe_account_id,
            transfer_group=payment.transfer_group,
            metadata={
                "appointment_id": appointment.id,
                "type": "payout",
                "original_total": payment.amount_cents,
                "platform_took": payment.platform_fee_cents
            }
        )

        # Оновлюємо статус в БД
        payment.stripe_transfer_id = transfer.id
        payment.status = 'payout_sent'
        appointment.status = 'completed'
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Appointment completed and payment released!'})

    except stripe.StripeError as e:
        current_app.logger.error(f"Stripe Transfer Error: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500