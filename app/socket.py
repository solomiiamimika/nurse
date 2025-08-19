from app.extensions import socketio, db
from flask import current_app, request
from flask_socketio import join_room, leave_room, emit
from app.models import Message, db,User
from datetime import datetime


@socketio.on('connect')
def handle_connect():
    print(f"Клієнт підключився: {request.sid}")
    emit('connection_response', {'status': 'connected'})

@socketio.on('disconnect')
def handle_disconnect():
    print(f"Клієнт відключився: {request.sid}")

@socketio.on('join')
def handle_join(data):
    user_id = data.get('user_id')
    if user_id:
        join_room(f"user_{user_id}")
        current_app.logger.info(f'Користувач {user_id} приєднався до кімнати')

@socketio.on('send_message')
def handle_send_message(data):
    try:
        print(f"Отримано дані: {data}")  # Логування вхідних даних
        
        if not all(key in data for key in ['text', 'sender_id', 'recipient_id']):
            raise ValueError("Недостатньо даних")
            
        # Створення повідомлення
        message = Message(
            sender_id=int(data['sender_id']),
            recipient_id=int(data['recipient_id']),
            text=data['text']
        )
        
        # Збереження в БД
        db.session.add(message)
        db.session.commit()
        
        # Отримання імені відправника
        sender = User.query.get(message.sender_id)
        sender_name = sender.user_name if sender else "Невідомий"
        
        # Відправка отримувачу
        emit('new_message', {
            'id': message.id,
            'sender_id': message.sender_id,
            'sender_name': sender_name,
            'text': message.text,
            'timestamp': message.timestamp.isoformat()
        }, room=f"user_{message.recipient_id}")
        
        # Підтвердження відправнику
        emit('message_sent', {
            'id': message.id,
            'status': 'delivered'
        }, room=request.sid)
        
    except Exception as e:
        print(f"Помилка: {str(e)}")
        emit('error', {'message': str(e)}, room=request.sid)
        db.session.rollback()