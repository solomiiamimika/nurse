from app import socketio
from flask import current_app
from flask_socketio import join_room, leave_room
from app.models import Message, db
from datetime import datetime

@socketio.on('connect')
def handle_connect():
    try:
        db.session.begin()
        current_app.logger.info('Клієнт підключився')
    except Exception as e:
        current_app.logger.error(f"Помилка при підключенні: {str(e)}")

@socketio.on('disconnect')
def handle_disconnect():
    try:
        db.session.remove()
        current_app.logger.info('Клієнт відключився')
    except Exception as e:
        current_app.logger.error(f"Помилка при відключенні: {str(e)}")

@socketio.on('join')
def handle_join(data):
    user_id = data.get('user_id')
    if user_id:
        join_room(user_id)
        current_app.logger.info(f'Користувач {user_id} приєднався до кімнати')

@socketio.on('send_message')
def handle_send_message(data):
    try:
        text = data.get('text')
        sender_id = data.get('sender_id')
        recipient_id = data.get('recipient')
        
        if not all([text, sender_id, recipient_id]):
            socketio.emit('error', {'message': 'Недостатньо даних'}, room=sender_id)
            return
        
        current_app.logger.info(f"Спроба зберегти повідомлення від {sender_id} до {recipient_id}: {text}")
        
        message = Message(
            sender_id=sender_id,
            recipient_id=recipient_id,
            text=text,
            timestamp=datetime.now(),
            is_read=False
        )
        
        db.session.add(message)
        db.session.commit()  
        

        saved_message = Message.query.get(message.id)
        if not saved_message:
            current_app.logger.error("Повідомлення не збереглося в базі!")
            raise Exception("Повідомлення не збереглося")
        
        socketio.emit('new_message', {
            'id': message.id,
            'sender_id': sender_id,
            'sender_name': message.sender.user_name,
            'text': text,
            'timestamp': message.timestamp.isoformat()
        }, room=recipient_id)
        
        socketio.emit('message_sent', {
            'message_id': message.id,
            'timestamp': message.timestamp.isoformat()
        }, room=sender_id)
        
    except Exception as e:
        db.session.rollback()  
        current_app.logger.error(f"Помилка відправки повідомлення: {str(e)}", exc_info=True)
        socketio.emit('error', {
            'message': 'Помилка відправки повідомлення'
        }, room=data.get('sender_id'))