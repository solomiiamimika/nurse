from app import create_app
from app.extensions import db
from app.models import User,Message,Service,Appointment,Payment,MedicalRecord,Prescription,Review

app = create_app()
if __name__ == '__main__':
    app.run(host='localhost', port=5000, ssl_context=None, debug=True)