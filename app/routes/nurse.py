from flask import render_template, redirect, url_for, flash, request,abort,jsonify
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
    
    data = request.get_json()
    if not data or 'latitude' not in data or 'longitude' not in data:
        return jsonify({'success': False, 'message': 'Invalid data'}), 400
    
    current_user.latitude = data['latitude']
    current_user.longtitude = data['longitude']
    current_user.location_approved = True
    db.session.commit()
    
    return jsonify({'success': True})

@nurse_bp.route('/toggle_online', methods=['POST'])
@login_required
def toggle_online():
    if current_user.role != 'nurse':
        abort(403)
    
    current_user.online = not current_user.online
    db.session.commit()
    
    return jsonify({'success': True, 'online': current_user.online})