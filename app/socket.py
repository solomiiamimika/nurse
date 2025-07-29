from app import socketio
from flask import current_app
from flask_socketio import join_room, leave_room,emit
from app.models import Message, db
from datetime import datetime

@socketio.on('connect')
def handle_connect():
    current_app.logger.info('Клієнт підключився')

@socketio.on('disconnect')
def handle_disconnect():
    current_app.logger.info('Клієнт відключився')

@socketio.on('join')
def handle_join(data):
    user_id = data.get('user_id')
    if user_id:
        join_room(user_id)
        current_app.logger.info(f'Користувач {user_id} приєднався до кімнати')

@socketio.on('send_message')
def handle_send_message(data):
    try:
        message = Message(
            sender_id=data['sender_id'],
            recipient_id=data['recipient'],
            text=data['text'],
            timestamp=datetime.utcnow()
        )
        db.session.add(message)
        db.session.commit()
        
        # Відправляємо повідомлення отримувачу
        emit('new_message', {
            'id': message.id,
            'sender_id': message.sender_id,
            'sender_name': message.sender.user_name,
            'text': message.text,
            'timestamp': message.timestamp.isoformat()
        }, room=f"user_{message.recipient_id}")
        
        # Підтвердження відправнику
        emit('message_sent', {
            'id': message.id,
            'status': 'delivered'
        }, room=f"user_{message.sender_id}")
        
    except Exception as e:
        emit('error', {'message': str(e)})