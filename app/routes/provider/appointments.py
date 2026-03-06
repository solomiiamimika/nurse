from . import provider_bp
from flask import Blueprint, jsonify, request, current_app, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models import User, Message, db, Service, ProviderService, Appointment, ClientSelfCreatedAppointment, RequestOfferResponse, ServiceHistory, CancellationPolicy
from app.utils import fuzz_coordinates, haversine_distance, validate_coordinates
from datetime import datetime
import json
from app.supabase_storage import get_file_url, delete_from_supabase, upload_to_supabase, buckets, supabase
import os
from werkzeug.utils import secure_filename
from math import radians, sin, cos, sqrt, atan2
import stripe
from app.extensions import socketio, db, mail
from flask import current_app, request
from flask_socketio import join_room, leave_room, emit
from app.models import Message, db, User
from datetime import datetime
from sqlalchemy import func
from flask_mail import Message as MailMessage
from threading import Thread
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'app', 'static', 'uploads')
DOCUMENTS_FOLDER = os.path.join(UPLOAD_FOLDER, 'documents')
PROFILE_PICTURES_FOLDER = os.path.join(UPLOAD_FOLDER, 'profile_pictures')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx'}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DOCUMENTS_FOLDER, exist_ok=True)
os.makedirs(PROFILE_PICTURES_FOLDER, exist_ok=True)


def calendar_appointment_color(Status):
    colors_dictionary = {
        'scheduled': 'gray',
        'request_sended': 'yellow',
        'provider_confirmed': 'green',
        'completed': 'blue',
        'cancelled': 'red'
    }
    return colors_dictionary.get(Status)


@provider_bp.route('/appointments')
@login_required
def appointments():
    if current_user.role != 'provider':
        return jsonify({'error': 'Access denied'}), 403
    return render_template('provider/appointments.html')


@provider_bp.route('/get_appointments')
@login_required
def get_appointments():
    print("Received request to /provider/get_appointments")  # Logging
    if current_user.role != 'provider':
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
            service_name = app.provider_service.name if app.provider_service else "Service"
            result.append({
                'id': app.id,
                'title': f"{service_name} - {app.client.user_name}",
                'start': app.appointment_time.isoformat(),
                'end': app.end_time.isoformat(),
                'color': calendar_appointment_color(app.status),
                'extendedProps': {
                    'client_name': app.client.user_name,
                    'provider_name': app.provider.user_name,
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


@provider_bp.route('/get_my_appointments')
@login_required
def get_my_appointments():
    if current_user.role != 'provider':
        return jsonify({'error': 'Access denied'}), 403

    try:
        # Беремо тільки майбутні та підтверджені записи
        # Можна додати status='confirmed' або 'paid', залежно від вашої логіки
        appointments = Appointment.query.filter(
            Appointment.provider_id == current_user.id,
            Appointment.appointment_time >= datetime.utcnow(),
            Appointment.status.in_(['confirmed', 'confirmed_paid', 'scheduled'])  # Додайте ваші статуси
        ).order_by(Appointment.appointment_time.asc()).all()

        result = []
        for app in appointments:
            # Отримуємо назву сервісу та ціну
            service_name = app.provider_service.name if app.provider_service else "Service"
            price = app.provider_service.price if app.provider_service else 0

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
                'type': 'appointment',
                'client_id': app.client.id
            })

        return jsonify(result)

    except Exception as e:
        print(f"Error in get_my_appointments: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


@provider_bp.route('/update_appointment_status', methods=['POST'])
@login_required
def update_appointment_status():
    data = request.get_json()
    appointment_id = data.get('appointment_id')
    new_status = data.get('status')

    appointment = Appointment.query.get_or_404(appointment_id)
    if appointment.provider_id != current_user.id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    # Logic: Provider Marks Job as Done
    if new_status == 'work_submitted':
        if appointment.status != 'confirmed_paid':
            return jsonify({'success': False, 'message': 'Cannot submit work for unpaid appointment'}), 400

        appointment.status = 'work_submitted'
        db.session.commit()
        return jsonify({'success': True, 'message': 'Work submitted! Waiting for client approval.'})

    # Logic: Provider Accepts/Declines
    elif new_status in ['confirmed', 'cancelled']:
        appointment.status = new_status
        db.session.commit()
        return jsonify({'success': True})

    return jsonify({'success': False, 'message': 'Invalid status update for Provider'}), 400


@provider_bp.route('/provider_get_requests', methods=['GET'])
@login_required
def provider_get_requests():
    if current_user.role != 'provider':
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    try:
        provider_lat = current_user.latitude
        provider_lng = current_user.longitude

        # Already-bid request IDs for this provider
        already_bid_ids = {
            o.request_id for o in RequestOfferResponse.query.filter_by(
                provider_id=current_user.id
            ).all()
        }

        requests = ClientSelfCreatedAppointment.query.filter(
            ClientSelfCreatedAppointment.status.in_(('pending', 'has_offers'))
        ).all()

        result = []
        for req in requests:
            if req.id in already_bid_ids:
                continue
            if not req.latitude or not req.longitude:
                continue

            # Для перегляду запиту: відстань + розмиті координати для карти
            # Точна адреса буде видна тільки після прийняття
            distance_km = None
            if provider_lat and provider_lng:
                distance_km = round(haversine_distance(
                    provider_lat, provider_lng, req.latitude, req.longitude
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

        # Sort: requests with known distance first (closest first), unknown last
        result.sort(key=lambda x: (x['distance_km'] is None, x['distance_km'] or 0))

        return jsonify({'success': True, 'requests': result}), 200

    except Exception as e:
        print(e)
        return jsonify({'success': False, 'error': 'Server Error'}), 500


@provider_bp.route('/provider_accept_request/<int:request_id>', methods=['POST'])
@login_required
def provider_accept_request(request_id):
    if current_user.role != 'provider':
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    try:
        data = request.get_json() or {}
        price = data.get('price')

        # Validate price
        try:
            price = float(price) if price is not None else 0
        except (ValueError, TypeError):
            price = 0

        req = ClientSelfCreatedAppointment.query.get(request_id)

        if not req:
            return jsonify({'success': False, 'message': 'Request not found'}), 404

        if req.status not in ('pending', 'has_offers'):
            return jsonify({'success': False, 'message': 'Request already processed'}), 400

        # Prevent duplicate offer from same provider
        existing = RequestOfferResponse.query.filter_by(
            request_id=req.id, provider_id=current_user.id
        ).first()
        if existing:
            return jsonify({'success': False, 'message': 'You already sent an offer for this request'}), 400

        # Mark request as having offers (stays visible to other providers)
        req.status = 'has_offers'

        new_offer = RequestOfferResponse(request_id=req.id, provider_id=current_user.id, proposed_price=price)
        db.session.add(new_offer)
        db.session.commit()
        return jsonify({'success': True})

    except Exception as e:
        current_app.logger.error(f"Error accepting request: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


@provider_bp.route('/withdraw_offer/<int:offer_id>', methods=['POST'])
@login_required
def withdraw_offer(offer_id):
    """Provider withdraws their pending offer before client accepts."""
    if current_user.role != 'provider':
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    try:
        offer = RequestOfferResponse.query.filter_by(
            id=offer_id,
            provider_id=current_user.id
        ).first()

        if not offer:
            return jsonify({'success': False, 'message': 'Offer not found'}), 404

        if offer.status != 'pending':
            return jsonify({'success': False, 'message': 'Can only withdraw pending offers'}), 400

        offer.status = 'rejected'

        # If no other pending offers remain, revert request status to pending
        req = ClientSelfCreatedAppointment.query.get(offer.request_id)
        if req and req.status == 'has_offers':
            remaining = RequestOfferResponse.query.filter(
                RequestOfferResponse.request_id == req.id,
                RequestOfferResponse.id != offer.id,
                RequestOfferResponse.status == 'pending'
            ).count()
            if remaining == 0:
                req.status = 'pending'

        db.session.commit()
        return jsonify({'success': True, 'message': 'Offer withdrawn'})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error withdrawing offer: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'}), 500


@provider_bp.route('/respond_to_counter/<int:offer_id>', methods=['POST'])
@login_required
def respond_to_counter(offer_id):
    """Provider responds to client's counter-offer: accept or revise."""
    if current_user.role != 'provider':
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    try:
        data = request.get_json() or {}
        action = data.get('action')  # 'accept_counter' or 'revise'

        offer = RequestOfferResponse.query.filter_by(
            id=offer_id, provider_id=current_user.id
        ).first()
        if not offer or offer.status != 'pending':
            return jsonify({'success': False, 'message': 'Offer not found'}), 404

        if action == 'accept_counter':
            if offer.counter_price is None:
                return jsonify({'success': False, 'message': 'No counter to accept'}), 400
            offer.proposed_price = offer.counter_price
            offer.counter_price = None
            offer.last_action_by = 'provider'
            db.session.commit()
            return jsonify({'success': True, 'message': 'Counter accepted'})

        elif action == 'revise':
            new_price = data.get('price')
            try:
                new_price = float(new_price)
                if new_price < 0:
                    raise ValueError
            except (ValueError, TypeError):
                return jsonify({'success': False, 'message': 'Invalid price'}), 400
            offer.proposed_price = new_price
            offer.counter_price = None
            offer.last_action_by = 'provider'
            db.session.commit()
            return jsonify({'success': True, 'message': 'Price revised'})
        else:
            return jsonify({'success': False, 'message': 'Invalid action'}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


@provider_bp.route('/provider_get_accepted_requests', methods=['GET'])
@login_required
def provider_get_accepted_requests():
    if current_user.role != 'provider':
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    try:
        # All offers this provider sent, joined with the request
        my_offers = RequestOfferResponse.query.filter_by(
            provider_id=current_user.id
        ).order_by(RequestOfferResponse.created_at.desc()).all()

        result = []
        for offer in my_offers:
            req = offer.appointment_requests  # backref on ClientSelfCreatedAppointment
            if not req:
                continue
            # Show address only when client accepted this provider's offer
            show_address = (offer.status == 'accepted')
            result.append({
                'id': req.id,
                'offer_id': offer.id,
                'offer_status': offer.status,   # pending | accepted | rejected
                'patient_name': req.patient.full_name if req.patient else '',
                'service_name': req.service_name,
                'status': req.status,
                'appointment_start_time': req.appointment_start_time.isoformat(),
                'created_appo': req.created_appo.isoformat(),
                'latitude': req.latitude if show_address else None,
                'longitude': req.longitude if show_address else None,
                'address': req.address if show_address else None,
                'notes': req.notes,
                'payment': offer.proposed_price,
                'counter_price': offer.counter_price,
                'last_action_by': offer.last_action_by,
                'client_budget': req.payment,
                'req_status': req.status,
                'req_id': req.id,
            })

        return jsonify({'success': True, 'requests': result}), 200

    except Exception as e:
        current_app.logger.error(f"Error retrieving accepted requests: {str(e)}")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


def send_service_receipt_email(client, provider, service_name, amount, currency, service_date, service_time, receipt_number):
    """Send a formal service receipt email for insurance/tax reimbursement."""
    flask_app = current_app._get_current_object()
    client_name = client.full_name or client.user_name
    provider_name = provider.full_name or provider.user_name

    msg = MailMessage(
        subject=f"Service Receipt #{receipt_number}",
        sender=os.getenv('MAIL_DEFAULT_SENDER'),
        recipients=[client.email]
    )
    msg.html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
        <div style="text-align:center;margin-bottom:30px;">
            <h2 style="color:#3f4a36;margin:0;">Service Receipt</h2>
            <p style="color:#6b7280;margin:5px 0;">Receipt #{receipt_number}</p>
        </div>

        <div style="background:#f9fafb;border-radius:12px;padding:20px;margin-bottom:20px;">
            <table style="width:100%;border-collapse:collapse;">
                <tr>
                    <td style="padding:8px 0;color:#6b7280;width:40%;">Client:</td>
                    <td style="padding:8px 0;font-weight:600;">{client_name}</td>
                </tr>
                <tr>
                    <td style="padding:8px 0;color:#6b7280;">Service Provider:</td>
                    <td style="padding:8px 0;font-weight:600;">{provider_name}</td>
                </tr>
                <tr>
                    <td style="padding:8px 0;color:#6b7280;">Service:</td>
                    <td style="padding:8px 0;font-weight:600;">{service_name}</td>
                </tr>
                <tr>
                    <td style="padding:8px 0;color:#6b7280;">Date:</td>
                    <td style="padding:8px 0;font-weight:600;">{service_date}</td>
                </tr>
                <tr>
                    <td style="padding:8px 0;color:#6b7280;">Time:</td>
                    <td style="padding:8px 0;font-weight:600;">{service_time}</td>
                </tr>
            </table>
        </div>

        <div style="background:#3f4a36;color:#fff;border-radius:12px;padding:20px;text-align:center;margin-bottom:20px;">
            <p style="margin:0;font-size:14px;opacity:0.8;">Amount Paid</p>
            <p style="margin:5px 0;font-size:28px;font-weight:700;">{amount:.2f} {currency}</p>
        </div>

        <p style="color:#6b7280;font-size:13px;text-align:center;">
            This receipt can be used for insurance reimbursement (Krankenkasse) or tax deduction purposes.
            <br>Generated on {datetime.now().strftime('%d.%m.%Y %H:%M')}
        </p>

        <hr style="border:none;border-top:1px solid #e5e7eb;margin:20px 0;">
        <p style="color:#9ca3af;font-size:12px;text-align:center;">Human-me Platform</p>
    </div>
    """

    def _send(app, m):
        with app.app_context():
            try:
                mail.send(m)
            except Exception as e:
                app.logger.error(f"Receipt email error: {str(e)}")

    Thread(target=_send, args=(flask_app, msg)).start()


@provider_bp.route('/complete_request/<int:request_id>', methods=['POST'])
@login_required
def complete_request(request_id):
    """Provider marks service as done → capture payment + transfer to provider."""
    if current_user.role != 'provider':
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    try:
        req = ClientSelfCreatedAppointment.query.filter_by(
            id=request_id, provider_id=current_user.id
        ).first()

        if not req:
            return jsonify({'success': False, 'message': 'Request not found'}), 404

        is_free = (req.payment or 0) == 0

        if is_free:
            # Free service — no payment needed, just mark complete
            if req.status not in ('accepted', 'authorized'):
                return jsonify({'success': False, 'message': 'Request not in valid state'}), 400

            req.status = 'completed'
            db.session.commit()

            # Send receipt email for free service
            try:
                client = User.query.get(req.patient_id)
                if client and client.email:
                    send_service_receipt_email(
                        client=client,
                        provider=current_user,
                        service_name=req.service_name or 'Service',
                        amount=0,
                        currency='EUR',
                        service_date=req.appointment_start_time.strftime('%d.%m.%Y'),
                        service_time=req.appointment_start_time.strftime('%H:%M'),
                        receipt_number=f"REQ-{request_id}"
                    )
            except Exception as e:
                current_app.logger.error(f"Receipt email error: {str(e)}")

            return jsonify({'success': True})

        # Paid service — must be authorized first
        if req.status != 'authorized':
            return jsonify({'success': False, 'message': 'Payment not yet authorized by client'}), 400

        if not req.payment_intent_id:
            return jsonify({'success': False, 'message': 'No payment intent found'}), 400

        if not current_user.stripe_account_id:
            return jsonify({'success': False, 'message': 'Provider Stripe account not connected'}), 400

        # 1. Capture the authorized payment
        pi = stripe.PaymentIntent.capture(req.payment_intent_id)
        amount_cents = pi.amount_received
        platform_fee_cents = int(round(amount_cents * 0.10))
        payout_cents = amount_cents - platform_fee_cents

        # 2. Transfer to provider minus platform fee
        stripe.Transfer.create(
            amount=payout_cents,
            currency='eur',
            destination=current_user.stripe_account_id,
            transfer_group=f"req_{request_id}",
            metadata={'request_id': str(request_id)},
            idempotency_key=f"complete_req_{request_id}",
        )

        req.status = 'completed'
        db.session.commit()

        # Send receipt email to client
        try:
            client = User.query.get(req.patient_id)
            if client and client.email:
                send_service_receipt_email(
                    client=client,
                    provider=current_user,
                    service_name=req.service_name or 'Service',
                    amount=float(amount_cents) / 100,
                    currency='EUR',
                    service_date=req.appointment_start_time.strftime('%d.%m.%Y'),
                    service_time=req.appointment_start_time.strftime('%H:%M'),
                    receipt_number=f"REQ-{request_id}"
                )
        except Exception as e:
            current_app.logger.error(f"Receipt email error: {str(e)}")

        return jsonify({'success': True})

    except stripe.StripeError as e:
        current_app.logger.error(f"Stripe error completing request {request_id}: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error completing request {request_id}: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'}), 500


@provider_bp.route('/cancel_accepted_request/<int:request_id>', methods=['POST'])
@login_required
def provider_cancel_request(request_id):
    """Provider cancels → void PaymentIntent (0 fee if authorized) + free client."""
    if current_user.role != 'provider':
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    try:
        req = ClientSelfCreatedAppointment.query.filter_by(
            id=request_id, provider_id=current_user.id
        ).first()

        if not req or req.status not in ('accepted', 'authorized'):
            return jsonify({'success': False, 'message': 'Cannot cancel at this stage'}), 400

        if req.payment_intent_id and req.status == 'authorized':
            stripe.PaymentIntent.cancel(req.payment_intent_id)

        req.status = 'cancelled'
        db.session.commit()
        return jsonify({'success': True})

    except stripe.StripeError as e:
        current_app.logger.error(f"Stripe error cancelling request {request_id}: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Internal server error'}), 500
