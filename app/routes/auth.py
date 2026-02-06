from flask import render_template, redirect, url_for, flash, request, abort, Blueprint, session
from flask_login import login_user, logout_user, current_user,login_required
from app.extensions import db, bcrypt
from app.models import User,Review,Appointment,Message,Payment,ClientSelfCreatedAppointment

from app.extensions import google_blueprint
from app.supabase_storage import delete_from_supabase
import json
auth_bp = Blueprint('auth', __name__, template_folder='templates/auth')

@auth_bp.route('/register', methods=['GET','POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for(f'{current_user.role}.dashboard'))
    
    if request.method == "POST":
        username = request.form.get('username')
        fullname = request.form.get('full_name')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password') 
        role = request.form.get('role')

        errors = []
        if not username or len(username) < 2:
            errors.append('Username must be at least 2 characters long')
        if not email or '@' not in email:
            errors.append('Invalid email address')
        if password and len(password) < 6:  #We’ll update it for Google users.
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
                role=role,
                full_name=fullname
            )
            if password:  # If this is not a Google user
                user.password = password
            
            db.session.add(user)
            db.session.commit()
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('auth.login'))
    
    return render_template('auth/register.html')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    
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
    
    # Check if the user already exists
    user = User.query.filter_by(google_id=google_data["id"]).first()
    
    if not user:
        # Check if the email is already in use
        user = User.query.filter_by(email=google_data["email"]).first()
        if user:
            # Link the Google ID to an existing account
            user.google_id = google_data["id"]
            db.session.commit()
        else:
            # Create a new user
            username = google_data["email"].split('@')[0]
            # Check username uniqueness
            counter = 1
            original_username = username
            while User.query.filter_by(user_name=username).first():
                username = f"{original_username}{counter}"
                counter += 1
            
            user = User(
                google_id=google_data["id"],
                email=google_data["email"],
                user_name=username,
                role='client', 
                online=True
            )
            db.session.add(user)
            db.session.commit()
    
    login_user(user)
    flash('You have been logged in with Google!', 'success')
    return redirect(url_for(f'{user.role}.dashboard'))

@auth_bp.route('/logout', methods=['GET', 'POST'])
def logout():
    # Additionally, we sign out of Google.
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


@auth_bp.route('/delete_account', methods=['POST'])
@login_required
def delete_account():
    try:
        user_id = current_user.id
        
        # 1. Delete Supabase Files (Photo)
        if current_user.photo:
            try:
                delete_from_supabase(current_user.photo, 'profile_pictures')
            except Exception as e:
                print(f"Supabase photo error: {e}")

        # 2. Delete Supabase Files (Documents)
        if current_user.documents:
            try:
                documents = json.loads(current_user.documents)
                for i in documents:
                    delete_from_supabase(i, 'documents')
            except Exception as e:
                print(f"Supabase doc error: {e}")

        # 3. MANUALLY DELETE RELATED DATABASE RECORDS
        # We use .delete() directly on the query
        
        # A. Delete Reviews (written by user OR written about user)
        Review.query.filter(
            (Review.patient_id == user_id) | (Review.doctor_id == user_id)
        ).delete(synchronize_session=False)

        # B. Delete Appointments (as client OR as nurse)
        Appointment.query.filter(
            (Appointment.client_id == user_id) | (Appointment.nurse_id == user_id)
        ).delete(synchronize_session=False)

        # C. Delete Self-Created Requests
        ClientSelfCreatedAppointment.query.filter(
            (ClientSelfCreatedAppointment.patient_id == user_id) | (ClientSelfCreatedAppointment.doctor_id == user_id)
        ).delete(synchronize_session=False)

        # D. Delete Messages (sent OR received)
        Message.query.filter(
            (Message.sender_id == user_id) | (Message.recipient_id == user_id)
        ).delete(synchronize_session=False)
        
        # E. Delete Payments
        Payment.query.filter_by(user_id=user_id).delete(synchronize_session=False)

        # 4. Finally, Delete the User
        db.session.delete(current_user)
        db.session.commit()
        
        # 5. Logout
        logout_user()
        
        flash('Your account has been successfully deleted.', 'success')
        return redirect(url_for('auth.register')) # or main.index
        
    except Exception as e:
        db.session.rollback()
        print(f"Delete Error: {e}")
        flash(f'Error deleting account: {str(e)}', 'danger')
        return redirect(url_for('client.profile'))
    
@auth_bp.route('/set_language/<lang_code>')    
def set_language(lang_code):
        print(f"Setting language to: {lang_code}")
        session['lang'] = lang_code
        return redirect(request.referrer or url_for('main.index'))