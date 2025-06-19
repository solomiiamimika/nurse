from .extensions import db, bcrypt, login_manager
from flask_login import UserMixin
from sqlalchemy import Column, Integer, Text, Boolean, DateTime, ForeignKey, Float, String
from sqlalchemy.orm import relationship
from datetime import datetime


class User(db.Model, UserMixin):
    __tablename__ = 'user'
    id = Column(Integer, primary_key=True)
    user_name = Column(Text, unique=True, nullable=False)
    email = Column(Text(), unique=True, nullable=False)
    password = Column(Text, nullable=False)

    role = Column(Text)

    created_at = Column(DateTime, default=datetime.now)
    online= Column(Boolean)
    

    messages_sent = db.relationship('Message', foreign_keys='Message.sender_id', backref='sender', lazy=True)
    messages_received = db.relationship('Message', foreign_keys='Message.recipient_id', backref='recipient', lazy=True)
    client_appointments = db.relationship('Appointment', foreign_keys='Appointment.client_id', backref='client', lazy=True)
    nurse_appointments = db.relationship('Appointment', foreign_keys='Appointment.nurse_id', backref='nurse', lazy=True)
    payments = db.relationship('Payment', backref='user', lazy=True)
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
    sender_id = Column(Integer,ForeignKey('user.id'))
    receiver_id=Column(Integer,ForeignKey('user.id'))
    text = Column(Text)
    timestamp=Column(DateTime,default=datetime.now)
    is_read = Column(Boolean,default=False)

class Service(db.Model):
    __tablename__ = 'service'
    id= Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    price = Column(Float, nullable=False)
    duration = Column(Integer, nullable=False)
    appointments = relationship('Appointment', backref='service', lazy=True)

class Appointment(db.Model):
    __tablename__ = 'appointment'
    id = Column (Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey('user.id'), nullable=False)
    nurse_id = Column(Integer, ForeignKey('user.id'), nullable=False)
    service_id = Column(Integer, ForeignKey('service.id'), nullable=False)
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
    patient_id = Column(Integer, ForeignKey('user.id'), nullable=False)  # хто залишив відгук
    doctor_id = Column(Integer, ForeignKey('user.id'), nullable=False)   # кому залишив
    rating = Column(Integer, nullable=False)  # оцінка, напр. від 1 до 5
    comment = Column(Text)                   # текстовий коментар
    created_at = Column(DateTime, default=datetime.now)    

    patient = relationship('User', foreign_keys=[patient_id])
    doctor = relationship('User', foreign_keys=[doctor_id])



