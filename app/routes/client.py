from flask import render_template, redirect, url_for, flash, request,abort,jsonify,current_app
from flask_login import login_user, logout_user, current_user, login_required
from app. extensions import db, bcrypt
from app.models import User
from . import client_bp


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