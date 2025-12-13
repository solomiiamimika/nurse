from app.extensions import socketio, db
from flask import current_app, request
from flask_socketio import join_room, leave_room, emit
from app.models import Message, db,User
from datetime import datetime


@socketio.on('connect')
def handle_connect():
    print(f"The client connected: {request.sid}")
    emit('connection_response', {'status': 'connected'})

@socketio.on('disconnect')
def handle_disconnect():
    print(f"The client disconnected: {request.sid}")

@socketio.on('join')
def handle_join(data):
    user_id = data.get('user_id')
    if user_id:
        join_room(f"user_{user_id}")
        current_app.logger.info(f'User {user_id} joined the room.')

@socketio.on('send_message')
def handle_send_message(data):
    try:
        print(f"Received data: {data}")  # Logging incoming data
        
        if not all(key in data for key in ['text', 'sender_id', 'recipient_id']):
            raise ValueError("Insufficient data provided.")
            
        # Creating a message
        message = Message(
            sender_id=int(data['sender_id']),
            recipient_id=int(data['recipient_id']),
            text=data['text']
        )
        
        # Saving to the database
        db.session.add(message)
        db.session.commit()
        
        # Retrieving the sender’s name
        sender = User.query.get(message.sender_id)
        sender_name = sender.user_name if sender else "Unknown"
        
        # Sending to the recipient
        emit('new_message', {
            'id': message.id,
            'sender_id': message.sender_id,
            'sender_name': sender_name,
            'text': message.text,
            'timestamp': message.timestamp.isoformat()
        }, room=f"user_{message.recipient_id}")
        
        # Confirmation to the sender
        emit('message_sent', {
            'id': message.id,
            'status': 'delivered'
        }, room=request.sid)
        
    except Exception as e:
        print(f"Error: {str(e)}")
        emit('error', {'message': str(e)}, room=request.sid)
        db.session.rollback()