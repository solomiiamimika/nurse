from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_user, logout_user, current_user
from app.extensions import db, bcrypt
from app.models import User
from . import auth_bp
from app.extensions import google_blueprint


@auth_bp.route('/register', methods=['GET','POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))
    
    if request.method == "POST":
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password') 
        role = request.form.get('role')

        errors = []
        if not username or len(username) < 2:
            errors.append('Username must be at least 2 characters long')
        if not email or '@' not in email:
            errors.append('Invalid email address')
        if password and len(password) < 6:  # Змінимо для Google-користувачів
            errors.append('Password must be at least 6 characters long')
        if password and password != confirm_password:
            errors.append('Passwords do not match')
        if role not in ['client','nurse']:
            errors.append('Invalid role')
        
        if User.query.filter_by(user_name=username).first():
            errors.append('User already exists')
        if User.query.filter_by(email=email).first():
            errors.append('Email already exists')

        if errors:
            for e in errors:
                flash(e,'danger')
        else:
            user = User(
                user_name=username,
                email=email,
                role=role
            )
            if password:  # Якщо це не Google-користувач
                user.password = password
            
            db.session.add(user)
            db.session.commit()
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('auth.login'))
    
    return render_template('auth/register.html')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))
    
    if request.method == "POST":
        username = request.form.get('username')
        password = request.form.get('password')

        user = User.query.filter((User.email == username) | (User.user_name == username)).first()
        
        if user and (user.verify_password(password) or user.google_id):
            login_user(user)
            flash('You have been logged in successfully!', 'success')
            return redirect(url_for(f'{user.role}.dashboard'))
        else:
            flash('Invalid username or password', 'danger')
    
    return render_template('auth/login.html')

@auth_bp.route("/google-login")
def google_login():
    if not google_blueprint.session.authorized:
        return redirect(url_for("google.login"))
    
    resp = google_blueprint.session.get("/oauth2/v2/userinfo")
    if not resp.ok:
        flash("Login failed with Google", "danger")
        return redirect(url_for("auth.login"))
    
    google_data = resp.json()
    
    # Перевіряємо чи користувач вже існує
    user = User.query.filter_by(google_id=google_data["id"]).first()
    
    if not user:
        # Перевіряємо чи email вже використовується
        user = User.query.filter_by(email=google_data["email"]).first()
        if user:
            # Прив'язуємо Google ID до існуючого акаунта
            user.google_id = google_data["id"]
            db.session.commit()
        else:
            # Створюємо нового користувача
            username = google_data["email"].split('@')[0]
            # Перевіряємо унікальність username
            counter = 1
            original_username = username
            while User.query.filter_by(user_name=username).first():
                username = f"{original_username}{counter}"
                counter += 1
            
            user = User(
                google_id=google_data["id"],
                email=google_data["email"],
                user_name=username,
                role='client',  # За замовчуванням
                online=True
            )
            db.session.add(user)
            db.session.commit()
    
    login_user(user)
    flash('You have been logged in with Google!', 'success')
    return redirect(url_for(f'{user.role}.dashboard'))

@auth_bp.route('/logout', methods=['GET', 'POST'])
def logout():
    # Додатково виходимо з Google
    if google_blueprint.session.authorized:
        token = google_blueprint.token["access_token"]
        google_blueprint.session.get(
            "https://accounts.google.com/o/oauth2/revoke",
            params={"token": token},
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        google_blueprint.token = None
    
    logout_user()
    return redirect(url_for('auth.login'))  
