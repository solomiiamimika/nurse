from flask import render_template, redirect, url_for, flash, request,abort,jsonify,current_app
from flask_login import login_user, logout_user, current_user, login_required
from app. extensions import db, bcrypt
from app.models import User
from . import nurse_bp


@nurse_bp.route('/dashboard')
@login_required
def dashboard():
    if current_user.role!='nurse':
        return redirect(url_for('auth.login'))
    return render_template('nurse/dashboard.html')
    

##################################3



@nurse_bp.route('/update_location', methods=['POST'])
@login_required
def update_location():
    if current_user.role != 'nurse':
        abort(403)
    
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
        abort(403)
    
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
        abort(403)
    
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
    
    
import os

@nurse_bp.route('/delete_document', methods=['POST'])
@login_required
def delete_document():
    if current_user.role != 'nurse':
        abort(403)

    filename = request.form.get('filename')
    if not filename:
        flash('Файл не вказано', 'danger')
        return redirect(url_for('nurse.dashboard'))

    # Шлях до документа
    folder_path = os.path.join(current_app.root_path, 'static', 'documents')
    file_path = os.path.join(folder_path, filename)

    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            flash(f'Файл "{filename}" успішно видалено.', 'success')
        else:
            flash(f'Файл "{filename}" не знайдено.', 'warning')
    except Exception as e:
        flash(f'Помилка при видаленні: {str(e)}', 'danger')

    return redirect(url_for('nurse.dashboard'))
    
    
@nurse_bp.route('/profile')
@login_required
def profile():
    if current_user.role != 'nurse':
        abort(403)

    # шлях до папки з документами
    documents_folder = os.path.join(current_app.root_path, 'static', 'documents')
    documents = os.listdir(documents_folder) if os.path.exists(documents_folder) else []

    # шлях до фото профілю (опціонально)
    photo = f"photo/{current_user.photo}" if current_user.photo else None

    return render_template('nurse/profile.html',
                           user=current_user,
                           documents=documents,
                           photo=photo)    