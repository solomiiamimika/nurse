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


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@provider_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if current_user.role != 'provider':
        return redirect(url_for('auth.login'))

    formatted_date = current_user.date_birth.strftime('%Y-%m-%d') if current_user.date_birth else ''

    if request.method == 'POST':
        try:
            current_user.full_name = request.form.get('full_name')
            current_user.phone_number = request.form.get('phone_number')
            current_user.about_me = request.form.get('about_me')
            current_user.address = request.form.get('address')
            current_user.password_hash = request.form.get('password')

            date_birth_str = request.form.get('date_birth')
            if date_birth_str:
                current_user.date_birth = datetime.strptime(date_birth_str, '%Y-%m-%d').date()

            if 'profile_picture' in request.files:
                file = request.files['profile_picture']
                if file and file.filename != '' and allowed_file(file.filename):
                    if current_user.photo:
                        delete_from_supabase(current_user.photo, buckets['profile_pictures'])

                    filename, file_url = upload_to_supabase(
                        file,
                        buckets['profile_pictures'],
                        current_user.id,
                        'nurse_profile'
                    )
                    if filename:
                        current_user.photo = filename

            if 'documents' in request.files:
                documents = request.files.getlist('documents')
                saved_docs = []
                for doc in documents:
                    if doc and doc.filename != '' and allowed_file(doc.filename):
                        filename, file_url = upload_to_supabase(
                            doc,
                            buckets['documents'],
                            current_user.id,
                            'nurse_doc'
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
            flash(f'Error updating profile: {str(e)}', 'danger')

        return redirect(url_for('provider.profile'))

    profile_photo = None
    if current_user.photo:
        profile_photo = get_file_url(current_user.photo, buckets['profile_pictures'])

    documents_urls = {}
    if current_user.documents:
        try:
            documents_list = json.loads(current_user.documents)
            for doc_name in documents_list:
                documents_urls[doc_name] = get_file_url(doc_name, buckets['documents'])
        except json.JSONDecodeError:
            documents_urls = {}

    # Fetch Stripe account details for the payout section
    stripe_info = None
    if current_user.stripe_account_id:
        try:
            acct = stripe.Account.retrieve(current_user.stripe_account_id)
            balance = stripe.Balance.retrieve(stripe_account=current_user.stripe_account_id)
            available_cents = sum(b.amount for b in balance.available)
            currency = balance.available[0].currency.upper() if balance.available else 'EUR'

            bank_accounts = acct.get('external_accounts', {}).get('data', [])
            bank = bank_accounts[0] if bank_accounts else None

            stripe_info = {
                'charges_enabled': acct.charges_enabled,
                'payouts_enabled': acct.payouts_enabled,
                'details_submitted': acct.details_submitted,
                'available_balance': available_cents / 100,
                'currency': currency,
                'bank_name': bank.get('bank_name') if bank else None,
                'last4': bank.get('last4') if bank else None,
                'account_holder': bank.get('account_holder_name') if bank else None,
            }
        except Exception:
            stripe_info = {'error': True}

    insurance_doc_url = None
    if current_user.insurance_document:
        insurance_doc_url = get_file_url(current_user.insurance_document, buckets['documents'])

    portfolio_items = []
    if current_user.portfolio:
        try:
            for item in json.loads(current_user.portfolio):
                portfolio_items.append({
                    'url': get_file_url(item['url'], buckets['profile_pictures']),
                    'filename': item['url'],
                    'type': item.get('type', 'photo'),
                })
        except (json.JSONDecodeError, KeyError):
            pass

    return render_template('provider/profile.html',
                           formatted_date=formatted_date,
                           documents_urls=documents_urls,
                           profile_photo=profile_photo,
                           stripe_info=stripe_info,
                           insurance_doc_url=insurance_doc_url,
                           portfolio_items=portfolio_items,
                           user=current_user)


@provider_bp.route('/delete_document', methods=['POST'])
@login_required
def delete_document():
    try:
        data = request.get_json()
        doc_name = data.get('doc_name')

        delete_from_supabase(doc_name, buckets['documents'])

        if current_user.documents:
            docs = json.loads(current_user.documents)
            if doc_name in docs:
                docs.remove(doc_name)
                current_user.documents = json.dumps(docs) if docs else None
                db.session.commit()
                return jsonify({'success': True})

        return jsonify({'success': False, 'message': 'Doc not found'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@provider_bp.route('/update_insurance_flag', methods=['POST'])
@login_required
def update_insurance_flag():
    data = request.get_json()
    current_user.has_insurance = bool(data.get('has_insurance'))
    db.session.commit()
    return jsonify({'success': True})


@provider_bp.route('/upload_insurance_doc', methods=['POST'])
@login_required
def upload_insurance_doc():
    file = request.files.get('insurance_document')
    if not file or file.filename == '':
        return jsonify({'success': False, 'message': 'No file provided'})
    if not allowed_file(file.filename):
        return jsonify({'success': False, 'message': 'Invalid file type'})
    try:
        if current_user.insurance_document:
            delete_from_supabase(current_user.insurance_document, buckets['documents'])
        filename, _ = upload_to_supabase(file, buckets['documents'], current_user.id, 'insurance')
        if filename:
            current_user.insurance_document = filename
            db.session.commit()
            return jsonify({'success': True})
        return jsonify({'success': False, 'message': 'Upload failed'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@provider_bp.route('/delete_insurance_doc', methods=['POST'])
@login_required
def delete_insurance_doc():
    if current_user.insurance_document:
        delete_from_supabase(current_user.insurance_document, buckets['documents'])
        current_user.insurance_document = None
        db.session.commit()
    return jsonify({'success': True})


PORTFOLIO_PHOTO_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
PORTFOLIO_VIDEO_EXTENSIONS = {'mp4', 'mov', 'webm'}
PORTFOLIO_ALL_EXTENSIONS = PORTFOLIO_PHOTO_EXTENSIONS | PORTFOLIO_VIDEO_EXTENSIONS


@provider_bp.route('/portfolio/upload', methods=['POST'])
@login_required
def portfolio_upload():
    """Upload a photo or video to portfolio gallery."""
    file = request.files.get('file')
    if not file or file.filename == '':
        return jsonify({'success': False, 'message': 'No file provided'}), 400

    ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
    if ext not in PORTFOLIO_ALL_EXTENSIONS:
        return jsonify({'success': False, 'message': 'Allowed: JPG, PNG, GIF, WEBP, MP4, MOV, WEBM'}), 400

    file_type = 'video' if ext in PORTFOLIO_VIDEO_EXTENSIONS else 'photo'

    try:
        filename, file_url = upload_to_supabase(
            file, buckets['profile_pictures'], current_user.id, 'portfolio'
        )
        if not filename:
            return jsonify({'success': False, 'message': 'Upload failed'}), 500

        portfolio = json.loads(current_user.portfolio or '[]')
        portfolio.append({'url': filename, 'type': file_type})
        current_user.portfolio = json.dumps(portfolio)
        db.session.commit()

        return jsonify({
            'success': True,
            'item': {
                'url': get_file_url(filename, buckets['profile_pictures']),
                'filename': filename,
                'type': file_type,
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@provider_bp.route('/portfolio/delete', methods=['POST'])
@login_required
def portfolio_delete():
    """Remove a photo or video from portfolio gallery."""
    data = request.get_json()
    filename = data.get('filename')
    if not filename:
        return jsonify({'success': False, 'message': 'Filename required'}), 400

    try:
        delete_from_supabase(filename, buckets['profile_pictures'])
    except Exception:
        pass

    portfolio = json.loads(current_user.portfolio or '[]')
    portfolio = [item for item in portfolio if item.get('url') != filename]
    current_user.portfolio = json.dumps(portfolio) if portfolio else None
    db.session.commit()

    return jsonify({'success': True})


@provider_bp.route('/update_visibility', methods=['POST'])
@login_required
def update_visibility():
    data = request.get_json()
    field = data.get('field')
    visible = data.get('visible')
    vis = json.loads(current_user.profile_visibility or '{}')
    vis[field] = visible
    current_user.profile_visibility = json.dumps(vis)
    db.session.commit()
    return jsonify({'success': True})
