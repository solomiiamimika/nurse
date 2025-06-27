from .extensions import socket_io
from flask import current_app
from flask_socketio import join_room, leave_room
from .models import User, Message, db

@socket_io.on('join')
def join_chat(data):
    user_id=data['user_id']
    join_room(user_id)
    
@socket_io.on('send_message') 
def send_message(data):
    try:
        text=data['text']
        sender_id=data['sender_id']
        recipient_id = data['recipient']
        message=Message(sender_id=sender_id, recipient_id=recipient_id, text=text)
        db.session.add(message)
        db.session.commit()
        sender=User.query.get(sender_id)
        socket_io.emit('new_message',
                        {
                            'id':message.id,
                            'sender_id':sender_id,
                            'sender_name':sender.user_name,
                            'text':text,
                            'timestamp':message.timestamp
                        }, room=str(recipient_id)) 
        socket_io.emit('message_sent',{
            'message_id':message.id
        },room=str(sender_id))
        
    except Exception as e:
        current_app.logger.error(f"Error sending message: {str(e)}")
        socket_io.emit('error', {
            'message': 'Помилка відправки повідомлення'
        }, room=str(sender_id))



