from functools import wraps
import json
import requests as http_requests
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, abort, current_app
from flask_login import login_required, current_user
from app.models import User, Appointment, Service, Feedback, InvitationToken, db, NoShowRecord, Dispute, ClientSelfCreatedAppointment
from sqlalchemy import func
from datetime import datetime, timedelta
import secrets
import stripe
import os
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

owner_bp = Blueprint('owner', __name__, url_prefix='/owner')


def owner_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.is_owner:
            abort(403)
        return f(*args, **kwargs)
    return decorated


# ── Dashboard ─────────────────────────────────────────────────────────────────

@owner_bp.route('/')
@owner_required
def dashboard():
    total_clients   = User.query.filter_by(role='client').count()
    total_providers = User.query.filter_by(role='provider').count()
    total_completed = Appointment.query.filter_by(status='completed').count()
    total_active    = Appointment.query.filter(
        Appointment.status.in_(['confirmed', 'confirmed_paid', 'scheduled'])
    ).count()

    # average_rating is a Python property — compute in Python
    all_providers = User.query.filter_by(role='provider').all()
    ratings = [p.average_rating for p in all_providers if p.average_rating]
    avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else None

    recent_users = User.query.order_by(User.created_at.desc()).limit(10).all()

    open_disputes = Dispute.query.filter(Dispute.status.in_(['open', 'under_review'])).count()
    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    no_shows_month = NoShowRecord.query.filter(NoShowRecord.created_at >= month_start).count()

    return render_template('owner/dashboard.html',
                           total_clients=total_clients,
                           total_providers=total_providers,
                           total_completed=total_completed,
                           total_active=total_active,
                           avg_rating=avg_rating,
                           recent_users=recent_users,
                           open_disputes=open_disputes,
                           no_shows_month=no_shows_month)


# ── Users ─────────────────────────────────────────────────────────────────────

@owner_bp.route('/users')
@owner_required
def users():
    q    = request.args.get('q', '').strip()
    role = request.args.get('role', '')

    query = User.query
    if q:
        query = query.filter(
            (User.user_name.ilike(f'%{q}%')) |
            (User.email.ilike(f'%{q}%')) |
            (User.full_name.ilike(f'%{q}%'))
        )
    if role in ('client', 'provider'):
        query = query.filter_by(role=role)

    all_users = query.order_by(User.created_at.desc()).all()
    return render_template('owner/users.html', users=all_users, q=q, role_filter=role)


@owner_bp.route('/users/<int:user_id>/toggle_active', methods=['POST'])
@owner_required
def toggle_active(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        return jsonify({'success': False, 'message': 'Cannot deactivate yourself'}), 400
    user.is_active = not user.is_active
    db.session.commit()
    return jsonify({'success': True, 'is_active': user.is_active})


@owner_bp.route('/users/<int:user_id>/change_role', methods=['POST'])
@owner_required
def change_role(user_id):
    user = User.query.get_or_404(user_id)
    new_role = request.get_json().get('role')
    if new_role not in ('client', 'provider'):
        return jsonify({'success': False, 'message': 'Invalid role'}), 400
    user.role = new_role
    db.session.commit()
    return jsonify({'success': True, 'role': user.role})


# ── Create User (manual) ──────────────────────────────────────────────────────

@owner_bp.route('/users/create', methods=['POST'])
@owner_required
def create_user():
    """Owner creates a user account manually."""
    data = request.get_json() or {}
    username  = data.get('username', '').strip()
    email     = data.get('email', '').strip()
    full_name = data.get('full_name', '').strip()
    role      = data.get('role', 'client')

    if not username or len(username) < 2:
        return jsonify({'success': False, 'message': 'Username must be at least 2 characters'}), 400
    if not email:
        return jsonify({'success': False, 'message': 'Email is required'}), 400
    if role not in ('client', 'provider'):
        return jsonify({'success': False, 'message': 'Invalid role'}), 400
    if User.query.filter_by(user_name=username).first():
        return jsonify({'success': False, 'message': 'Username already taken'}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({'success': False, 'message': 'Email already registered'}), 400

    temp_password = secrets.token_urlsafe(12)

    # Generate unique referral code
    while True:
        ref_code = secrets.token_urlsafe(6)[:8].upper()
        if not User.query.filter_by(referral_code=ref_code).first():
            break

    user = User(
        user_name=username,
        email=email,
        full_name=full_name or None,
        role=role,
        roles=json.dumps([role]),
        referral_code=ref_code,
        terms_accepted=True,
        email_verified=False,
        phone_verified=False,
        id_verified=False,
    )
    user.password = temp_password
    db.session.add(user)
    db.session.commit()

    # Generate setup link
    from app.routes.auth import _generate_token
    token = _generate_token(user.id, salt='account-setup')
    setup_url = url_for('auth.setup_account', token=token, _external=True)

    return jsonify({
        'success': True,
        'user_id': user.id,
        'username': user.user_name,
        'temp_password': temp_password,
        'setup_url': setup_url,
    })


@owner_bp.route('/users/<int:user_id>/setup_link', methods=['POST'])
@owner_required
def generate_setup_link(user_id):
    """Generate a new setup link for an existing user."""
    user = User.query.get_or_404(user_id)
    from app.routes.auth import _generate_token
    token = _generate_token(user.id, salt='account-setup')
    setup_url = url_for('auth.setup_account', token=token, _external=True)
    return jsonify({'success': True, 'setup_url': setup_url})


@owner_bp.route('/users/<int:user_id>/manual_verify', methods=['POST'])
@owner_required
def manual_verify(user_id):
    """Owner manually toggles verification flags."""
    user = User.query.get_or_404(user_id)
    data = request.get_json() or {}

    if 'email_verified' in data:
        user.email_verified = bool(data['email_verified'])
    if 'phone_verified' in data:
        user.phone_verified = bool(data['phone_verified'])
    if 'id_verified' in data:
        user.id_verified = bool(data['id_verified'])
        if user.id_verified:
            user.id_verification_status = 'approved'

    db.session.commit()
    return jsonify({
        'success': True,
        'email_verified': user.email_verified,
        'phone_verified': user.phone_verified,
        'id_verified': user.id_verified,
    })


# ── Services ──────────────────────────────────────────────────────────────────

@owner_bp.route('/services')
@owner_required
def services():
    all_services = Service.query.order_by(Service.name).all()
    return render_template('owner/services.html', services=all_services)


@owner_bp.route('/services/add', methods=['POST'])
@owner_required
def add_service():
    data = request.get_json() or {}
    name          = data.get('name', '').strip()
    description   = data.get('description', '').strip()
    base_price    = data.get('base_price')
    base_duration = data.get('base_duration')

    if not name or base_price is None or base_duration is None:
        return jsonify({'success': False, 'message': 'name, base_price and base_duration are required'}), 400

    svc = Service(
        name=name,
        description=description or None,
        base_price=float(base_price),
        base_duration=int(base_duration),
        is_standart=True,
    )
    db.session.add(svc)
    db.session.commit()
    return jsonify({'success': True, 'id': svc.id, 'name': svc.name})


@owner_bp.route('/services/<int:service_id>/delete', methods=['POST'])
@owner_required
def delete_service(service_id):
    svc = Service.query.get_or_404(service_id)
    db.session.delete(svc)
    db.session.commit()
    return jsonify({'success': True})


# ── Verification ─────────────────────────────────────────────────────────────

@owner_bp.route('/verification')
@owner_required
def verification():
    unverified = User.query.filter_by(role='provider', is_verified=False).order_by(User.created_at.desc()).all()
    verified = User.query.filter_by(role='provider', is_verified=True).order_by(User.verification_date.desc()).all()
    return render_template('owner/verification.html', unverified=unverified, verified=verified)


@owner_bp.route('/users/<int:user_id>/verify', methods=['POST'])
@owner_required
def verify_user(user_id):
    user = User.query.get_or_404(user_id)
    data = request.get_json() or {}
    method = data.get('method', 'manual')

    user.is_verified = True
    user.verification_method = method
    user.verification_date = datetime.utcnow()
    db.session.commit()
    return jsonify({'success': True, 'is_verified': True})


@owner_bp.route('/users/<int:user_id>/unverify', methods=['POST'])
@owner_required
def unverify_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_verified = False
    user.verification_method = None
    user.verification_date = None
    db.session.commit()
    return jsonify({'success': True, 'is_verified': False})


# ── Feedback ─────────────────────────────────────────────────────────────────

@owner_bp.route('/feedback')
@owner_required
def feedback():
    all_feedback = Feedback.query.order_by(Feedback.created_at.desc()).all()
    return render_template('owner/feedback.html', feedbacks=all_feedback)


@owner_bp.route('/feedback/<int:fb_id>/status', methods=['POST'])
@owner_required
def update_feedback_status(fb_id):
    fb = Feedback.query.get_or_404(fb_id)
    new_status = (request.get_json() or {}).get('status', 'reviewed')
    if new_status not in ('new', 'reviewed', 'resolved'):
        return jsonify({'success': False}), 400
    fb.status = new_status
    db.session.commit()
    return jsonify({'success': True, 'status': fb.status})


# ── Telegram Panel ────────────────────────────────────────────────────────────

@owner_bp.route('/telegram')
@owner_required
def telegram_panel():
    bot_token = current_app.config.get('TELEGRAM_BOT_TOKEN')
    bot_name = current_app.config.get('TELEGRAM_BOT_NAME')

    # Bot status
    bot_info = None
    if bot_token:
        try:
            resp = http_requests.get(
                f"https://api.telegram.org/bot{bot_token}/getMe", timeout=5
            )
            if resp.ok:
                bot_info = resp.json().get('result', {})
        except Exception:
            pass

    # Users with Telegram linked
    tg_users = User.query.filter(User.telegram_id.isnot(None)).order_by(User.created_at.desc()).all()
    tg_notifications_on = sum(1 for u in tg_users if u.telegram_notifications)

    # All users (for invitation dropdown)
    all_users = User.query.filter(User.is_active == True).order_by(User.full_name).all()

    return render_template('owner/telegram.html',
                           bot_info=bot_info,
                           bot_name=bot_name,
                           bot_token_set=bool(bot_token),
                           tg_users=tg_users,
                           tg_notifications_on=tg_notifications_on,
                           all_users=all_users)


@owner_bp.route('/telegram/send_message', methods=['POST'])
@owner_required
def telegram_send_message():
    """Send a message to a specific user via Telegram bot."""
    data = request.get_json() or {}
    user_id = data.get('user_id')
    message = data.get('message', '').strip()

    if not message:
        return jsonify({'success': False, 'error': 'Message is required'}), 400

    bot_token = current_app.config.get('TELEGRAM_BOT_TOKEN')
    if not bot_token:
        return jsonify({'success': False, 'error': 'Bot not configured'}), 400

    user = User.query.get(user_id)
    if not user or not user.telegram_id:
        return jsonify({'success': False, 'error': 'User has no Telegram linked'}), 400

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {'chat_id': user.telegram_id, 'text': message, 'parse_mode': 'HTML'}
    try:
        resp = http_requests.post(url, json=payload, timeout=5)
        if resp.ok:
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Telegram API error'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


@owner_bp.route('/telegram/send_invite', methods=['POST'])
@owner_required
def telegram_send_invite():
    """Create an invitation link and send it to a user or chat_id via Telegram."""
    data = request.get_json() or {}
    target = data.get('target', '').strip()       # user_id or raw telegram chat_id
    role_hint = data.get('role_hint', '')          # 'client', 'provider', or ''
    custom_text = data.get('custom_text', '').strip()

    bot_token = current_app.config.get('TELEGRAM_BOT_TOKEN')
    if not bot_token:
        return jsonify({'success': False, 'error': 'Bot not configured'}), 400

    if not target:
        return jsonify({'success': False, 'error': 'Target is required'}), 400

    # Resolve chat_id
    chat_id = None
    try:
        uid = int(target)
        user = User.query.get(uid)
        if user and user.telegram_id:
            chat_id = user.telegram_id
        else:
            # Maybe it's a raw chat_id
            chat_id = uid
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'Invalid target'}), 400

    # Create invitation token
    token = secrets.token_urlsafe(32)
    inv = InvitationToken(
        token=token,
        created_by=current_user.id,
        role_hint=role_hint if role_hint in ('client', 'provider') else None,
    )
    db.session.add(inv)
    db.session.commit()

    invite_url = url_for('auth.invite_landing', token=token, _external=True)
    role_label = f" as a {role_hint}" if role_hint else ""

    message = custom_text or f"You're invited to join Human-me{role_label}!"
    message += f"\n\nRegister here:\n{invite_url}"

    url_api = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {'chat_id': chat_id, 'text': message, 'parse_mode': 'HTML'}
    try:
        resp = http_requests.post(url_api, json=payload, timeout=5)
        if resp.ok:
            return jsonify({'success': True, 'invite_url': invite_url})
        error_data = resp.json() if resp.headers.get('content-type', '').startswith('application/json') else {}
        return jsonify({'success': False, 'error': error_data.get('description', 'Telegram API error')}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


@owner_bp.route('/telegram/broadcast', methods=['POST'])
@owner_required
def telegram_broadcast():
    """Send a message to all users who have Telegram linked and notifications on."""
    data = request.get_json() or {}
    message = data.get('message', '').strip()
    role_filter = data.get('role', '')  # 'client', 'provider', or '' (all)

    if not message:
        return jsonify({'success': False, 'error': 'Message is required'}), 400

    bot_token = current_app.config.get('TELEGRAM_BOT_TOKEN')
    if not bot_token:
        return jsonify({'success': False, 'error': 'Bot not configured'}), 400

    query = User.query.filter(
        User.telegram_id.isnot(None),
        User.telegram_notifications == True,
        User.is_active == True,
    )
    if role_filter in ('client', 'provider'):
        query = query.filter_by(role=role_filter)

    users = query.all()
    sent = 0
    failed = 0
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    for u in users:
        try:
            resp = http_requests.post(url, json={
                'chat_id': u.telegram_id, 'text': message, 'parse_mode': 'HTML'
            }, timeout=5)
            if resp.ok:
                sent += 1
            else:
                failed += 1
        except Exception:
            failed += 1

    return jsonify({'success': True, 'sent': sent, 'failed': failed, 'total': len(users)})


# ── Disputes ──────────────────────────────────────────────────────────────────

@owner_bp.route('/disputes')
@owner_required
def disputes():
    status_filter = request.args.get('status', '')
    query = Dispute.query
    if status_filter in ('open', 'under_review', 'resolved'):
        query = query.filter_by(status=status_filter)
    all_disputes = query.order_by(Dispute.created_at.desc()).all()

    # Enrich with appointment/request details
    enriched = []
    for d in all_disputes:
        info = {
            'dispute': d,
            'reporter': d.reporter,
        }
        if d.appointment_id:
            appt = Appointment.query.get(d.appointment_id)
            if appt:
                info['client'] = User.query.get(appt.client_id)
                info['provider'] = User.query.get(appt.provider_id)
                info['service_name'] = appt.provider_service.name if appt.provider_service else 'Service'
                info['date'] = appt.appointment_time
                info['amount'] = appt.provider_service.price if appt.provider_service else 0
                info['item_type'] = 'appointment'
                info['item_id'] = appt.id
        elif d.request_id:
            req = ClientSelfCreatedAppointment.query.get(d.request_id)
            if req:
                info['client'] = User.query.get(req.patient_id)
                info['provider'] = User.query.get(req.provider_id) if req.provider_id else None
                info['service_name'] = req.service_name or 'Service'
                info['date'] = req.appointment_start_time
                info['amount'] = float(req.payment or 0)
                info['item_type'] = 'request'
                info['item_id'] = req.id
        enriched.append(info)

    return render_template('owner/disputes.html', disputes=enriched, status_filter=status_filter)


@owner_bp.route('/disputes/<int:dispute_id>/resolve', methods=['POST'])
@owner_required
def resolve_dispute(dispute_id):
    d = Dispute.query.get_or_404(dispute_id)
    data = request.get_json() or {}
    resolution = data.get('resolution', 'dismissed')
    admin_notes = data.get('admin_notes', '')

    if resolution not in ('refunded', 'partial_refund', 'dismissed', 'warning'):
        return jsonify({'success': False, 'message': 'Invalid resolution'}), 400

    # Handle refunds if needed
    if resolution in ('refunded', 'partial_refund'):
        try:
            if d.appointment_id:
                from app.models import Payment
                appt = Appointment.query.get(d.appointment_id)
                payment = Payment.query.filter_by(appointment_id=appt.id).first() if appt else None
                if payment and payment.transaction_id:
                    if resolution == 'refunded':
                        stripe.Refund.create(payment_intent=payment.transaction_id)
                    else:
                        refund_pct = data.get('refund_percent', 50)
                        refund_amount = int(payment.amount_cents * int(refund_pct) / 100)
                        stripe.Refund.create(payment_intent=payment.transaction_id, amount=refund_amount)
            elif d.request_id:
                req = ClientSelfCreatedAppointment.query.get(d.request_id)
                if req and req.payment_intent_id:
                    if resolution == 'refunded':
                        stripe.Refund.create(payment_intent=req.payment_intent_id)
                    else:
                        refund_pct = data.get('refund_percent', 50)
                        refund_amount = int(int(req.payment * 100) * int(refund_pct) / 100)
                        stripe.Refund.create(payment_intent=req.payment_intent_id, amount=refund_amount)
        except stripe.StripeError as e:
            current_app.logger.error(f"Stripe dispute resolution error: {e}")
            return jsonify({'success': False, 'message': 'Payment processing error'}), 500

    d.status = 'resolved'
    d.resolution = resolution
    d.admin_notes = admin_notes
    d.resolved_by_id = current_user.id
    d.resolved_at = datetime.utcnow()
    db.session.commit()

    return jsonify({'success': True})


@owner_bp.route('/disputes/<int:dispute_id>/status', methods=['POST'])
@owner_required
def update_dispute_status(dispute_id):
    d = Dispute.query.get_or_404(dispute_id)
    new_status = (request.get_json() or {}).get('status', 'under_review')
    if new_status not in ('open', 'under_review', 'resolved'):
        return jsonify({'success': False}), 400
    d.status = new_status
    db.session.commit()
    return jsonify({'success': True, 'status': d.status})


# ── No-Shows ──────────────────────────────────────────────────────────────────

@owner_bp.route('/no_shows')
@owner_required
def no_shows():
    role_filter = request.args.get('role', '')
    query = NoShowRecord.query
    if role_filter in ('client', 'provider'):
        query = query.filter_by(role=role_filter)
    all_records = query.order_by(NoShowRecord.created_at.desc()).all()

    enriched = []
    for r in all_records:
        info = {
            'record': r,
            'no_show_user': r.no_show_user,
            'reported_by': r.reported_by,
        }
        if r.appointment_id:
            appt = Appointment.query.get(r.appointment_id)
            if appt:
                info['service_name'] = appt.provider_service.name if appt.provider_service else 'Service'
                info['date'] = appt.appointment_time
                info['item_type'] = 'appointment'
        elif r.request_id:
            req = ClientSelfCreatedAppointment.query.get(r.request_id)
            if req:
                info['service_name'] = req.service_name or 'Service'
                info['date'] = req.appointment_start_time
                info['item_type'] = 'request'
        enriched.append(info)

    return render_template('owner/no_shows.html', records=enriched, role_filter=role_filter)
