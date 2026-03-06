from functools import wraps
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from app.models import User, Appointment, Service, db
from sqlalchemy import func
from datetime import datetime, timedelta

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

    return render_template('owner/dashboard.html',
                           total_clients=total_clients,
                           total_providers=total_providers,
                           total_completed=total_completed,
                           total_active=total_active,
                           avg_rating=avg_rating,
                           recent_users=recent_users)


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
