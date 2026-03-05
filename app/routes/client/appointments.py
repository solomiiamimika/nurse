from . import client_bp
from flask import render_template, redirect, url_for, flash, request, abort, jsonify, current_app, Blueprint
from sqlalchemy.sql.sqltypes import DateTime
from app.extensions import db, bcrypt, socketio, db, mail
from app.models import Appointment, ProviderService, User, Message, Payment, ClientSelfCreatedAppointment, Review, RequestOfferResponse, ServiceHistory, CancellationPolicy
from app.utils import fuzz_coordinates, validate_coordinates
from app.supabase_storage import get_file_url, delete_from_supabase, upload_to_supabase, buckets
from datetime import datetime, timedelta
import os
from werkzeug.utils import secure_filename
import json
from dotenv import load_dotenv
import stripe
import supabase
import base64
from flask_mail import Message as MailMessage
from threading import Thread
from flask import current_app, request
from flask_socketio import join_room, leave_room, emit
from app.models import Message, db, User
from datetime import datetime
from app.supabase_storage import upload_to_supabase, supabase
from flask_cors import cross_origin
from flask_login import login_required, current_user
load_dotenv()
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
stripe_public_key = os.getenv('STRIPE_PUBLIC_KEY')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'app', 'static', 'uploads')
DOCUMENTS_FOLDER = os.path.join(UPLOAD_FOLDER, 'documents')
PROFILE_PICTURES_FOLDER = os.path.join(UPLOAD_FOLDER, 'profile_pictures')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DOCUMENTS_FOLDER, exist_ok=True)
os.makedirs(PROFILE_PICTURES_FOLDER, exist_ok=True)


def get_appointment_color(status):
    colors = {
        'scheduled': 'gray',
        'confirmed': 'blue',
        'completed': 'green',
        'cancelled': 'red'
    }
    return colors.get(status, 'gray')


def calendar_appointment_color(Status):
    colors_dictionary = {
        'scheduled': 'gray',
        'request_sended': 'yellow',
        'nurse_confirmed': 'green',
        'completed': 'blue',
        'cancelled': 'red'
    }
    return colors_dictionary.get(Status)


@client_bp.route('/appointments')
@login_required
def appointments():
    if current_user.role != 'client':
        return jsonify({'error': 'access denied'}), 403
    return render_template('client/appointments.html', stripe_public_key=stripe_public_key)


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
        if not nurse or nurse.role != 'provider':
            return jsonify({'success': False, 'message': 'Service provider not found'}), 404

        service = ProviderService.query.get(service_id)
        if not service or service.provider_id != int(nurse_id):
            return jsonify({'success': False, 'message': 'Service not found'}), 404

        appointment_time = datetime.strptime(date_time, '%Y-%m-%dT%H:%M')
        end_time = appointment_time + timedelta(minutes=service.duration)

        conflicting_appointments = Appointment.query.filter(
            Appointment.provider_id == nurse_id,
            Appointment.status == 'scheduled',
            ((Appointment.appointment_time <= appointment_time) & (Appointment.end_time > appointment_time)) |
            ((Appointment.appointment_time < end_time) & (Appointment.end_time >= end_time)) |
            ((Appointment.appointment_time >= appointment_time) & (Appointment.end_time <= end_time))
        ).count()

        if conflicting_appointments > 0:
            return jsonify({'success': False, 'message': 'This time is already taken'}), 400

        new_appointment = Appointment(
            client_id=current_user.id,
            provider_id=nurse_id,
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

        now = datetime.now()
        hours_until = (appointment.appointment_time - now).total_seconds() / 3600

        # Завантажуємо політику провайдера (якщо є)
        policy = CancellationPolicy.query.filter_by(provider_id=appointment.provider_id).first()

        # Якщо провайдер не встановив політику — скасування завжди безкоштовне
        if policy is None or policy.free_cancel_hours is None:
            fee_percent = 0
        elif hours_until >= policy.free_cancel_hours:
            fee_percent = 0
        else:
            fee_percent = policy.late_cancel_fee_percent

        if appointment.status == 'confirmed_paid':
            payment = Payment.query.filter_by(
                appointment_id=appointment.id, status='completed'
            ).first()

            if payment and payment.transaction_id:
                try:
                    if fee_percent == 0:
                        # Повне повернення — скасовуємо PaymentIntent
                        stripe.PaymentIntent.cancel(
                            payment.transaction_id,
                            cancellation_reason='requested_by_customer'
                        )
                        payment.status = 'canceled'
                    else:
                        # Частковий штраф — capture тільки % від суми
                        fee_cents = int(payment.amount_cents * fee_percent / 100)
                        stripe.PaymentIntent.capture(
                            payment.transaction_id,
                            amount_to_capture=fee_cents
                        )
                        payment.status = 'partially_captured'
                        payment.platform_fee_cents = fee_cents
                except stripe.StripeError as e:
                    current_app.logger.error(f'Stripe ERROR {str(e)}')
                    return jsonify({'success': False, 'message': 'Payment cancellation failed'}), 500

        appointment.status = 'cancelled'
        db.session.commit()

        msg = 'Appointment cancelled'
        if fee_percent > 0:
            msg = f'Appointment cancelled. Cancellation fee: {fee_percent}% per provider policy.'

        return jsonify({'success': True, 'message': msg, 'fee_percent': fee_percent})

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

        if not data.get('appointment_start_time'):
            return jsonify({'success': False, 'error': 'Time is required'}), 400

        if not data.get('address', '').strip():
            return jsonify({'success': False, 'error': 'Address is required'}), 400

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
            latitude=data.get('latitude') or 0,
            longitude=data.get('longitude') or 0,
            address=data['address'].strip(),
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
            offers = []
            for offer in req.offers:
                if offer.status == 'pending':
                    p = offer.provider
                    offers.append({
                        'offer_id': offer.id,
                        'provider_id': offer.provider_id,
                        'provider_name': p.full_name or p.user_name if p else 'Unknown',
                        'provider_photo': p.photo if p else None,
                        'proposed_price': offer.proposed_price,
                    })

            # For accepted requests, include the accepted provider info
            accepted_provider = None
            if req.status in ('accepted', 'authorized', 'completed', 'confirmed_paid') and req.provider:
                p = req.provider
                # Find the accepted offer to get the agreed price
                accepted_offer = next(
                    (o for o in req.offers if o.status == 'accepted'),
                    None
                )
                accepted_provider = {
                    'id': p.id,
                    'name': p.full_name or p.user_name,
                    'photo': p.photo,
                    'phone': p.phone_number,
                    'about': p.about_me,
                    'agreed_price': accepted_offer.proposed_price if accepted_offer else req.payment,
                    'latitude': p.latitude,
                    'longitude': p.longitude,
                }

            result.append({
                'id': req.id,
                'service_name': req.service_name,
                'status': req.status,
                'appointment_start_time': req.appointment_start_time.isoformat(),
                'created_appo': req.created_appo.isoformat(),
                'notes': req.notes,
                'payment': req.payment,
                'offers': offers,
                'accepted_provider': accepted_provider,
            })

        return jsonify({'success': True, 'requests': result}), 200

    except Exception as e:
        current_app.logger.error(f"Error retrieving requests: {str(e)}")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


@client_bp.route('/pay_request/<int:request_id>')
@login_required
def pay_request_page(request_id):
    """Email link landing page — redirect to dashboard with ?pay_request=ID."""
    req = ClientSelfCreatedAppointment.query.filter_by(
        id=request_id, patient_id=current_user.id
    ).first_or_404()
    if req.status == 'authorized':
        flash('Payment already authorized for this appointment.', 'info')
        return redirect(url_for('client.dashboard'))
    if req.status != 'accepted':
        flash('This appointment cannot be paid at this stage.', 'warning')
        return redirect(url_for('client.dashboard'))
    return redirect(url_for('client.dashboard') + f'?pay_request={request_id}')


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


@client_bp.route('/client_accept_request/<int:offer_id>/', methods=['POST'])
@login_required
def client_accept_request(offer_id):
    if current_user.role != 'client':
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    try:
        provider_offer = RequestOfferResponse.query.get(offer_id)

        if not provider_offer or provider_offer.status != 'pending':  #тут змінити якщо ми хочемо бачити після прийняття запропонованих провайдерів
            return jsonify({'success': False, 'message': 'Request not found'}), 404  # обробка коли не виводити

        req = ClientSelfCreatedAppointment.query.get(provider_offer.request_id)

        if not req or provider_offer.status != 'pending':
            return jsonify({'success': False, 'message': 'Request not found'}), 404

        if req.patient_id != current_user.id:
            return jsonify({'success': False, 'message': 'Request not found'}), 404

        provider_offer.status = 'accepted'
        req.status = 'accepted'
        req.provider_id = provider_offer.provider_id
        req.payment = provider_offer.proposed_price

        # Reject all other pending offers for this request
        RequestOfferResponse.query.filter(
            RequestOfferResponse.request_id == req.id,
            RequestOfferResponse.id != provider_offer.id,
            RequestOfferResponse.status == 'pending'
        ).update({'status': 'rejected'}, synchronize_session=False)

        # Створюємо Appointment
        appointment = Appointment(
            client_id=current_user.id,
            provider_id=provider_offer.provider_id,
            nurse_service_id=req.nurse_service_id,
            appointment_time=req.appointment_start_time,
            end_time=req.end_time,
            status='scheduled',
            notes=req.notes
        )
        db.session.add(appointment)
        db.session.flush()  # отримуємо appointment.id до commit

        # Створюємо запис в ServiceHistory
        service_history = ServiceHistory(
            provider_id=provider_offer.provider_id,
            client_id=current_user.id,
            request_id=req.id,
            service_name=req.service_name,
            service_description=req.service_description,
            price=provider_offer.proposed_price,
            appointment_time=req.appointment_start_time,
            end_time=req.end_time,
            status='scheduled'
        )
        db.session.add(service_history)
        db.session.commit()

        return jsonify({'success': True, 'message': 'Offer accepted', 'appointment_id': appointment.id}), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error accepting offer: {str(e)}")
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

    if rating <= 3 and not comment:
        return jsonify({'success': False, 'message': 'Please provide a reason for your low rating'}), 400

    appo = Appointment.query.filter_by(id=appointment_id, client_id=current_user.id).first()
    if not appo:
        return jsonify({'success': False, 'message': 'Appointment not found'}), 404
    if appo.status != 'confirmed_paid':
        return jsonify({'success': False, 'message': 'Review can be left only after the visit is completed'}), 400

    # Check to prevent duplicate reviews for the same appointment.
    existing = Review.query.filter_by(patient_id=current_user.id, provider_id=appo.provider_id, appointment_id=appo.id).first()
    if existing:
        return jsonify({'success': False, 'message': 'Review already left'}), 400

    review = Review(
        patient_id=current_user.id,
        provider_id=appo.provider_id,
        appointment_id=appo.id,
        rating=rating,
        comment=comment
    )
    db.session.add(review)
    db.session.commit()

    return jsonify({'success': True, 'message': 'Thank you for your review!'})


@client_bp.route('/get_reviews/<int:nurse_id>')
@login_required
def get_reviews(nurse_id):
    reviews = Review.query.filter_by(provider_id=nurse_id).order_by(
        Review.created_at.desc()
    ).all()

    return jsonify({
        'reviews': [{
            'id': r.id,
            'patient_name': r.patient.full_name,
            'rating': r.rating,
            'comment': r.comment,
            'response_text': r.response_text,
            'response_at': r.response_at.isoformat() if r.response_at else None,
            'review_direction': r.review_direction or 'client_to_provider',
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

    if appointment.status not in ('confirmed_paid', 'completed'):
        return jsonify({'can_review': False, 'reason': 'Appointment not completed'})

    existing_review = Review.query.filter_by(
        appointment_id=appointment_id,
        patient_id=current_user.id
    ).first()

    if existing_review:
        return jsonify({'can_review': False, 'review_exists': True})

    return jsonify({'can_review': True, 'review_exists': False})


@client_bp.route('/review/<int:review_id>/respond', methods=['POST'])
@login_required
def respond_to_review(review_id):
    """Let the reviewed party write a public dispute response."""
    review = Review.query.get_or_404(review_id)

    # Only the reviewed party can respond
    if review.review_direction == 'client_to_provider':
        if current_user.id != review.provider_id:
            return jsonify({'success': False, 'message': 'Access denied'}), 403
    else:
        if current_user.id != review.patient_id:
            return jsonify({'success': False, 'message': 'Access denied'}), 403

    if review.response_text:
        return jsonify({'success': False, 'message': 'Response already submitted'}), 400

    data = request.get_json() or {}
    response_text = data.get('response_text', '').strip()
    if not response_text:
        return jsonify({'success': False, 'message': 'Response text is required'}), 400

    review.response_text = response_text
    review.response_at = datetime.now()
    db.session.commit()

    return jsonify({'success': True, 'message': 'Response submitted successfully'})


@client_bp.route('/client_get_history', methods=['GET'])
@login_required
def client_get_history():
    """Return completed/cancelled requests and completed appointments for history page."""
    if current_user.role != 'client':
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    try:
        # Completed/cancelled self-created requests
        reqs = ClientSelfCreatedAppointment.query.filter(
            ClientSelfCreatedAppointment.patient_id == current_user.id,
            ClientSelfCreatedAppointment.status.in_(['completed', 'confirmed_paid', 'cancelled'])
        ).order_by(ClientSelfCreatedAppointment.created_appo.desc()).all()

        requests_list = []
        for req in reqs:
            provider_name = None
            if req.provider:
                provider_name = req.provider.full_name or req.provider.user_name
            requests_list.append({
                'id': req.id,
                'service_name': req.service_name,
                'status': req.status,
                'payment': req.payment,
                'appointment_start_time': req.appointment_start_time.isoformat() if req.appointment_start_time else None,
                'created_appo': req.created_appo.isoformat() if req.created_appo else None,
                'provider_name': provider_name,
            })

        # Completed appointments (direct bookings)
        appos = Appointment.query.filter(
            Appointment.client_id == current_user.id,
            Appointment.status.in_(['completed', 'confirmed_paid', 'cancelled', 'work_submitted'])
        ).order_by(Appointment.appointment_time.desc()).all()

        appointments_list = []
        for a in appos:
            provider = User.query.get(a.provider_id)
            service = ProviderService.query.get(a.nurse_service_id) if a.nurse_service_id else None
            service_name = service.name if service and service.name else (service.base_service.name if service and service.base_service else 'Service')
            appointments_list.append({
                'id': a.id,
                'service_name': service_name,
                'status': a.status,
                'appointment_time': a.appointment_time.isoformat() if a.appointment_time else None,
                'provider_name': (provider.full_name or provider.user_name) if provider else 'Unknown',
                'notes': a.notes,
            })

        return jsonify({
            'success': True,
            'requests': requests_list,
            'appointments': appointments_list,
        })

    except Exception as e:
        current_app.logger.error(f"Error retrieving history: {str(e)}")
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
