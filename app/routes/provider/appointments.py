from . import provider_bp
from flask import Blueprint, jsonify, request, current_app, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models import User, Message, db, Service, ProviderService, Appointment, ClientSelfCreatedAppointment, RequestOfferResponse, ServiceHistory, CancellationPolicy, NoShowRecord, Dispute
from app.utils import fuzz_coordinates, haversine_distance, validate_coordinates
from datetime import datetime, timedelta
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
        'confirmed': '#f59e0b',
        'confirmed_paid': 'green',
        'provider_confirmed': 'green',
        'in_progress': '#10b981',
        'work_submitted': '#0ea5e9',
        'completed': 'blue',
        'cancelled': 'red',
        'no_show': '#6b7280',
        'disputed': '#f97316',
    }
    return colors_dictionary.get(Status)


def _find_linked_request(appointment):
    """Find the ClientSelfCreatedAppointment linked to an Appointment.
    Uses ServiceHistory.request_id first, then direct field matching as fallback."""
    # Try via ServiceHistory
    sh = ServiceHistory.query.filter_by(
        provider_id=appointment.provider_id,
        client_id=appointment.client_id,
    ).filter(
        ServiceHistory.request_id.isnot(None)
    ).all()
    for s in sh:
        if s.appointment_time == appointment.appointment_time:
            req = ClientSelfCreatedAppointment.query.get(s.request_id)
            if req:
                return req
    # Fallback: direct field matching
    req = ClientSelfCreatedAppointment.query.filter_by(
        patient_id=appointment.client_id,
        provider_id=appointment.provider_id,
        appointment_start_time=appointment.appointment_time
    ).first()
    return req


def _find_linked_appointment(req):
    """Find the Appointment linked to a ClientSelfCreatedAppointment."""
    appt = Appointment.query.filter_by(
        provider_id=req.provider_id,
        client_id=req.patient_id,
        appointment_time=req.appointment_start_time
    ).first()
    return appt


def sync_appointment_request_status(appointment, new_status):
    """Sync Appointment status → linked Request. Only syncs meaningful statuses."""
    if new_status not in ('work_submitted', 'completed', 'cancelled', 'confirmed_paid', 'authorized', 'in_progress', 'no_show', 'disputed'):
        return
    req = _find_linked_request(appointment)
    if req:
        req.set_status(new_status)
        # Also sync ServiceHistory
        sh = ServiceHistory.query.filter_by(
            provider_id=appointment.provider_id,
            client_id=appointment.client_id,
            appointment_time=appointment.appointment_time
        ).first()
        if sh:
            sh.status = new_status


def sync_request_appointment_status(req, new_status):
    """Sync Request status → linked Appointment. Only syncs meaningful statuses."""
    if new_status not in ('work_submitted', 'completed', 'cancelled', 'confirmed_paid', 'authorized', 'in_progress', 'no_show', 'disputed'):
        return
    appt = _find_linked_appointment(req)
    if appt:
        appt.set_status(new_status)
        # Also sync ServiceHistory
        sh = ServiceHistory.query.filter_by(request_id=req.id).first()
        if sh:
            sh.status = new_status


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

        # Fallback: get service names from ServiceHistory when provider_service is None
        sh_lookup = {}
        for sh in ServiceHistory.query.filter_by(provider_id=current_user.id).all():
            sh_lookup[(sh.client_id, sh.appointment_time)] = sh.service_name

        result = []

        for app in appointments:
            if app.provider_service:
                service_name = app.provider_service.name
            else:
                service_name = sh_lookup.get((app.client_id, app.appointment_time)) or "Service"
            client_name = app.client.full_name or app.client.user_name
            result.append({
                'id': app.id,
                'title': f"{service_name} - {client_name}",
                'start': app.appointment_time.isoformat(),
                'end': app.end_time.isoformat(),
                'color': calendar_appointment_color(app.status),
                'extendedProps': {
                    'client_name': app.client.full_name or app.client.user_name,
                    'provider_name': app.provider.full_name or app.provider.user_name,
                    'service_name': service_name,
                    'price': app.provider_service.price if app.provider_service else 0,
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
            Appointment.status.in_(['confirmed', 'confirmed_paid', 'scheduled', 'work_submitted'])
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
        if appointment.status not in ('confirmed_paid', 'confirmed'):
            return jsonify({'success': False, 'message': 'Cannot submit work for unpaid appointment'}), 400

        # Allow work_submitted from 'confirmed' only if free or cash
        if appointment.status == 'confirmed':
            price = appointment.provider_service.price if appointment.provider_service else 0
            if price > 0:
                return jsonify({'success': False, 'message': 'Cannot submit work for unpaid appointment'}), 400

        appointment.set_status('work_submitted')
        sync_appointment_request_status(appointment, 'work_submitted')
        db.session.commit()

        try:
            from app.telegram.notifications import notify_status_change
            svc = appointment.provider_service.name if appointment.provider_service else 'Service'
            notify_status_change(appointment.client_id, svc, 'confirmed_paid', 'work_submitted')
        except Exception:
            pass

        return jsonify({'success': True, 'message': 'Work submitted! Waiting for client approval.'})

    # Logic: Provider Accepts/Declines
    elif new_status in ['confirmed', 'cancelled']:
        if new_status == 'confirmed':
            # If free service, skip payment step entirely
            price = appointment.provider_service.price if appointment.provider_service else 0
            if price == 0:
                appointment.set_status('confirmed_paid')
                db.session.commit()
                return jsonify({'success': True, 'status': 'confirmed_paid'})
        appointment.set_status(new_status)
        # Only sync cancelled to the linked request (confirmed is appointment-specific)
        if new_status == 'cancelled':
            sync_appointment_request_status(appointment, 'cancelled')
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
            # Skip requests without address — provider needs location info
            if not req.address or not req.address.strip():
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
                'patient_id': req.patient_id,
                'patient_name': req.patient.full_name if req.patient else "Client",
                'service_name': req.service_name,
                'service_tags': req.service_tags or '',
                'appointment_start_time': req.appointment_start_time.isoformat(),
                'lat': f_lat,          # розмиті координати для карти
                'lng': f_lng,
                'district': req.district or '',  # тільки район, не точна адреса
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
        req.set_status('has_offers')

        new_offer = RequestOfferResponse(request_id=req.id, provider_id=current_user.id, proposed_price=price)
        db.session.add(new_offer)
        db.session.commit()

        try:
            from app.telegram.notifications import notify_new_offer
            notify_new_offer(req, new_offer)
        except Exception:
            pass

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
                req.set_status('pending')

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
            # Show full address only when client accepted this provider's offer
            show_address = (offer.status == 'accepted')
            result.append({
                'id': req.id,
                'offer_id': offer.id,
                'offer_status': offer.status,   # pending | accepted | rejected
                'patient_id': req.patient_id,
                'patient_name': req.patient.full_name if req.patient else '',
                'service_name': req.service_name,
                'service_tags': req.service_tags or '',
                'status': req.status,
                'appointment_start_time': req.appointment_start_time.isoformat(),
                'created_appo': req.created_appo.isoformat(),
                'latitude': req.latitude if show_address else None,
                'longitude': req.longitude if show_address else None,
                'address': req.address if show_address else None,
                'district': req.district or '',  # district always visible
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
    """Provider marks service as done → work_submitted (client must approve to release payment)."""
    if current_user.role != 'provider':
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    try:
        req = ClientSelfCreatedAppointment.query.filter_by(
            id=request_id, provider_id=current_user.id
        ).first()

        if not req:
            return jsonify({'success': False, 'message': 'Request not found'}), 404

        if req.status not in ('accepted', 'authorized'):
            return jsonify({'success': False, 'message': 'Request not in valid state'}), 400

        req.set_status('work_submitted')
        sync_request_appointment_status(req, 'work_submitted')
        db.session.commit()

        # Notify client
        try:
            from app.telegram.notifications import notify_status_change
            notify_status_change(
                req.patient_id,
                req.service_name or 'Service',
                'authorized', 'work_submitted'
            )
        except Exception:
            pass

        return jsonify({'success': True, 'message': 'Work submitted! Waiting for client approval.'})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error completing request {request_id}: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'}), 500


@provider_bp.route('/receipt/<receipt_type>/<int:item_id>')
@login_required
def provider_view_receipt(receipt_type, item_id):
    """Render a print-friendly receipt page for provider."""
    if current_user.role != 'provider':
        return redirect(url_for('auth.login'))

    now = datetime.now()

    if receipt_type == 'appointment':
        a = Appointment.query.filter_by(id=item_id, provider_id=current_user.id).first_or_404()
        client = User.query.get(a.client_id)
        service = ProviderService.query.get(a.nurse_service_id) if a.nurse_service_id else None
        service_name = service.name if service and service.name else 'Service'
        price = service.price if service else 0
        return render_template('client/receipt.html',
            receipt_number=f"APPT-{a.id}",
            client_name=(client.full_name or client.user_name) if client else 'Unknown',
            provider_name=current_user.full_name or current_user.user_name,
            service_name=service_name,
            price=price,
            currency='EUR',
            service_date=a.appointment_time.strftime('%d.%m.%Y') if a.appointment_time else '',
            service_time=a.appointment_time.strftime('%H:%M') if a.appointment_time else '',
            status=a.status,
            now=now,
        )
    elif receipt_type == 'request':
        req = ClientSelfCreatedAppointment.query.filter_by(id=item_id, provider_id=current_user.id).first_or_404()
        client = User.query.get(req.patient_id)
        return render_template('client/receipt.html',
            receipt_number=f"REQ-{req.id}",
            client_name=(client.full_name or client.user_name) if client else 'Unknown',
            provider_name=current_user.full_name or current_user.user_name,
            service_name=req.service_name or 'Service',
            price=float(req.payment or 0),
            currency='EUR',
            service_date=req.appointment_start_time.strftime('%d.%m.%Y') if req.appointment_start_time else '',
            service_time=req.appointment_start_time.strftime('%H:%M') if req.appointment_start_time else '',
            status=req.status,
            now=now,
        )
    else:
        from flask import abort
        abort(404)


@provider_bp.route('/retract_work_submitted/<int:request_id>', methods=['POST'])
@login_required
def retract_work_submitted(request_id):
    """Provider retracts work_submitted → go back to previous status."""
    if current_user.role != 'provider':
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    try:
        req = ClientSelfCreatedAppointment.query.filter_by(
            id=request_id, provider_id=current_user.id
        ).first()

        if not req:
            return jsonify({'success': False, 'message': 'Request not found'}), 404

        if req.status != 'work_submitted':
            return jsonify({'success': False, 'message': 'Request is not in work_submitted state'}), 400

        restore_to = req.previous_status or 'authorized'
        req.set_status(restore_to)
        sync_request_appointment_status(req, restore_to)
        db.session.commit()

        return jsonify({'success': True, 'message': 'Work submission retracted'})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error retracting work submitted: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'}), 500


@provider_bp.route('/retract_work_appointment/<int:appointment_id>', methods=['POST'])
@login_required
def retract_work_appointment(appointment_id):
    """Provider retracts work_submitted on appointment → go back to previous status."""
    if current_user.role != 'provider':
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    try:
        appointment = Appointment.query.filter_by(
            id=appointment_id, provider_id=current_user.id
        ).first()

        if not appointment:
            return jsonify({'success': False, 'message': 'Appointment not found'}), 404

        if appointment.status != 'work_submitted':
            return jsonify({'success': False, 'message': 'Appointment is not in work_submitted state'}), 400

        restore_to = appointment.previous_status or 'confirmed_paid'
        appointment.set_status(restore_to)
        sync_appointment_request_status(appointment, restore_to)
        db.session.commit()

        return jsonify({'success': True, 'message': 'Work submission retracted'})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error retracting work submitted: {str(e)}")
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

        req.set_status('cancelled')
        sync_request_appointment_status(req, 'cancelled')
        db.session.commit()
        return jsonify({'success': True})

    except stripe.StripeError as e:
        current_app.logger.error(f"Stripe error cancelling request {request_id}: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Internal server error'}), 500


# ── Arrival & Lateness ──────────────────────────────────────────────────────

@provider_bp.route('/confirm_arrival', methods=['POST'])
@login_required
def confirm_arrival():
    """Provider confirms arrival at client location → status becomes in_progress."""
    if current_user.role != 'provider':
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    data = request.get_json() or {}
    appointment_id = data.get('appointment_id')
    request_id = data.get('request_id')

    try:
        if appointment_id:
            item = Appointment.query.filter_by(id=appointment_id, provider_id=current_user.id).first()
            if not item:
                return jsonify({'success': False, 'message': 'Appointment not found'}), 404
            if item.status not in ('confirmed_paid', 'confirmed'):
                return jsonify({'success': False, 'message': 'Cannot confirm arrival for this status'}), 400
            item.provider_arrived_at = datetime.now()
            item.set_status('in_progress')
            sync_appointment_request_status(item, 'in_progress')
            db.session.commit()
            # Notify client
            try:
                from app.telegram.notifications import notify_status_change
                svc = item.provider_service.name if item.provider_service else 'Service'
                notify_status_change(item.client_id, svc, 'confirmed_paid', 'in_progress')
            except Exception:
                pass
            return jsonify({'success': True, 'message': 'Arrival confirmed'})

        elif request_id:
            item = ClientSelfCreatedAppointment.query.filter_by(id=request_id, provider_id=current_user.id).first()
            if not item:
                return jsonify({'success': False, 'message': 'Request not found'}), 404
            if item.status not in ('authorized', 'confirmed_paid', 'accepted'):
                return jsonify({'success': False, 'message': 'Cannot confirm arrival for this status'}), 400
            item.provider_arrived_at = datetime.now()
            item.set_status('in_progress')
            sync_request_appointment_status(item, 'in_progress')
            db.session.commit()
            try:
                from app.telegram.notifications import notify_status_change
                notify_status_change(item.patient_id, item.service_name or 'Service', 'authorized', 'in_progress')
            except Exception:
                pass
            return jsonify({'success': True, 'message': 'Arrival confirmed'})

        return jsonify({'success': False, 'message': 'appointment_id or request_id required'}), 400

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error confirming arrival: {e}")
        return jsonify({'success': False, 'message': 'Internal server error'}), 500


@provider_bp.route('/report_late', methods=['POST'])
@login_required
def report_late():
    """Provider reports they are running late."""
    if current_user.role != 'provider':
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    data = request.get_json() or {}
    appointment_id = data.get('appointment_id')
    request_id = data.get('request_id')
    delay_minutes = data.get('delay_minutes')

    try:
        delay_minutes = int(delay_minutes)
        if delay_minutes < 1:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'Valid delay_minutes required'}), 400

    try:
        if appointment_id:
            item = Appointment.query.filter_by(id=appointment_id, provider_id=current_user.id).first()
            if not item:
                return jsonify({'success': False, 'message': 'Appointment not found'}), 404
            item.provider_late_minutes = delay_minutes
            db.session.commit()
            try:
                from app.telegram.notifications import send_user_telegram
                svc = item.provider_service.name if item.provider_service else 'Service'
                send_user_telegram(item.client_id,
                    f"Your provider is running ~{delay_minutes} min late for '{svc}'.")
            except Exception:
                pass
            return jsonify({'success': True, 'message': f'Reported {delay_minutes} min late'})

        elif request_id:
            item = ClientSelfCreatedAppointment.query.filter_by(id=request_id, provider_id=current_user.id).first()
            if not item:
                return jsonify({'success': False, 'message': 'Request not found'}), 404
            item.provider_late_minutes = delay_minutes
            db.session.commit()
            try:
                from app.telegram.notifications import send_user_telegram
                send_user_telegram(item.patient_id,
                    f"Your provider is running ~{delay_minutes} min late for '{item.service_name or 'Service'}'.")
            except Exception:
                pass
            return jsonify({'success': True, 'message': f'Reported {delay_minutes} min late'})

        return jsonify({'success': False, 'message': 'appointment_id or request_id required'}), 400

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error reporting late: {e}")
        return jsonify({'success': False, 'message': 'Internal server error'}), 500


# ── No-Show ──────────────────────────────────────────────────────────────────

@provider_bp.route('/report_no_show', methods=['POST'])
@login_required
def report_no_show():
    """Provider reports client no-show → charge based on cancellation policy."""
    if current_user.role != 'provider':
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    data = request.get_json() or {}
    appointment_id = data.get('appointment_id')
    request_id = data.get('request_id')
    reason = data.get('reason', '')

    try:
        from app.models import NoShowRecord

        if appointment_id:
            item = Appointment.query.filter_by(id=appointment_id, provider_id=current_user.id).first()
            if not item:
                return jsonify({'success': False, 'message': 'Appointment not found'}), 404
            if item.status not in ('confirmed_paid', 'confirmed', 'in_progress'):
                return jsonify({'success': False, 'message': 'Cannot report no-show for this status'}), 400

            # Check 15 min past appointment time
            now = datetime.now()
            if now < item.appointment_time + timedelta(minutes=15):
                return jsonify({'success': False, 'message': 'Must wait 15 minutes after appointment time'}), 400

            # Get policy
            policy = CancellationPolicy.query.filter_by(provider_id=current_user.id).first()
            fee_percent = policy.no_show_client_fee_percent if policy else 100

            # Stripe: capture fee from authorized payment
            if item.status == 'confirmed_paid':
                from app.models import Payment
                payment = Payment.query.filter_by(appointment_id=item.id, status='completed').first()
                if payment and payment.transaction_id:
                    if fee_percent >= 100:
                        pi = stripe.PaymentIntent.capture(payment.transaction_id)
                        # Transfer to provider (minus commission)
                        amount_cents = pi.amount_received
                        commission_rate = current_app.config.get('PLATFORM_COMMISSION_RATE', 0.15)
                        platform_fee = int(round(amount_cents * commission_rate))
                        payout = amount_cents - platform_fee
                        if current_user.stripe_account_id:
                            stripe.Transfer.create(
                                amount=payout, currency='eur',
                                destination=current_user.stripe_account_id,
                                transfer_group=f"noshow_appt_{item.id}",
                            )
                    elif fee_percent > 0:
                        fee_cents = int(payment.amount_cents * fee_percent / 100)
                        stripe.PaymentIntent.capture(payment.transaction_id, amount_to_capture=fee_cents)
                    else:
                        stripe.PaymentIntent.cancel(payment.transaction_id)

            # Record no-show
            client = User.query.get(item.client_id)
            record = NoShowRecord(
                appointment_id=item.id, reported_by_id=current_user.id,
                no_show_user_id=item.client_id, role='client', reason=reason,
            )
            db.session.add(record)
            if client:
                client.no_show_count = (client.no_show_count or 0) + 1
            item.set_status('no_show')
            sync_appointment_request_status(item, 'no_show')
            db.session.commit()
            return jsonify({'success': True, 'message': 'Client no-show recorded'})

        elif request_id:
            item = ClientSelfCreatedAppointment.query.filter_by(id=request_id, provider_id=current_user.id).first()
            if not item:
                return jsonify({'success': False, 'message': 'Request not found'}), 404
            if item.status not in ('authorized', 'confirmed_paid', 'accepted', 'in_progress'):
                return jsonify({'success': False, 'message': 'Cannot report no-show for this status'}), 400

            now = datetime.now()
            if now < item.appointment_start_time + timedelta(minutes=15):
                return jsonify({'success': False, 'message': 'Must wait 15 minutes after appointment time'}), 400

            policy = CancellationPolicy.query.filter_by(provider_id=current_user.id).first()
            fee_percent = policy.no_show_client_fee_percent if policy else 100

            if item.payment_intent_id and item.status == 'authorized':
                if fee_percent >= 100:
                    pi = stripe.PaymentIntent.capture(item.payment_intent_id)
                    amount_cents = pi.amount_received
                    commission_rate = current_app.config.get('PLATFORM_COMMISSION_RATE', 0.15)
                    platform_fee = int(round(amount_cents * commission_rate))
                    payout = amount_cents - platform_fee
                    if current_user.stripe_account_id:
                        stripe.Transfer.create(
                            amount=payout, currency='eur',
                            destination=current_user.stripe_account_id,
                            transfer_group=f"noshow_req_{item.id}",
                        )
                elif fee_percent > 0:
                    fee_cents = int(int(item.payment * 100) * fee_percent / 100)
                    stripe.PaymentIntent.capture(item.payment_intent_id, amount_to_capture=fee_cents)
                else:
                    stripe.PaymentIntent.cancel(item.payment_intent_id)

            client = User.query.get(item.patient_id)
            record = NoShowRecord(
                request_id=item.id, reported_by_id=current_user.id,
                no_show_user_id=item.patient_id, role='client', reason=reason,
            )
            db.session.add(record)
            if client:
                client.no_show_count = (client.no_show_count or 0) + 1
            item.set_status('no_show')
            sync_request_appointment_status(item, 'no_show')
            db.session.commit()
            return jsonify({'success': True, 'message': 'Client no-show recorded'})

        return jsonify({'success': False, 'message': 'appointment_id or request_id required'}), 400

    except stripe.StripeError as e:
        current_app.logger.error(f"Stripe error on no-show: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error reporting no-show: {e}")
        return jsonify({'success': False, 'message': 'Internal server error'}), 500


# ── Cancellation Policy Summary ─────────────────────────────────────────────

@provider_bp.route('/cancellation_policy_summary', methods=['GET'])
@login_required
def cancellation_policy_summary():
    """Return provider's current cancellation policy for display."""
    if current_user.role != 'provider':
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    policy = CancellationPolicy.query.filter_by(provider_id=current_user.id).first()
    if not policy:
        return jsonify({
            'success': True,
            'has_policy': False,
            'free_cancel_hours': 24,
            'late_cancel_fee_percent': 25,
            'no_show_client_fee_percent': 100,
        })

    return jsonify({
        'success': True,
        'has_policy': True,
        'free_cancel_hours': policy.free_cancel_hours,
        'late_cancel_fee_percent': policy.late_cancel_fee_percent,
        'no_show_client_fee_percent': policy.no_show_client_fee_percent,
    })
