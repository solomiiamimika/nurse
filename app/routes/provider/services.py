from . import provider_bp
from flask import Blueprint, jsonify, request, current_app, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models import User, Message, db, Service, ProviderService, Appointment, ClientSelfCreatedAppointment, RequestOfferResponse, ServiceHistory, CancellationPolicy, SERVICE_TAGS
from app.models.service import SERVICE_TAG_CATEGORIES
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


@provider_bp.route('/services', methods=['GET', 'POST'])
@login_required
def manage_services():
    if current_user.role != 'provider':
        return redirect(url_for('auth.login'))

    standard_services = Service.query.filter_by(is_standart=True).all()
    provider_services = ProviderService.query.filter_by(provider_id=current_user.id).all()

    if request.method == 'POST':
        # Progressive verification: providers need full_name to manage services
        if not current_user.full_name:
            flash('Please add your full name in your profile before managing services.', 'warning')
            return redirect(url_for('provider.profile'))
        if not current_user.is_contact_verified:
            flash('Please verify your email or link Telegram before managing services.', 'warning')
            return redirect(url_for('provider.profile'))

        try:
            action = request.form.get('action')

            if action == 'add_custom':
                new_service = ProviderService(
                    provider_id=current_user.id,
                    service_id=None,
                    name=request.form.get('name'),
                    price=float(request.form.get('price')),
                    duration=int(request.form.get('duration')),
                    description=request.form.get('description', ''),
                    is_available='is_available' in request.form,
                    deposit_percentage=int(request.form.get('deposit_percentage', 0)),
                    tags=request.form.get('tags', '')
                )
                db.session.add(new_service)
                flash('Custom service added successfully', 'success')

            elif action == 'add':
                service_id = request.form.get('service_id')
                if not service_id:
                    flash('No service selected', 'danger')
                    return redirect(url_for('provider.manage_services'))

                new_service = ProviderService(
                    provider_id=current_user.id,
                    service_id=service_id,
                    name=None,
                    price=float(request.form.get('price')),
                    duration=int(request.form.get('duration')),
                    description=request.form.get('description', ''),
                    is_available='is_available' in request.form,
                    deposit_percentage=int(request.form.get('deposit_percentage', 0)),
                    tags=request.form.get('tags', '')
                )
                db.session.add(new_service)
                flash('Standard service added successfully', 'success')

            elif action == 'update':
                service_id = request.form.get('service_id')
                is_custom = request.form.get('is_custom') == 'true'

                if is_custom:
                    service = ProviderService.query.filter_by(
                        id=service_id,
                        provider_id=current_user.id
                    ).first()
                    if service:
                        service.name = request.form.get('name')
                else:
                    service = ProviderService.query.filter_by(
                        service_id=service_id,
                        provider_id=current_user.id
                    ).first()

                if service:
                    service.price = float(request.form.get('price'))
                    service.duration = int(request.form.get('duration'))
                    service.description = request.form.get('description', '')
                    service.is_available = 'is_available' in request.form
                    service.deposit_percentage = int(request.form.get('deposit_percentage', 0))
                    service.tags = request.form.get('tags', '')
                    flash('Service updated successfully', 'success')
                else:
                    flash('Service not found', 'danger')

            elif action == 'remove':
                service_id = request.form.get('service_id')
                service = ProviderService.query.filter_by(
                    service_id=service_id,
                    provider_id=current_user.id
                ).first()

                if service:
                    db.session.delete(service)
                    flash('Standard service removed successfully', 'success')
                else:
                    flash('Service not found', 'danger')

            elif action == 'remove_custom':
                service_id = request.form.get('service_id')
                service = ProviderService.query.filter_by(
                    id=service_id,
                    provider_id=current_user.id
                ).first()

                if service:
                    db.session.delete(service)
                    flash('Custom service removed successfully', 'success')
                else:
                    flash('Service not found', 'danger')

            db.session.commit()
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error managing services: {str(e)}")
            flash('Error processing request. Please try again.', 'danger')

        return redirect(url_for('provider.manage_services'))

    return render_template('provider/services.html',
                           standard_services=standard_services,
                           provider_services=provider_services,
                           service_tags=SERVICE_TAGS,
                           service_tag_categories=SERVICE_TAG_CATEGORIES)


@provider_bp.route('/service_history', methods=['GET'])
@login_required
def get_service_history():
    if current_user.role != 'provider':
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    try:
        history = ServiceHistory.query.filter_by(
            provider_id=current_user.id
        ).order_by(ServiceHistory.created_at.desc()).all()

        result = []
        for h in history:
            result.append({
                'id': h.id,
                'service_name': h.service_name,
                'service_description': h.service_description,
                'price': h.price,
                'appointment_time': h.appointment_time.isoformat(),
                'end_time': h.end_time.isoformat(),
                'status': h.status,
                'created_at': h.created_at.isoformat(),
                'client_name': h.client.full_name or h.client.user_name if h.client else None,
            })

        return jsonify({'success': True, 'history': result}), 200

    except Exception as e:
        current_app.logger.error(f"Error getting service history: {str(e)}")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


@provider_bp.route('/promote_from_history/<int:history_id>', methods=['POST'])
@login_required
def promote_from_history(history_id):
    """Перенести сервіс з ServiceHistory в постійний ProviderService."""
    if current_user.role != 'provider':
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    try:
        history_entry = ServiceHistory.query.filter_by(
            id=history_id,
            provider_id=current_user.id
        ).first()

        if not history_entry:
            return jsonify({'success': False, 'message': 'History entry not found'}), 404

        data = request.get_json() or {}
        price = float(data.get('price', history_entry.price))
        duration_minutes = int(data.get('duration', 60))
        name = data.get('name', history_entry.service_name)
        description = data.get('description', history_entry.service_description or '')

        # Перевіряємо чи вже є такий самий кастомний сервіс
        existing = ProviderService.query.filter_by(
            provider_id=current_user.id,
            name=name,
            service_id=None
        ).first()

        if existing:
            return jsonify({'success': False, 'message': 'Service with this name already exists'}), 400

        new_service = ProviderService(
            provider_id=current_user.id,
            service_id=None,
            name=name,
            price=price,
            duration=duration_minutes,
            description=description,
            is_available=True
        )
        db.session.add(new_service)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Service added to your permanent services',
            'provider_service_id': new_service.id
        }), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error promoting from history: {str(e)}")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500
