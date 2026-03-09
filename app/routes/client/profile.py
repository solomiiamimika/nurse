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


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif', 'pdf'}


@client_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if current_user.role != 'client':
        return redirect(url_for('auth.login'))

    formatted_date = current_user.date_birth.strftime('%Y-%m-%d') if current_user.date_birth else ''

    if request.method == 'POST':
        try:
            current_user.full_name = request.form.get('full_name')
            new_email = request.form.get('email', '').strip()
            if new_email and new_email != current_user.email:
                existing = User.query.filter(User.email == new_email, User.id != current_user.id).first()
                if existing:
                    flash('This email is already in use', 'danger')
                    return redirect(url_for('client.profile'))
                current_user.email = new_email
            current_user.phone_number = request.form.get('phone_number')
            current_user.about_me = request.form.get('about_me')
            current_user.address = request.form.get('address')
            new_password = request.form.get('password', '').strip()
            if new_password:
                current_user.password_hash = bcrypt.generate_password_hash(new_password).decode('utf-8')

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
        profile_photo = get_file_url(current_user.photo, buckets['profile_pictures'])
    documents_urls = {}
    if current_user.documents:
        documents = json.loads(current_user.documents)
        for i in documents:
            documents_urls[i] = get_file_url(i, buckets['documents'])
    id_doc_url = None
    if current_user.id_document:
        id_doc_url = get_file_url(current_user.id_document, buckets['documents'])

    return render_template('client/profile.html',
                           formatted_date=formatted_date,
                           profile_photo=profile_photo,
                           documents_urls=documents_urls,
                           id_doc_url=id_doc_url,
                           user=current_user)


@client_bp.route('/update_visibility', methods=['POST'])
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


@client_bp.route('/upload_id_document', methods=['POST'])
@login_required
def upload_id_document():
    if current_user.role != 'client':
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    file = request.files.get('id_document')
    if not file or file.filename == '':
        return jsonify({'success': False, 'message': 'No file provided'})
    ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
    if ext not in ('jpg', 'jpeg', 'png', 'pdf'):
        return jsonify({'success': False, 'message': 'Allowed: JPG, PNG, PDF'})
    try:
        if current_user.id_document:
            delete_from_supabase(current_user.id_document, buckets['documents'])
        filename, _ = upload_to_supabase(file, buckets['documents'], current_user.id, 'id_document')
        if filename:
            current_user.id_document = filename
            current_user.id_verification_status = 'pending'
            current_user.id_verified = False
            current_user.id_rejection_reason = None
            db.session.commit()
            return jsonify({'success': True})
        return jsonify({'success': False, 'message': 'Upload failed'})
    except Exception:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Internal server error'}), 500


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
            current_app.logger.error(f"Supabase delete error: {e}")

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
        current_app.logger.error(f"Profile update error: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Internal server error'}), 500
