from flask import render_template, redirect, url_for, flash, request,abort,jsonify,current_app
from flask_login import login_user, logout_user, current_user, login_required
from app. extensions import db, bcrypt
from app.models import User,Message
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
@client_bp.route('/get_nurses_locations')
@login_required
def get_nurses_locations():
    if current_user.role != 'client':
        return jsonify({'error': 'Доступ заборонено'}), 403
    
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
        'online': nurse.online
    } for nurse in nurses]
    
    return jsonify(nurses_data)

@client_bp.route('/profile')
@login_required
def profile():
    if current_user.role != 'client':
        return redirect(url_for('auth.login'))
    return render_template('client/profile.html')


@client_bp.route('/get_chat_messages')
@login_required
def get_chat_messages():
    if current_user.role != 'client':
        return jsonify({'error': 'Доступ заборонено'}), 403
    
    recipient_id = request.args.get('recipient_id')
    if not recipient_id:
        return jsonify({'error': 'Не вказано отримувача'}), 400
    
    messages = Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.recipient_id == recipient_id)) |
        ((Message.sender_id == recipient_id) & (Message.recipient_id == current_user.id))
    ).order_by(Message.timestamp.asc()).all()
    
    messages_data = [{
        'id': msg.id,
        'sender_id': msg.sender_id,
        'sender_name': msg.sender.user_name if msg.sender_id != current_user.id else 'Ви',
        'text': msg.text,
        'timestamp': msg.timestamp.isoformat()
    } for msg in messages]
    
    return jsonify(messages_data)