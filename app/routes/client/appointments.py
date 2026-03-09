from . import client_bp
from flask import render_template, redirect, url_for, flash, request, abort, jsonify, current_app, Blueprint
from sqlalchemy.sql.sqltypes import DateTime
from app.extensions import db, bcrypt, socketio, mail
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
        'pending': '#9ca3af',
        'has_offers': '#8b5cf6',
        'accepted': '#f59e0b',
        'authorized': '#3b82f6',
        'request_sended': '#f59e0b',
        'confirmed': '#f59e0b',
        'confirmed_paid': 'green',
        'provider_confirmed': 'green',
        'in_progress': '#16a34a',
        'work_submitted': '#0ea5e9',
        'completed': '#2563eb',
        'cancelled': 'red',
        'no_show': '#6b7280',
        'disputed': '#f97316',
    }
    return colors.get(status, 'gray')


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

        # Pre-fetch service names and prices from ServiceHistory for appointments without provider_service
        sh_records = ServiceHistory.query.filter_by(client_id=current_user.id).all()
        sh_lookup = {}
        for sh in sh_records:
            sh_lookup[(sh.provider_id, sh.appointment_time)] = {'name': sh.service_name, 'price': sh.price}

        result = []
        for app in appointments:
            sh_info = sh_lookup.get((app.provider_id, app.appointment_time))
            if app.provider_service:
                service_name = app.provider_service.name
                amount = app.provider_service.price
            elif sh_info:
                service_name = sh_info['name'] or "Service"
                amount = sh_info['price'] or 0
            else:
                service_name = "Service"
                amount = 0
            provider_name = app.provider.user_name if app.provider else "Provider"

            result.append({
                'id': app.id,
                'title': f"{service_name} - {provider_name}",
                'start': app.appointment_time.isoformat(),
                'end': app.end_time.isoformat(),
                'color': get_appointment_color(app.status),
                'extendedProps': {
                    'type': 'appointment',
                    'status': app.status,
                    'notes': app.notes or '',
                    'provider_name': provider_name,
                    'service_name': service_name,
                    'amount': f"{amount:.2f}"
                }
            })

        # Also include client requests (ClientSelfCreatedAppointment)
        req_query = ClientSelfCreatedAppointment.query.filter_by(patient_id=current_user.id)
        if start_date and end_date:
            try:
                req_query = req_query.filter(
                    ClientSelfCreatedAppointment.appointment_start_time >= start,
                    ClientSelfCreatedAppointment.appointment_start_time <= end
                )
            except Exception:
                pass
        requests_list = req_query.order_by(ClientSelfCreatedAppointment.appointment_start_time.asc()).all()

        for r in requests_list:
            provider_name = ''
            if r.provider_id:
                prov = User.query.get(r.provider_id)
                provider_name = (prov.full_name or prov.user_name) if prov else ''
            svc_name = r.service_name or 'Request'
            title = f"{svc_name} - {provider_name}" if provider_name else svc_name
            amount = float(r.payment or 0)

            end_time = r.end_time or (r.appointment_start_time + timedelta(hours=1))

            result.append({
                'id': f"req_{r.id}",
                'title': title,
                'start': r.appointment_start_time.isoformat(),
                'end': end_time.isoformat(),
                'color': get_appointment_color(r.status),
                'extendedProps': {
                    'type': 'request',
                    'request_id': r.id,
                    'status': r.status,
                    'notes': r.notes or '',
                    'provider_name': provider_name,
                    'service_name': svc_name,
                    'amount': f"{amount:.2f}"
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

    # Progressive verification: require profile basics before first booking
    if not current_user.full_name:
        return jsonify({'success': False, 'message': 'Please add your full name in your profile before booking.', 'redirect': url_for('client.profile')}), 400
    if not current_user.is_contact_verified:
        return jsonify({'success': False, 'message': 'Please verify your email or link Telegram before booking.', 'redirect': url_for('client.profile')}), 400

    try:
        data = request.get_json()
        provider_id = data.get('provider_id')
        service_id = data.get('service_id')
        date_time = data.get('date_time')
        notes = data.get('notes')

        if not all([provider_id, service_id, date_time]):
            return jsonify({'success': False, 'message': 'All fields must be filled'}), 400

        provider = User.query.get(provider_id)
        if not provider or provider.role != 'provider':
            return jsonify({'success': False, 'message': 'Service provider not found'}), 404

        service = ProviderService.query.get(service_id)
        if not service or service.provider_id != int(provider_id):
            return jsonify({'success': False, 'message': 'Service not found'}), 404

        appointment_time = datetime.strptime(date_time, '%Y-%m-%dT%H:%M')
        end_time = appointment_time + timedelta(minutes=service.duration)

        active_statuses = ('scheduled', 'confirmed', 'confirmed_paid', 'in_progress', 'authorized')
        conflicting_appointments = Appointment.query.filter(
            Appointment.provider_id == provider_id,
            Appointment.status.in_(active_statuses),
            ((Appointment.appointment_time <= appointment_time) & (Appointment.end_time > appointment_time)) |
            ((Appointment.appointment_time < end_time) & (Appointment.end_time >= end_time)) |
            ((Appointment.appointment_time >= appointment_time) & (Appointment.end_time <= end_time))
        ).count()

        if conflicting_appointments > 0:
            return jsonify({'success': False, 'message': 'This time is already taken'}), 400

        new_appointment = Appointment(
            client_id=current_user.id,
            provider_id=provider_id,
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
        return jsonify({'success': False, 'message': 'Internal server error'}), 500



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

        # 3-tier cancellation policy
        policy = CancellationPolicy.query.filter_by(provider_id=appointment.provider_id).first()
        free_hours = policy.free_cancel_hours if policy and policy.free_cancel_hours is not None else 24
        late_fee = policy.late_cancel_fee_percent if policy else 25

        if hours_until >= free_hours:
            fee_percent = 0                          # Tier 1: free cancellation
        elif hours_until >= 2:
            fee_percent = late_fee                    # Tier 2: late cancel fee (default 25%)
        else:
            fee_percent = min(late_fee * 2, 100)      # Tier 3: very late (<2h), double fee capped at 100%

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

        appointment.set_status('cancelled')

        # Sync linked request + service history
        from app.routes.provider.appointments import sync_appointment_request_status
        sync_appointment_request_status(appointment, 'cancelled')

        db.session.commit()

        msg = 'Appointment cancelled'
        if fee_percent > 0:
            msg = f'Appointment cancelled. Cancellation fee: {fee_percent}% per provider policy.'

        return jsonify({'success': True, 'message': msg, 'fee_percent': fee_percent})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error cancelling appointment: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'}), 500


@client_bp.route('/client_self_create_appointment', methods=['POST'])
@login_required
def client_self_create_appointment():
    if current_user.role != 'client':
        return jsonify({'success': False, 'message': 'access denied'}), 403

    # Progressive verification: require profile basics before posting a request
    if not current_user.full_name:
        return jsonify({'success': False, 'error': 'Please add your full name in your profile before creating a request.', 'redirect': url_for('client.profile')}), 400
    if not current_user.is_contact_verified:
        return jsonify({'success': False, 'error': 'Please verify your email or link Telegram before creating a request.', 'redirect': url_for('client.profile')}), 400

    try:
        data = request.get_json()

        if not data.get('appointment_start_time'):
            return jsonify({'success': False, 'error': 'Time is required'}), 400

        if not data.get('address', '').strip():
            return jsonify({'success': False, 'error': 'Address is required'}), 400

        if not data.get('district', '').strip():
            return jsonify({'success': False, 'error': 'District / neighborhood is required'}), 400

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
            district=data['district'].strip(),
            service_tags=data.get('service_tags', ''),
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
                        'counter_price': offer.counter_price,
                        'last_action_by': offer.last_action_by,
                        'is_verified': p.is_verified if p else False,
                    })

            # For accepted requests, include the accepted provider info
            accepted_provider = None
            if req.status in ('accepted', 'authorized', 'work_submitted', 'completed', 'confirmed_paid') and req.provider:
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
                'address': req.address,
                'district': req.district,
                'service_tags': req.service_tags,
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
        req = ClientSelfCreatedAppointment.query.filter_by(
            id=request_id,
            patient_id=current_user.id
        ).first()

        if not req:
            return jsonify({'success': False, 'message': 'Request not found'}), 404

        cancellable = ['pending', 'has_offers', 'accepted', 'authorized']
        if req.status not in cancellable:
            return jsonify({'success': False, 'message': 'Cannot cancel this request'}), 400

        # 3-tier cancellation fee for authorized payments
        if req.status == 'authorized' and req.payment_intent_id:
            try:
                now = datetime.now()
                hours_until = (req.appointment_start_time - now).total_seconds() / 3600
                policy = CancellationPolicy.query.filter_by(provider_id=req.provider_id).first() if req.provider_id else None
                free_hours = policy.free_cancel_hours if policy and policy.free_cancel_hours is not None else 24
                late_fee = policy.late_cancel_fee_percent if policy else 25

                if hours_until >= free_hours:
                    fee_percent = 0
                elif hours_until >= 2:
                    fee_percent = late_fee
                else:
                    fee_percent = min(late_fee * 2, 100)

                if fee_percent == 0:
                    stripe.PaymentIntent.cancel(req.payment_intent_id)
                else:
                    fee_cents = int(int((req.payment or 0) * 100) * fee_percent / 100)
                    if fee_cents > 0:
                        stripe.PaymentIntent.capture(req.payment_intent_id, amount_to_capture=fee_cents)
                    else:
                        stripe.PaymentIntent.cancel(req.payment_intent_id)
            except stripe.StripeError as e:
                current_app.logger.error(f'Stripe cancel error: {str(e)}')
                return jsonify({'success': False, 'message': 'Payment cancellation failed'}), 500

        # Reject all pending/accepted offers for this request
        RequestOfferResponse.query.filter(
            RequestOfferResponse.request_id == req.id,
            RequestOfferResponse.status.in_(['pending', 'accepted'])
        ).update({'status': 'rejected'}, synchronize_session=False)

        # Cancel associated Appointment if one was created
        if req.status in ('accepted', 'authorized', 'confirmed_paid', 'work_submitted') and req.provider_id:
            appt = Appointment.query.filter_by(
                client_id=current_user.id,
                provider_id=req.provider_id,
                appointment_time=req.appointment_start_time,
            ).filter(Appointment.status != 'cancelled').first()
            if appt:
                appt.set_status('cancelled')

        # Also sync ServiceHistory
        sh = ServiceHistory.query.filter_by(request_id=req.id).first()
        if sh:
            sh.status = 'cancelled'

        req.set_status('cancelled')
        db.session.commit()

        return jsonify({'success': True, 'message': 'Request cancelled'}), 200

    except Exception as e:
        current_app.logger.error(f"Error cancelling request: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


@client_bp.route('/undo_cancel_request/<int:request_id>', methods=['POST'])
@login_required
def undo_cancel_request(request_id):
    """Restore a cancelled request back to pending status."""
    if current_user.role != 'client':
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    try:
        req = ClientSelfCreatedAppointment.query.filter_by(
            id=request_id, patient_id=current_user.id
        ).first()

        if not req:
            return jsonify({'success': False, 'message': 'Request not found'}), 404

        if req.status != 'cancelled':
            return jsonify({'success': False, 'message': 'Request is not cancelled'}), 400

        # Check if appointment date hasn't passed
        if req.appointment_start_time and req.appointment_start_time < datetime.now():
            return jsonify({'success': False, 'message': 'Cannot restore — appointment date has passed'}), 400

        # Determine restore target
        restore_to = req.previous_status or 'pending'
        # If previous state involved payment that was cancelled, fall back to accepted
        if restore_to == 'authorized' and not req.payment_intent_id:
            restore_to = 'accepted'

        # Restore linked appointment if exists
        if req.provider_id:
            appt = Appointment.query.filter_by(
                client_id=current_user.id,
                provider_id=req.provider_id,
                appointment_time=req.appointment_start_time,
                status='cancelled'
            ).first()
            if appt:
                appt_restore = appt.previous_status or 'scheduled'
                appt.set_status(appt_restore)

        # Sync ServiceHistory
        sh = ServiceHistory.query.filter_by(request_id=req.id).first()
        if sh:
            sh.status = restore_to

        req.set_status(restore_to)

        db.session.commit()
        return jsonify({'success': True, 'message': 'Request restored successfully'})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error restoring request {request_id}: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'}), 500


@client_bp.route('/undo_cancel_appointment/<int:appointment_id>', methods=['POST'])
@login_required
def undo_cancel_appointment(appointment_id):
    """Restore a cancelled appointment back to scheduled status."""
    if current_user.role != 'client':
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    try:
        appointment = Appointment.query.filter_by(
            id=appointment_id, client_id=current_user.id
        ).first()

        if not appointment:
            return jsonify({'success': False, 'message': 'Appointment not found'}), 404

        if appointment.status != 'cancelled':
            return jsonify({'success': False, 'message': 'Appointment is not cancelled'}), 400

        if appointment.appointment_time < datetime.now():
            return jsonify({'success': False, 'message': 'Cannot restore — appointment date has passed'}), 400

        restore_to = appointment.previous_status or 'scheduled'
        appointment.set_status(restore_to)

        # Sync linked request
        from app.routes.provider.appointments import _find_linked_request
        linked_req = _find_linked_request(appointment)
        if linked_req and linked_req.status == 'cancelled':
            req_restore = linked_req.previous_status or 'pending'
            linked_req.set_status(req_restore)

        # Sync ServiceHistory
        sh = ServiceHistory.query.filter_by(
            provider_id=appointment.provider_id,
            client_id=current_user.id,
            appointment_time=appointment.appointment_time
        ).first()
        if sh:
            sh.status = restore_to

        db.session.commit()
        return jsonify({'success': True, 'message': 'Appointment restored successfully'})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error restoring appointment {appointment_id}: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'}), 500


@client_bp.route('/undo_step/<int:request_id>', methods=['POST'])
@login_required
def undo_step(request_id):
    """Client goes back one step on a request (e.g. un-accept, retract authorization)."""
    if current_user.role != 'client':
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    try:
        req = ClientSelfCreatedAppointment.query.filter_by(
            id=request_id, patient_id=current_user.id
        ).first()

        if not req:
            return jsonify({'success': False, 'message': 'Request not found'}), 404

        if not req.previous_status:
            return jsonify({'success': False, 'message': 'Cannot go back further'}), 400

        # Don't allow going back from completed
        if req.status == 'completed':
            return jsonify({'success': False, 'message': 'Cannot undo completed service'}), 400

        restore_to = req.previous_status

        # If going back from accepted → restore rejected offers
        if req.status == 'accepted' and restore_to in ('pending', 'has_offers'):
            # Reject the accepted offer
            RequestOfferResponse.query.filter(
                RequestOfferResponse.request_id == req.id,
                RequestOfferResponse.status == 'accepted'
            ).update({'status': 'rejected'}, synchronize_session=False)

            # Cancel linked appointment and sync
            if req.provider_id:
                appt = Appointment.query.filter_by(
                    client_id=current_user.id,
                    provider_id=req.provider_id,
                    appointment_time=req.appointment_start_time,
                ).filter(Appointment.status != 'cancelled').first()
                if appt:
                    appt.set_status('cancelled')

            req.provider_id = None

        # If going back from authorized → cancel Stripe hold
        if req.status == 'authorized' and req.payment_intent_id:
            try:
                stripe.PaymentIntent.cancel(req.payment_intent_id)
            except stripe.StripeError as e:
                current_app.logger.error(f'Stripe cancel error: {str(e)}')
            req.payment_intent_id = None

        # If going back from work_submitted or authorized → sync linked appointment
        if req.status in ('work_submitted', 'authorized'):
            from app.routes.provider.appointments import sync_request_appointment_status
            sync_request_appointment_status(req, restore_to)

        req.set_status(restore_to)

        # Sync ServiceHistory
        sh = ServiceHistory.query.filter_by(request_id=req.id).first()
        if sh:
            sh.status = restore_to

        db.session.commit()
        return jsonify({'success': True, 'message': 'Returned to previous step'})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error undoing step: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'}), 500


@client_bp.route('/client_accept_request/<int:offer_id>/', methods=['POST'])
@login_required
def client_accept_request(offer_id):
    if current_user.role != 'client':
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    try:
        provider_offer = RequestOfferResponse.query.get(offer_id)

        if not provider_offer or provider_offer.status != 'pending':
            return jsonify({'success': False, 'message': 'Offer not found or already processed'}), 404

        req = ClientSelfCreatedAppointment.query.get(provider_offer.request_id)

        if not req:
            return jsonify({'success': False, 'message': 'Request not found'}), 404

        if req.patient_id != current_user.id:
            return jsonify({'success': False, 'message': 'Access denied'}), 403

        if req.status not in ('pending', 'has_offers'):
            return jsonify({'success': False, 'message': 'Request already accepted'}), 400

        # Safe price — handle NULL proposed_price
        offer_price = float(provider_offer.proposed_price) if provider_offer.proposed_price is not None else 0.0

        provider_offer.status = 'accepted'
        req.set_status('accepted')
        req.provider_id = provider_offer.provider_id
        req.payment = offer_price

        # Reject all other pending offers for this request
        RequestOfferResponse.query.filter(
            RequestOfferResponse.request_id == req.id,
            RequestOfferResponse.id != provider_offer.id,
            RequestOfferResponse.status == 'pending'
        ).update({'status': 'rejected'}, synchronize_session=False)

        # Create Appointment
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
        db.session.flush()

        # Create ServiceHistory
        service_history = ServiceHistory(
            provider_id=provider_offer.provider_id,
            client_id=current_user.id,
            request_id=req.id,
            service_name=req.service_name,
            service_description=req.service_description,
            price=offer_price,
            appointment_time=req.appointment_start_time,
            end_time=req.end_time,
            status='scheduled'
        )
        db.session.add(service_history)
        db.session.commit()

        try:
            from app.telegram.notifications import notify_offer_accepted
            notify_offer_accepted(provider_offer)
        except Exception:
            pass

        return jsonify({'success': True, 'message': 'Offer accepted', 'appointment_id': appointment.id}), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error accepting offer {offer_id}: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


@client_bp.route('/counter_offer/<int:offer_id>', methods=['POST'])
@login_required
def counter_offer(offer_id):
    """Client sends a counter-offer price."""
    if current_user.role != 'client':
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    try:
        data = request.get_json() or {}
        counter_price = data.get('counter_price')
        try:
            counter_price = float(counter_price)
            if counter_price < 0:
                return jsonify({'success': False, 'message': 'Price must be positive'}), 400
        except (ValueError, TypeError):
            return jsonify({'success': False, 'message': 'Invalid price'}), 400

        offer = RequestOfferResponse.query.get(offer_id)
        if not offer or offer.status != 'pending':
            return jsonify({'success': False, 'message': 'Offer not found'}), 404

        req = ClientSelfCreatedAppointment.query.get(offer.request_id)
        if not req or req.patient_id != current_user.id:
            return jsonify({'success': False, 'message': 'Access denied'}), 403

        offer.counter_price = counter_price
        offer.last_action_by = 'client'
        db.session.commit()

        try:
            from app.telegram.notifications import notify_counter_offer
            notify_counter_offer(offer)
        except Exception:
            pass

        return jsonify({'success': True, 'message': 'Counter-offer sent'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error sending counter-offer: {str(e)}")
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
    if appo.status not in ('confirmed_paid', 'completed', 'work_submitted'):
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


@client_bp.route('/get_reviews/<int:provider_id>')
@login_required
def get_reviews(provider_id):
    reviews = Review.query.filter_by(provider_id=provider_id).order_by(
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

    if appointment.status not in ('confirmed_paid', 'completed', 'work_submitted'):
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


@client_bp.route('/complete_appointment', methods=['POST'])
@login_required
def complete_appointment():
    """Client approves work_submitted → capture payment → transfer to provider → completed."""
    if current_user.role != 'client':
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    try:
        data = request.get_json()
        appointment_id = data.get('appointment_id')
        if not appointment_id:
            return jsonify({'success': False, 'message': 'Appointment ID required'}), 400

        appointment = Appointment.query.filter_by(
            id=appointment_id, client_id=current_user.id
        ).first()
        if not appointment:
            return jsonify({'success': False, 'message': 'Appointment not found'}), 404

        if appointment.status != 'work_submitted':
            return jsonify({'success': False, 'message': 'Appointment is not in work_submitted state'}), 400

        provider = User.query.get(appointment.provider_id)
        service = ProviderService.query.get(appointment.nurse_service_id) if appointment.nurse_service_id else None
        service_name = 'Service'
        if service:
            service_name = service.name if service.name else (service.base_service.name if service.base_service else 'Service')
        price = service.price if service else 0

        # Handle paid appointment — capture Stripe payment
        if price > 0:
            payment = Payment.query.filter_by(
                appointment_id=appointment.id, status='completed'
            ).first()

            if payment and payment.transaction_id:
                if not provider or not provider.stripe_account_id:
                    return jsonify({'success': False, 'message': 'Provider Stripe account not connected'}), 400

                pi = stripe.PaymentIntent.capture(
                    payment.transaction_id,
                    idempotency_key=f"complete_appt_{appointment_id}",
                )
                amount_cents = pi.amount_received
                commission_rate = current_app.config.get('PLATFORM_COMMISSION_RATE', 0.15)
                platform_fee_cents = int(round(amount_cents * commission_rate))
                payout_cents = amount_cents - platform_fee_cents

                stripe.Transfer.create(
                    amount=payout_cents,
                    currency='eur',
                    destination=provider.stripe_account_id,
                    transfer_group=f"appt_{appointment_id}",
                    metadata={'appointment_id': str(appointment_id)},
                    idempotency_key=f"transfer_appt_{appointment_id}",
                )

                payment.status = 'paid'
                payment.platform_fee_cents = platform_fee_cents
                payment.stripe_transfer_id = f"appt_{appointment_id}"

        appointment.set_status('completed')

        # Sync linked request + service history
        from app.routes.provider.appointments import sync_appointment_request_status
        sync_appointment_request_status(appointment, 'completed')

        db.session.commit()

        # Send receipt email
        try:
            from app.routes.provider.appointments import send_service_receipt_email
            send_service_receipt_email(
                client=current_user,
                provider=provider,
                service_name=service_name,
                amount=price,
                currency='EUR',
                service_date=appointment.appointment_time.strftime('%d.%m.%Y') if appointment.appointment_time else '',
                service_time=appointment.appointment_time.strftime('%H:%M') if appointment.appointment_time else '',
                receipt_number=f"APPT-{appointment_id}",
            )
        except Exception as e:
            current_app.logger.error(f"Receipt email error: {e}")

        # Notify provider
        try:
            from app.telegram.notifications import notify_status_change
            notify_status_change(appointment.provider_id, service_name, 'work_submitted', 'completed')
        except Exception:
            pass

        return jsonify({'success': True, 'message': 'Payment released. Service completed!'})

    except stripe.StripeError as e:
        current_app.logger.error(f"Stripe error completing appointment {appointment_id}: {e}")
        return jsonify({'success': False, 'message': 'Internal server error'}), 500
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error completing appointment: {e}")
        return jsonify({'success': False, 'message': 'Internal server error'}), 500


@client_bp.route('/complete_request_appointment', methods=['POST'])
@login_required
def complete_request_appointment():
    """Client approves work_submitted on a request → capture payment → transfer → completed."""
    if current_user.role != 'client':
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    try:
        data = request.get_json()
        request_id = data.get('request_id')
        if not request_id:
            return jsonify({'success': False, 'message': 'Request ID required'}), 400

        req = ClientSelfCreatedAppointment.query.filter_by(
            id=request_id, patient_id=current_user.id
        ).first()
        if not req:
            return jsonify({'success': False, 'message': 'Request not found'}), 404

        if req.status != 'work_submitted':
            return jsonify({'success': False, 'message': 'Request is not in work_submitted state'}), 400

        provider = User.query.get(req.provider_id) if req.provider_id else None
        is_free = (req.payment or 0) == 0

        if not is_free and req.payment_intent_id:
            if not provider or not provider.stripe_account_id:
                return jsonify({'success': False, 'message': 'Provider Stripe account not connected'}), 400

            pi = stripe.PaymentIntent.capture(
                req.payment_intent_id,
                idempotency_key=f"complete_req_{request_id}",
            )
            amount_cents = pi.amount_received
            commission_rate = current_app.config.get('PLATFORM_COMMISSION_RATE', 0.15)
            platform_fee_cents = int(round(amount_cents * commission_rate))
            payout_cents = amount_cents - platform_fee_cents

            stripe.Transfer.create(
                amount=payout_cents,
                currency='eur',
                destination=provider.stripe_account_id,
                transfer_group=f"req_{request_id}",
                metadata={'request_id': str(request_id)},
                idempotency_key=f"transfer_req_{request_id}",
            )

        req.set_status('completed')

        # Sync linked appointment + service history
        from app.routes.provider.appointments import sync_request_appointment_status
        sync_request_appointment_status(req, 'completed')

        db.session.commit()

        # Send receipt email
        try:
            from app.routes.provider.appointments import send_service_receipt_email
            amount = float(req.payment or 0)
            send_service_receipt_email(
                client=current_user,
                provider=provider,
                service_name=req.service_name or 'Service',
                amount=amount,
                currency='EUR',
                service_date=req.appointment_start_time.strftime('%d.%m.%Y') if req.appointment_start_time else '',
                service_time=req.appointment_start_time.strftime('%H:%M') if req.appointment_start_time else '',
                receipt_number=f"REQ-{request_id}",
            )
        except Exception as e:
            current_app.logger.error(f"Receipt email error: {e}")

        # Notify provider
        try:
            from app.telegram.notifications import notify_status_change
            if req.provider_id:
                notify_status_change(req.provider_id, req.service_name or 'Service', 'work_submitted', 'completed')
        except Exception:
            pass

        return jsonify({'success': True, 'message': 'Payment released. Service completed!'})

    except stripe.StripeError as e:
        current_app.logger.error(f"Stripe error completing request {request_id}: {e}")
        return jsonify({'success': False, 'message': 'Internal server error'}), 500
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error completing request: {e}")
        return jsonify({'success': False, 'message': 'Internal server error'}), 500


@client_bp.route('/client_get_history', methods=['GET'])
@login_required
def client_get_history():
    """Return merged list of completed/cancelled appointments and requests for history page."""
    if current_user.role != 'client':
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    try:
        items = []

        # Self-created requests
        reqs = ClientSelfCreatedAppointment.query.filter(
            ClientSelfCreatedAppointment.patient_id == current_user.id,
            ClientSelfCreatedAppointment.status.in_(['completed', 'confirmed_paid', 'cancelled', 'work_submitted'])
        ).order_by(ClientSelfCreatedAppointment.created_appo.desc()).all()

        for req in reqs:
            provider_name = None
            if req.provider:
                provider_name = req.provider.full_name or req.provider.user_name
            items.append({
                'id': req.id,
                'type': 'request',
                'service_name': req.service_name or 'Service',
                'status': req.status,
                'price': float(req.payment or 0),
                'date': req.appointment_start_time.isoformat() if req.appointment_start_time else None,
                'date_display': req.appointment_start_time.strftime('%d.%m.%Y %H:%M') if req.appointment_start_time else '',
                'provider_name': provider_name,
                'notes': req.notes,
                'receipt_number': f"REQ-{req.id}",
                'sort_key': req.appointment_start_time.isoformat() if req.appointment_start_time else '1970-01-01',
            })

        # Direct bookings
        appos = Appointment.query.filter(
            Appointment.client_id == current_user.id,
            Appointment.status.in_(['completed', 'confirmed_paid', 'cancelled', 'work_submitted'])
        ).order_by(Appointment.appointment_time.desc()).all()

        for a in appos:
            provider = User.query.get(a.provider_id)
            service = ProviderService.query.get(a.nurse_service_id) if a.nurse_service_id else None
            service_name = service.name if service and service.name else (service.base_service.name if service and service.base_service else 'Service')
            price = service.price if service else 0
            items.append({
                'id': a.id,
                'type': 'appointment',
                'service_name': service_name,
                'status': a.status,
                'price': float(price),
                'date': a.appointment_time.isoformat() if a.appointment_time else None,
                'date_display': a.appointment_time.strftime('%d.%m.%Y %H:%M') if a.appointment_time else '',
                'provider_name': (provider.full_name or provider.user_name) if provider else 'Unknown',
                'notes': a.notes,
                'receipt_number': f"APPT-{a.id}",
                'sort_key': a.appointment_time.isoformat() if a.appointment_time else '1970-01-01',
            })

        # Sort by date descending
        items.sort(key=lambda x: x['sort_key'], reverse=True)

        return jsonify({'success': True, 'items': items})

    except Exception as e:
        current_app.logger.error(f"Error retrieving history: {str(e)}")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


@client_bp.route('/receipt/<receipt_type>/<int:item_id>')
@login_required
def view_receipt(receipt_type, item_id):
    """Render a print-friendly receipt page for a completed service."""
    if current_user.role != 'client':
        return redirect(url_for('auth.login'))

    now = datetime.now()

    if receipt_type == 'appointment':
        a = Appointment.query.filter_by(id=item_id, client_id=current_user.id).first_or_404()
        provider = User.query.get(a.provider_id)
        service = ProviderService.query.get(a.nurse_service_id) if a.nurse_service_id else None
        service_name = service.name if service and service.name else 'Service'
        price = service.price if service else 0
        return render_template('client/receipt.html',
            receipt_number=f"APPT-{a.id}",
            client_name=current_user.full_name or current_user.user_name,
            provider_name=(provider.full_name or provider.user_name) if provider else 'Unknown',
            service_name=service_name,
            price=price,
            currency='EUR',
            service_date=a.appointment_time.strftime('%d.%m.%Y') if a.appointment_time else '',
            service_time=a.appointment_time.strftime('%H:%M') if a.appointment_time else '',
            status=a.status,
            now=now,
        )
    elif receipt_type == 'request':
        req = ClientSelfCreatedAppointment.query.filter_by(id=item_id, patient_id=current_user.id).first_or_404()
        provider_name = 'Unknown'
        if req.provider:
            provider_name = req.provider.full_name or req.provider.user_name
        return render_template('client/receipt.html',
            receipt_number=f"REQ-{req.id}",
            client_name=current_user.full_name or current_user.user_name,
            provider_name=provider_name,
            service_name=req.service_name or 'Service',
            price=float(req.payment or 0),
            currency='EUR',
            service_date=req.appointment_start_time.strftime('%d.%m.%Y') if req.appointment_start_time else '',
            service_time=req.appointment_start_time.strftime('%H:%M') if req.appointment_start_time else '',
            status=req.status,
            now=now,
        )
    else:
        abort(404)


# ── Client No-Show Provider & Disputes ───────────────────────────────────────

@client_bp.route('/report_no_show_provider', methods=['POST'])
@login_required
def report_no_show_provider():
    """Client reports provider no-show → full refund."""
    if current_user.role != 'client':
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    data = request.get_json() or {}
    appointment_id = data.get('appointment_id')
    request_id = data.get('request_id')
    reason = data.get('reason', '')

    try:
        from app.models import NoShowRecord

        if appointment_id:
            item = Appointment.query.filter_by(id=appointment_id, client_id=current_user.id).first()
            if not item:
                return jsonify({'success': False, 'message': 'Appointment not found'}), 404
            if item.status not in ('confirmed_paid', 'confirmed'):
                return jsonify({'success': False, 'message': 'Cannot report no-show for this status'}), 400

            now = datetime.now()
            if now < item.appointment_time + timedelta(minutes=15):
                return jsonify({'success': False, 'message': 'Must wait 15 minutes after appointment time'}), 400

            # Full refund to client
            payment = Payment.query.filter_by(appointment_id=item.id, status='completed').first()
            if payment and payment.transaction_id:
                stripe.PaymentIntent.cancel(payment.transaction_id, cancellation_reason='requested_by_customer')
                payment.status = 'canceled'

            provider = User.query.get(item.provider_id)
            record = NoShowRecord(
                appointment_id=item.id, reported_by_id=current_user.id,
                no_show_user_id=item.provider_id, role='provider', reason=reason,
            )
            db.session.add(record)
            if provider:
                provider.no_show_count = (provider.no_show_count or 0) + 1
            item.set_status('no_show')
            from app.routes.provider.appointments import sync_appointment_request_status
            sync_appointment_request_status(item, 'no_show')
            db.session.commit()
            return jsonify({'success': True, 'message': 'Provider no-show recorded. Full refund issued.'})

        elif request_id:
            item = ClientSelfCreatedAppointment.query.filter_by(id=request_id, patient_id=current_user.id).first()
            if not item:
                return jsonify({'success': False, 'message': 'Request not found'}), 404
            if item.status not in ('authorized', 'confirmed_paid', 'accepted'):
                return jsonify({'success': False, 'message': 'Cannot report no-show for this status'}), 400

            now = datetime.now()
            if now < item.appointment_start_time + timedelta(minutes=15):
                return jsonify({'success': False, 'message': 'Must wait 15 minutes after appointment time'}), 400

            if item.payment_intent_id:
                stripe.PaymentIntent.cancel(item.payment_intent_id, cancellation_reason='requested_by_customer')

            provider = User.query.get(item.provider_id) if item.provider_id else None
            record = NoShowRecord(
                request_id=item.id, reported_by_id=current_user.id,
                no_show_user_id=item.provider_id, role='provider', reason=reason,
            )
            db.session.add(record)
            if provider:
                provider.no_show_count = (provider.no_show_count or 0) + 1
            item.set_status('no_show')
            from app.routes.provider.appointments import sync_request_appointment_status
            sync_request_appointment_status(item, 'no_show')
            db.session.commit()
            return jsonify({'success': True, 'message': 'Provider no-show recorded. Full refund issued.'})

        return jsonify({'success': False, 'message': 'appointment_id or request_id required'}), 400

    except stripe.StripeError as e:
        current_app.logger.error(f"Stripe error on provider no-show: {e}")
        return jsonify({'success': False, 'message': 'Internal server error'}), 500
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error reporting provider no-show: {e}")
        return jsonify({'success': False, 'message': 'Internal server error'}), 500


@client_bp.route('/dispute', methods=['POST'])
@login_required
def create_dispute():
    """Client creates a dispute about service quality or completion."""
    if current_user.role != 'client':
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    data = request.get_json() or {}
    appointment_id = data.get('appointment_id')
    request_id = data.get('request_id')
    reason = data.get('reason', 'other')
    description = data.get('description', '')

    if reason not in ('not_completed', 'quality_issue', 'other'):
        return jsonify({'success': False, 'message': 'Invalid reason'}), 400

    try:
        from app.models import Dispute

        if appointment_id:
            item = Appointment.query.filter_by(id=appointment_id, client_id=current_user.id).first()
            if not item:
                return jsonify({'success': False, 'message': 'Appointment not found'}), 404
            if item.status not in ('work_submitted', 'completed'):
                return jsonify({'success': False, 'message': 'Can only dispute work_submitted or completed appointments'}), 400

            dispute = Dispute(
                appointment_id=item.id, reporter_id=current_user.id,
                reason=reason, description=description,
            )
            db.session.add(dispute)
            item.set_status('disputed')
            from app.routes.provider.appointments import sync_appointment_request_status
            sync_appointment_request_status(item, 'disputed')
            db.session.commit()

            # Notify provider
            try:
                from app.telegram.notifications import send_user_telegram
                svc = item.provider_service.name if item.provider_service else 'Service'
                send_user_telegram(item.provider_id,
                    f"A dispute has been filed for '{svc}'. Reason: {reason}.")
            except Exception:
                pass

            return jsonify({'success': True, 'message': 'Dispute created'})

        elif request_id:
            item = ClientSelfCreatedAppointment.query.filter_by(id=request_id, patient_id=current_user.id).first()
            if not item:
                return jsonify({'success': False, 'message': 'Request not found'}), 404
            if item.status not in ('work_submitted', 'completed'):
                return jsonify({'success': False, 'message': 'Can only dispute work_submitted or completed requests'}), 400

            dispute = Dispute(
                request_id=item.id, reporter_id=current_user.id,
                reason=reason, description=description,
            )
            db.session.add(dispute)
            item.set_status('disputed')
            from app.routes.provider.appointments import sync_request_appointment_status
            sync_request_appointment_status(item, 'disputed')
            db.session.commit()

            # Notify provider
            try:
                from app.telegram.notifications import send_user_telegram
                if item.provider_id:
                    send_user_telegram(item.provider_id,
                        f"A dispute has been filed for '{item.service_name or 'Service'}'. Reason: {reason}.")
            except Exception:
                pass

            return jsonify({'success': True, 'message': 'Dispute created'})

        return jsonify({'success': False, 'message': 'appointment_id or request_id required'}), 400

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating dispute: {e}")
        return jsonify({'success': False, 'message': 'Internal server error'}), 500



# SocketIO handlers are defined in provider/dashboard.py (single source of truth)
