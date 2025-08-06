from app import create_app
from app.extensions import db,socketio
from app.models import User,Message,Service,Appointment,Payment,MedicalRecord,Prescription,Review
from pyngrok import ngrok
ngrok.set_auth_token('30Y5lts3TU8tBYOQ5g0CAxupy09_5M8qwijjkLXatMoCjpjbT')
app = create_app()
if __name__ == '__main__':
    # URL=ngrok.connect(5000).public_url
    # print(URL)
    # app.run(port=5000,debug=True)
    socketio.run(app,host='localhost', port=5000, ssl_context=None, debug=True)
    c
