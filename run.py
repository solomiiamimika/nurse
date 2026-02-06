from app import create_app
from app.extensions import db,socketio
from app.models import User,Message,Service,Appointment,Payment,MedicalRecord,Prescription,Review
from pyngrok import ngrok
from flask_socketio import SocketIO
import os

ngrok.set_auth_token('30Y5lts3TU8tBYOQ5g0CAxupy09_5M8qwijjkLXatMoCjpjbT')
os.environ['OAUTHLIB_INSECURE_TRANSOPRT'] = "1"
app = create_app()

if __name__ == '__main__':
    host = "127.0.0.1"
    port = 5000
    url = f"http://{host}:{port}"
    print(">>> SocketIO async_mode:", socketio.async_mode)
    print(f"🚀 Server running at {url}")
    print("Press CTRL+C to quit")
    # URL=ngrok.connect(5000).public_url
    # print(URL)
    # app.run(port=5000,debug=True)
    socketio.run(app, host="127.0.0.1", port=5000, debug=True)


