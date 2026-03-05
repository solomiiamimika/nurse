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
from app.extensions import socketio, db
from flask import current_app, request
from flask_socketio import join_room, leave_room, emit
from app.models import Message, db, User
from datetime import datetime
from sqlalchemy import func
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'app', 'static', 'uploads')
DOCUMENTS_FOLDER = os.path.join(UPLOAD_FOLDER, 'documents')
PROFILE_PICTURES_FOLDER = os.path.join(UPLOAD_FOLDER, 'profile_pictures')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx'}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DOCUMENTS_FOLDER, exist_ok=True)
os.makedirs(PROFILE_PICTURES_FOLDER, exist_ok=True)


def notify_nurses_about_new_appointment(appointment):
    """Notify service provider about a new request"""
    # Find all services nearby
    nurses = User.query.filter_by(role='provider').all()

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
    R = 6371  # Earth's radius in km

    lat1_rad = radians(lat1)
    lng1_rad = radians(lng1)
    lat2_rad = radians(lat2)
    lng2_rad = radians(lng2)

    dlng = lng2_rad - lng1_rad
    dlat = lat2_rad - lat1_rad

    a = sin(dlat/2)**2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlng/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))

    return R * c


@provider_bp.route('/connect_stripe', methods=['GET', 'POST'])
@login_required
def connect_stripe():
    try:
        country = request.args.get('country', 'DE')
        account = stripe.Account.create(
            type='express',
            country=country,
            email=current_user.email,
            capabilities={
                'card_payments': {'requested': True},
                'transfers': {'requested': True},
            },
        )
        current_user.stripe_account_id = account.id
        db.session.commit()
        account_link = stripe.AccountLink.create(
            account=account.id,
            refresh_url=url_for('provider.connect_stripe', _external=True),
            return_url=url_for('provider.dashboard', _external=True),
            type='account_onboarding',
        )
        return redirect(account_link.url)
    except Exception as e:
        current_app.logger.error(f"Stripe connection error: {str(e)}")
        flash('Error connecting to Stripe', 'danger')
        return redirect(url_for('provider.dashboard'))


@provider_bp.route('/finances')
@login_required
def provider_finances_management():
    if current_user.role != 'provider':
        return redirect(url_for('auth.login'))
    if not current_user.stripe_account_id:
        flash('Please connect your Stripe account first.', 'warning')
        return redirect(url_for('provider.connect_stripe'))
    try:
        stripe_account = stripe.Account.retrieve(current_user.stripe_account_id)
        balance = stripe.Balance.retrieve(stripe_account=stripe_account.id)
        payouts = stripe.Payout.list(stripe_account=stripe_account.id)
        transactions = stripe.BalanceTransaction.list(stripe_account=stripe_account.id)
        return render_template('provider/finances.html',
                               balance=balance,
                               payouts=payouts,
                               transactions=transactions)
    except Exception as e:
        current_app.logger.error(f"Error retrieving finances: {str(e)}")
        flash('Error retrieving financial data from Stripe', 'danger')
        return redirect(url_for('provider.dashboard'))


@provider_bp.route('/cancellation_policy', methods=['GET', 'POST'])
@login_required
def cancellation_policy():
    if current_user.role != 'provider':
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    policy = CancellationPolicy.query.filter_by(provider_id=current_user.id).first()

    if request.method == 'GET':
        if policy:
            return jsonify({
                'has_policy': True,
                'free_cancel_hours': policy.free_cancel_hours,
                'late_cancel_fee_percent': policy.late_cancel_fee_percent,
                'no_show_client_fee_percent': policy.no_show_client_fee_percent,
            })
        return jsonify({
            'has_policy': False,
            'free_cancel_hours': None,
            'late_cancel_fee_percent': 0,
            'no_show_client_fee_percent': 0,
        })

    # POST — зберегти або оновити
    try:
        data = request.get_json()

        free_cancel_hours = data.get('free_cancel_hours')
        if free_cancel_hours is not None:
            free_cancel_hours = int(free_cancel_hours)

        late_fee = int(data.get('late_cancel_fee_percent', 0))
        no_show_fee = int(data.get('no_show_client_fee_percent', 0))

        if not (0 <= late_fee <= 100) or not (0 <= no_show_fee <= 100):
            return jsonify({'success': False, 'message': 'Fee percent must be between 0 and 100'}), 400

        if policy:
            policy.free_cancel_hours = free_cancel_hours
            policy.late_cancel_fee_percent = late_fee
            policy.no_show_client_fee_percent = no_show_fee
            policy.updated_at = datetime.now()
        else:
            policy = CancellationPolicy(
                provider_id=current_user.id,
                free_cancel_hours=free_cancel_hours,
                late_cancel_fee_percent=late_fee,
                no_show_client_fee_percent=no_show_fee,
            )
            db.session.add(policy)

        db.session.commit()
        return jsonify({'success': True, 'message': 'Policy saved'})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error saving cancellation policy: {str(e)}")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


@provider_bp.route('/stats')
@login_required
def nurse_stats():
    if current_user.role != 'provider':
        return jsonify({'error': 'Access denied'}), 403

    accepted_statuses = ['confirmed', 'confirmed_paid', 'nurse_confirmed']
    accepted_count = Appointment.query.filter(
        Appointment.provider_id == current_user.id,
        Appointment.status.in_(accepted_statuses)
    ).count()

    completed_count = Appointment.query.filter(
        Appointment.provider_id == current_user.id,
        Appointment.status == 'completed'
    ).count()

    avg_rating = current_user.average_nurse_rating  # with hybrid_property
    reviews_count = current_user.reviews_nurse_count

    # Additionally: how many upcoming active requests
    upcoming_count = Appointment.query.filter(
        Appointment.provider_id == current_user.id,
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
