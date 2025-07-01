from flask import render_template, redirect, url_for, flash, request,abort,jsonify,current_app
from flask_login import login_user, logout_user, current_user, login_required
from app. extensions import db, bcrypt
from app.models import User
from . import client_bp
from datetime import datetime
import os 
from werkzeug.utils import secure_filename
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'app', 'static', 'uploads')
DOCUMENTS_FOLDER = os.path.join(UPLOAD_FOLDER, 'documents')
PROFILE_PICTURES_FOLDER = os.path.join(UPLOAD_FOLDER, 'profile_pictures')


os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DOCUMENTS_FOLDER, exist_ok=True)
os.makedirs(PROFILE_PICTURES_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@client_bp.route('/dashboard')
@login_required
def dashboard():
    if current_user.role!='client':
        return redirect(url_for('auth.login'))
    return render_template('client/dashboard.html')





#################################################33

@client_bp.route('/update_location', methods=['POST'])
@login_required
def update_location():
    if current_user.role != 'client':
        abort(403)
    
    try:
        data = request.get_json()
        if not data or 'latitude' not in data or 'longitude' not in data:
            return jsonify({'success': False, 'message': 'Необхідно надати latitude та longitude'}), 400
        
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

@client_bp.route('/get_nurses_locations')
@login_required
def get_nurses_locations():
    if current_user.role != 'client':
        abort(403)
    
    try:
        nurses = User.query.filter(
            User.role == 'nurse',
            User.location_approved == True,
            User.latitude.isnot(None),
            User.longitude.isnot(None)
        ).all()
        
        nurses_data = [{
            'id': nurse.id,
            'name': nurse.user_name,
            'lat': nurse.latitude,
            'lng': nurse.longitude,
            'online': nurse.online if nurse.online is not None else False
        } for nurse in nurses]
        
        return jsonify(nurses_data)
    
    except Exception as e:
        current_app.logger.error(f"Error getting nurses locations: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500
    
    
@client_bp.route('/profile', methods = ['GET', ' POST'])
@login_required
def profile():
    if request.method == 'POST':
        try:
            current_user.full_name=request.form.get('full_name')
            current_user.phone_number=request.form.get('phone_number')
            current_user.about_me=request.form.get('about_me')
            current_user.address=request.form.get('address')
            date_birth=request.form.get('date_birth')
            if date_birth:
                current_user.date_birth=datetime.strptime(date_birth, '%Y-%m-%d').date()
                
            if 'profile_picture' in request.files:
                file = request.files['profile_picture']
                if file and allowed_file(file.filename):
                    filename = secure_filename(f"user_{current_user.id}_{datetime.now().timestamp()}.{file.filename.rsplit('.', 1)[1].lower()}")
                    file_path = os.path.join(PROFILE_PICTURES_FOLDER, filename)
                    file.save(file_path)
                    current_user.photo = filename
                    
            existing_docs = json.loads(current_user.documents) if current_user.documents else []        
                        
            if 'documents' in request.files:
                documents = request.files.getlist('documents')
                 
                for doc in documents:
                    if doc and doc.filename:
                        filename = secure_filename(f"user_{current_user.id}_doc_{datetime.now().timestamp()}_{doc.filename}")
                       
                        file_path = os.path.join(DOCUMENTS_FOLDER, filename)
                        doc.save(file_path)
                        existing_docs.append(filename)
            
               
                current_user.documents=json.dumps(existing_docs)              
            
            
            db.session.commit()  
            flash('Профіль успішно оновлено!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Помилка при оновленні профілю: {str(e)}', 'danger')
        
        return redirect(url_for('client.profile'))
    
    existing_docs = json.loads(current_user.documents) if current_user.documents else []
    formatted_date = current_user.date_birth.strftime('%Y-%m-%d') if current_user.date_birth else ''
    user_documents = json.loads(current_user.documents) if current_user.documents else []
    
    return render_template('client/profile.html', 
                         user=current_user, 
                         formatted_date=formatted_date,
                         user_documents=user_documents) 
    
    
@client_bp.route('/delete_document', methods=['POST'])
@login_required
def delete_document():
    filename = request.form.get('filename')
    if not filename:
        return jsonify({'success': False, 'message': 'Файл не вказано'}), 400

    file_path = os.path.join(DOCUMENTS_FOLDER, filename)

    try:
        if os.path.exists(file_path):
            os.remove(file_path)
        else:
            return jsonify({'success': False, 'message': 'Файл не знайдено'}), 404

        existing_docs = json.loads(current_user.documents) if current_user.documents else []
        if filename in existing_docs:
            existing_docs.remove(filename)
            current_user.documents = json.dumps(existing_docs)
            db.session.commit()

        return jsonify({'success': True, 'message': f'Файл "{filename}" успішно видалено'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Помилка: {str(e)}'}), 500

    
    

    
            
            
            
       
