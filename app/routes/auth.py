from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, current_user
from app. extensions import db, bcrypt
from app.models import User

auth_bp = Blueprint('auth',__name__)

@auth_bp.route('/register',methods = ['GET','POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))
    
    if request.method == "POST":
        username = request.form.get('username') # register.html -> form -> name = username
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password') 
        role = request.form.get('role')

        errors = []
        if not username or len(username) < 2:
            errors.append('Username must be at least 2 characters long')
        if not email or '@' not in email:
            errors.append('Invalid email address')
        if not password or len(password) < 6:
            errors.append('Password must be at least 6 characters long')
        if password != confirm_password:
            errors.append('Passwords do not match')
        if role not in ['client','nurse']:
            errors.append('Invalid role')
        
        if User.query.filter_by(username=username).first():
            errors.append('User already exists')
        if User.query.filter_by(email=email).first():
            errors.append('Email already exists')

        if errors:
            for e in errors:
                flash(e,'danger')
            else:
                hashed_password = bcrypt.generate_password_hash(password)
                user = User(
                    username = username,
                    email = email,
                    password = hashed_password,
                    role=role
                )

            db.session.add(user)
            db.session.commit()
            return redirect(url_for('auth.login'))
    return render_template('auth/register.html')

@auth_bp.route('/login',methods = ['GET','POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))
    
    if request.method == "POST":
        username = request.form.get('username') # register.html -> form -> name = username
        password = request.form.get('password')

        user= User.query.filter((User.email==username) or (User.user_name==username)).first()
        
        if user and bcrypt.check_password_hash(user.password,password):
            login_user(user)
            return redirect (url_for(f'{user.role}.dashboard'))
        
        
