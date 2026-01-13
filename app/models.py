from .extensions import db, bcrypt, login_manager
from flask_login import UserMixin
from sqlalchemy import Column, Integer, Text, Boolean, DateTime, ForeignKey, Float, String, Date
from sqlalchemy.orm import relationship
from datetime import datetime
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy import func

    

class User(db.Model, UserMixin):
    __tablename__ ='user'
    id = Column(Integer, primary_key=True)
    user_name = Column(Text, unique=True, nullable=False, name='uq_user_user_name')
    email = Column(Text(), unique=True, nullable=False, name='uq_user_email')

    password_hash = Column(Text, nullable=False)
    
    google_id = Column(String(100), unique=True, nullable=True)
    latitude = Column(Float) 
    longitude = Column(Float) 

    location_approved = Column(Boolean,default = False)


    role = Column(Text)
    
    photo = Column(String)
    full_name = Column(String)
    documents = Column(Text)
    phone_number = Column(String)
    date_birth = Column(Date)
    about_me = Column(String)
    address = Column(String)
    

    created_at = Column(DateTime, default=datetime.now)
    online= Column(Boolean)
    
    reviews_received = db.relationship('Review', 
                                     foreign_keys='Review.doctor_id', 
                                     backref='nurse_profile', 
                                     lazy=True)
    sent_messages = db.relationship('Message', 
                                  foreign_keys='Message.sender_id', 
                                  backref='sender', 
                                  lazy=True,cascade = 'all, delete-orphan')
    
    received_messages = db.relationship('Message', 
                                      foreign_keys='Message.recipient_id', 
                                      backref='recipient', 
                                      lazy=True,cascade = 'all, delete-orphan')
    
    client_appointments = db.relationship('Appointment', foreign_keys='Appointment.client_id', backref='client', lazy=True,cascade = 'all, delete-orphan')
    nurse_appointments = db.relationship('Appointment', foreign_keys='Appointment.nurse_id', backref='nurse', lazy=True,cascade = 'all, delete-orphan')
    payments = db.relationship('Payment', backref='user', lazy=True, cascade = 'all, delete-orphan')
    
    
    @property
    def average_rating(self):
        if not self.reviews_received:
            return 0.0
        

        total = sum(r.rating for r in self.reviews_received)
        

        return round(total / len(self.reviews_received), 1)
    @property
    def review_count(self):
        return len(self.reviews_received)
    @property
    def password(self):
        raise AttributeError('password is not a readable attribute')
    
    @password.setter
    def password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
    
    def verify_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)
    
class Message (db.Model):
    __tablename__ = 'message'
    id = Column (Integer, primary_key=True)
    sender_id = Column(Integer,ForeignKey('user.id',name='fk_message_sender'))
    recipient_id=Column(Integer,ForeignKey('user.id',name='fk_message_recipient'))
    text = Column(Text)
    timestamp=Column(DateTime,default=datetime.now)
    is_read = Column(Boolean,default=False)
    
    
    message_type = Column(String , default='text') # audio,video,photo
    supabase_file_path = Column(String)
    mime_type = Column(String)
    file_name = Column(String)
    file_size = Column(Integer)

class Service(db.Model):
    __tablename__ = 'service'
    id= Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    base_price = Column(Float, nullable=False)
    base_duration = Column(Integer, nullable=False)
    is_standart = Column(Boolean,default = True)
    
    nurse_services = relationship('NurseService',backref='base_service',lazy=True)

    
    
    
    
    
    
    
class NurseService(db.Model):
    __tablename__ = 'nurse_service'
    id= Column(Integer, primary_key=True)
    name = db.Column(db.String(100)) 
    nurse_id = Column(Integer,ForeignKey('user.id'),nullable = False)
    service_id = Column(Integer,ForeignKey('service.id'),nullable = True)
    price = Column(Float, nullable=False)
    duration = Column(Integer, nullable=False)
    is_available = Column(Boolean,default = True)
    description = Column(Text)
    
    appointments = relationship('Appointment', backref='nurse_service', lazy=True)








class Appointment(db.Model):
    __tablename__ = 'appointment'
    id = Column (Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey('user.id'), nullable=False)
    nurse_id = Column(Integer, ForeignKey('user.id'), nullable=False)
    nurse_service_id = Column(Integer, ForeignKey('nurse_service.id'), nullable=False)
    appointment_time = Column (DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    status = Column(String(20), default='scheduled') # scheduled, completed, canceled
    notes = Column(Text)
    payment = relationship('Payment', backref='appointment', uselist=False)

class Payment (db.Model):
    __tablename__='payment'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey ('user.id'), nullable=False)
    appointment_id = Column(Integer, ForeignKey('appointment.id'), nullable=False)
    amount = Column(Float, nullable=False)
    payment_date = Column(DateTime, default=datetime.now)
    status = Column (String(20), default='pending') # pending, completed, failed    
    transaction_id = Column(String(50))
    payment_method = Column(String(50))
    

            

class MedicalRecord(db.Model):
    __tablename__ = 'medical_record'
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey('user.id'), nullable=False)
    diagnosis = Column(Text, nullable=False)
    treatment = Column(Text)
    record_date = Column(DateTime, default=datetime.now)

    client = relationship('User', foreign_keys=[client_id])

class Prescription(db.Model):
    __tablename__ = 'prescription'
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey('user.id'), nullable=False)
    doctor_id = Column(Integer, ForeignKey('user.id'), nullable=False)
    
    appointment_id = Column(Integer, ForeignKey('appointment.id'))
    medication_name = Column(Text)
    dosage = Column(Text)
    instructions = Column(Text)
    created_at = Column(DateTime, default=datetime.now)

    patient = relationship('User', foreign_keys=[patient_id])
    doctor = relationship('User', foreign_keys=[doctor_id])

class Review(db.Model):
    __tablename__ = 'review'
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey('user.id'), nullable=False)  # who left the review
    doctor_id = Column(Integer, ForeignKey('user.id'), nullable=False)   # whom they left it for
    appointment_id = Column(Integer,ForeignKey('appointment.id'),nullable=False)
    rating = Column(Integer, nullable=False)  #rating (e.g., from 1 to 5)
    comment = Column(Text)                   # text comment
    created_at = Column(DateTime, default=datetime.now)    

    patient = relationship('User', foreign_keys=[patient_id])
    doctor = relationship('User', foreign_keys=[doctor_id])
    
    @hybrid_property
    def average_nurse_rating(self):
        return db.session.query(func.avg(Review.rating)).filter(Review.doctor_id == self.id).scalar() or 0
    @hybrid_property
    def reviews_nurse_count(self):
        return Review.query.filter_by(doctor_id = self.id).count()
        
    


class ClientSelfCreatedAppointment(db.Model):
    __tablename__= 'client_self_create_appointment'
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey('user.id'), nullable=False)  # who left the review
    doctor_id = Column(Integer, ForeignKey('user.id'), nullable=True)   # whom they left it for
    appointment_start_time = Column (DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    status = Column(String(20), default='scheduled') # scheduled, completed, canceled
    notes = Column(Text)
    payment = Column(Float)
    nurse_service_id = Column(Integer,ForeignKey('nurse_service.id'),nullable = True)
    service_name=Column(String, nullable=True)
    service_description =Column(Text, nullable=True)
    latitude = Column(Float) 
    longitude = Column(Float) 
    created_appo = Column(DateTime, default=datetime.now)
    
    patient = relationship('User', foreign_keys=[patient_id])
    doctor = relationship('User', foreign_keys=[doctor_id])
    nurse_service = relationship('NurseService')
    

    
    

    