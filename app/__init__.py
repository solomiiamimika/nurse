from flask import Flask
from .extensions import db,bcrypt,login_manager,migrate,socket_io
from app.models import User,Message,Service,Appointment,Payment,MedicalRecord,Prescription,Review
def create_app():
    app=Flask(__name__)
    app.config['SECRET_KEY'] =  'dev-secret-key'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///mobile_nurse.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
 
    # Ініціалізація розширень
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    socket_io.init_app(app)
    with app.app_context():
        db.create_all()
    return app




