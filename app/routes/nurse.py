from flask import Blueprint, jsonify, request, current_app, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models import User, Message, db
from datetime import datetime
import json
import os
from werkzeug.utils import secure_filename

nurse_bp = Blueprint('nurse', __name__)


BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'app', 'static', 'uploads')
DOCUMENTS_FOLDER = os.path.join(UPLOAD_FOLDER, 'documents')
PROFILE_PICTURES_FOLDER = os.path.join(UPLOAD_FOLDER, 'profile_pictures')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx'}


os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DOCUMENTS_FOLDER, exist_ok=True)
os.makedirs(PROFILE_PICTURES_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@nurse_bp.route('/dashboard')
@login_required
def dashboard():
    if current_user.role != 'nurse':
        return redirect(url_for('auth.login'))
    return render_template('nurse/dashboard.html')

@nurse_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if current_user.role != 'nurse':
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        try:
            # Оновлюємо основну інформацію
            current_user.full_name = request.form.get('full_name')
            current_user.phone_number = request.form.get('phone_number')
            current_user.about_me = request.form.get('about_me')
            current_user.address = request.form.get('address')
            
            date_birth_str = request.form.get('date_birth')
            if date_birth_str:
                current_user.date_birth = datetime.strptime(date_birth_str, '%Y-%m-%d').date()
            
            if 'profile_picture' in request.files:
                file = request.files['profile_picture']
                if file and allowed_file(file.filename):
                    filename = secure_filename(f"nurse_{current_user.id}_{datetime.now().timestamp()}.{file.filename.rsplit('.', 1)[1].lower()}")
                    file_path = os.path.join(PROFILE_PICTURES_FOLDER, filename)
                    file.save(file_path)
                    current_user.profile_picture = filename
            
            if 'documents' in request.files:
                documents = request.files.getlist('documents')
                saved_docs = []
                for doc in documents:
                    if doc and allowed_file(doc.filename):
                        filename = secure_filename(f"doc_{current_user.id}_{datetime.now().timestamp()}_{doc.filename}")
                        file_path = os.path.join(DOCUMENTS_FOLDER, filename)
                        doc.save(file_path)
                        saved_docs.append(filename)
                
                if saved_docs:
                    current_user.documents = json.dumps(saved_docs)
            
            db.session.commit()
            flash('Профіль успішно оновлено!', 'success')
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating profile: {str(e)}")
            flash('Помилка при оновленні профілю', 'danger')
        
        return redirect(url_for('nurse.profile'))
    
    formatted_date = current_user.date_birth.strftime('%Y-%m-%d') if current_user.date_birth else ''
    user_documents = json.loads(current_user.documents) if current_user.documents else []
    
    return render_template('nurse/profile.html', 
                         formatted_date=formatted_date,
                         user_documents=user_documents)

@nurse_bp.route('/delete_document', methods=['POST'])
@login_required
def delete_document():
    if current_user.role != 'nurse':
        return jsonify({'success': False, 'message': 'Доступ заборонено'}), 403
    
    try:
        doc_name = request.json.get('doc_name')
        if not doc_name:
            return jsonify({'success': False, 'message': 'Не вказано назву документа'})

        doc_path = os.path.join(DOCUMENTS_FOLDER, doc_name)
        if os.path.exists(doc_path):
            os.remove(doc_path)
        

        if current_user.documents:
            documents = json.loads(current_user.documents)
            if doc_name in documents:
                documents.remove(doc_name)
                current_user.documents = json.dumps(documents) if documents else None
                db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@nurse_bp.route('/update_location', methods=['POST'])
@login_required
def update_location():
    if current_user.role != 'nurse':
        return jsonify({'success': False, 'message': 'Доступ заборонено'}), 403
    
    try:
        data = request.get_json()
        if not data or 'latitude' not in data or 'longitude' not in data:
            return jsonify({'success': False, 'message': 'Необхідно надати координати'}), 400
        
        current_user.latitude = float(data['latitude'])
        current_user.longitude = float(data['longitude'])
        current_user.location_approved = True
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Локація оновлена',
            'latitude': current_user.latitude,
            'longitude': current_user.longitude
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@nurse_bp.route('/toggle_online', methods=['POST'])
@login_required
def toggle_online():
    if current_user.role != 'nurse':
        return jsonify({'success': False, 'message': 'Доступ заборонено'}), 403
    
    try:
        current_user.online = not current_user.online
        db.session.commit()
        return jsonify({
            'success': True,
            'online': current_user.online
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@nurse_bp.route('/get_clients_locations')
@login_required
def get_clients_locations():
    if current_user.role != 'nurse':
        return jsonify({'error': 'Доступ заборонено'}), 403
    
    try:
        clients = User.query.filter(
            User.role == 'client',
            User.location_approved == True,
            User.latitude.isnot(None),
            User.longitude.isnot(None)
        ).all()
        
        clients_data = [{
            'id': client.id,
            'name': client.user_name,
            'lat': client.latitude,
            'lng': client.longitude
        } for client in clients]
        
        return jsonify(clients_data)
    except Exception as e:
        current_app.logger.error(f"Error getting clients locations: {str(e)}")
        return jsonify({'error': 'Помилка сервера'}), 500