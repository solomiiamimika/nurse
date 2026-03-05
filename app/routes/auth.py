from flask import render_template, redirect, url_for, flash, request, abort, Blueprint, session, jsonify
from flask_login import login_user, logout_user, current_user,login_required
from app.extensions import db, bcrypt
from app.models import User,Review,Appointment,Message,Payment,ClientSelfCreatedAppointment,InvitationToken

from app.extensions import google_blueprint
from app.supabase_storage import delete_from_supabase
import json
import secrets
from datetime import datetime, timedelta

auth_bp = Blueprint('auth', __name__, template_folder='templates/auth')

def _generate_referral_code():
    """Генерує унікальний 8-символьний реферальний код."""
    while True:
        code = secrets.token_urlsafe(6)[:8].upper()
        if not User.query.filter_by(referral_code=code).first():
            return code


@auth_bp.route('/invite/<token>')
def invite_landing(token):
    """Лендінг для запрошень — показує опис додатку перед реєстрацією."""
    inv = InvitationToken.query.filter_by(token=token, used=False).first()

    if not inv:
        flash('This invitation link is invalid or has already been used.', 'danger')
        return redirect(url_for('auth.register'))

    if inv.expires_at and inv.expires_at < datetime.now():
        flash('This invitation link has expired.', 'danger')
        return redirect(url_for('auth.register'))

    return redirect(url_for('auth.register', invite=token, role=inv.role_hint or ''))


@auth_bp.route('/register', methods=['GET','POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for(f'{current_user.role}.dashboard'))

    # Токен запрошення та реферальний код з URL
    invite_token = request.args.get('invite') or request.form.get('invite_token')
    ref_code = request.args.get('ref') or request.form.get('ref_code')
    role_hint = request.args.get('role', '')

    # Валідуємо invite token якщо є
    invitation = None
    if invite_token:
        invitation = InvitationToken.query.filter_by(token=invite_token, used=False).first()
        if invitation and invitation.expires_at and invitation.expires_at < datetime.now():
            invitation = None

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
        if password and len(password) < 6:
            errors.append('Password must be at least 6 characters long')
        if password and password != confirm_password:
            errors.append('Passwords do not match')
        if role not in ['client', 'provider']:
            errors.append('Invalid role')

        if User.query.filter_by(user_name=username).first():
            errors.append('User already exists')
        if User.query.filter_by(email=email).first():
            errors.append('Email already exists')

        if errors:
            for e in errors:
                flash(e, 'danger')
        else:
            referred_by = None
            if ref_code:
                referrer = User.query.filter_by(referral_code=ref_code).first()
                if referrer:
                    referred_by = ref_code

            user = User(
                user_name=username,
                email=email,
                role=role,
                full_name=fullname,
                referral_code=_generate_referral_code(),
                referred_by=referred_by,
            )
            if password:
                user.password = password

            db.session.add(user)
            db.session.flush()

            # Позначити запрошення як використане
            if invitation:
                invitation.used = True
                invitation.used_by = user.id
                invitation.used_at = datetime.now()

            db.session.commit()
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('auth.login'))

    return render_template('auth/register.html',
                           invite_token=invite_token,
                           ref_code=ref_code,
                           role_hint=role_hint)


@auth_bp.route('/create_invite', methods=['POST'])
@login_required
def create_invite():
    """Будь-який юзер може створити посилання-запрошення."""
    data = request.get_json() or {}
    role_hint = data.get('role')        # 'provider' | 'client' | None
    email_hint = data.get('email')      # необов'язково
    expires_days = data.get('expires_days')  # None = безстроково

    if role_hint and role_hint not in ('provider', 'client'):
        return jsonify({'success': False, 'message': 'Invalid role'}), 400

    token = secrets.token_urlsafe(32)
    expires_at = None
    if expires_days:
        expires_at = datetime.now() + timedelta(days=int(expires_days))

    inv = InvitationToken(
        token=token,
        created_by=current_user.id,
        role_hint=role_hint,
        email_hint=email_hint,
        expires_at=expires_at,
    )
    db.session.add(inv)
    db.session.commit()

    invite_url = url_for('auth.invite_landing', token=token, _external=True)
    return jsonify({'success': True, 'url': invite_url, 'token': token})


@auth_bp.route('/my_referrals')
@login_required
def my_referrals():
    """Статистика рефералів поточного юзера."""
    referrals = User.query.filter_by(referred_by=current_user.referral_code).all()
    invites = InvitationToken.query.filter_by(created_by=current_user.id).order_by(
        InvitationToken.created_at.desc()
    ).all()

    return jsonify({
        'referral_code': current_user.referral_code,
        'referral_url': url_for('auth.register', ref=current_user.referral_code, _external=True),
        'total_referred': len(referrals),
        'referred_users': [
            {'id': u.id, 'user_name': u.user_name, 'role': u.role,
             'joined': u.created_at.isoformat()}
            for u in referrals
        ],
        'invites_sent': len(invites),
        'invites': [
            {'token': i.token,
             'url': url_for('auth.invite_landing', token=i.token, _external=True),
             'role_hint': i.role_hint,
             'used': i.used,
             'expires_at': i.expires_at.isoformat() if i.expires_at else None,
             'created_at': i.created_at.isoformat()}
            for i in invites
        ]
    })

@auth_bp.route('/invite_manager')
@login_required
def invite_manager():
    invites = InvitationToken.query.filter_by(created_by=current_user.id).order_by(
        InvitationToken.created_at.desc()
    ).all()
    referrals = User.query.filter_by(referred_by=current_user.referral_code).all()
    referral_url = url_for('auth.register', ref=current_user.referral_code, _external=True)
    return render_template('auth/invite_manager.html',
                           invites=invites,
                           referrals=referrals,
                           referral_url=referral_url,
                           now=datetime.now)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    
    if request.method == "POST":
        username = request.form.get('username')
        password = request.form.get('password')

        user = User.query.filter((User.email == username) | (User.user_name == username)).first()
        
        if user and (user.verify_password(password) or user.google_id):
            if not user.is_active:
                flash('Your account has been deactivated. Contact support.', 'danger')
                return redirect(url_for('auth.login'))
            login_user(user)
            flash('You have been logged in successfully!', 'success')
            if user.is_owner:
                return redirect(url_for('owner.dashboard'))
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
            role= session.get('google_role', 'client') # Default to 'client' if not set

            session.pop('google_role', None)  # Clear the temporary role from session
            password = secrets.token_urlsafe(16)  # Generate a random password for Google users (not used for login)
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
                role=role, 
                online=True,
                password_hash = password, #bcrypt.generate_password_hash(password).decode('utf-8')
                full_name=google_data.get("name", "")
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
            (Review.patient_id == user_id) | (Review.provider_id == user_id)
        ).delete(synchronize_session=False)

        # B. Delete Appointments (as client OR as provider)
        Appointment.query.filter(
            (Appointment.client_id == user_id) | (Appointment.provider_id == user_id)
        ).delete(synchronize_session=False)

        # C. Delete Self-Created Requests
        ClientSelfCreatedAppointment.query.filter(
            (ClientSelfCreatedAppointment.patient_id == user_id) | (ClientSelfCreatedAppointment.provider_id == user_id)
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

@auth_bp.route('/change_password', methods=['POST'])
@login_required
def change_password():
    current_pw = request.form.get('current_password', '')
    new_pw = request.form.get('new_password', '')
    confirm = request.form.get('confirm_password', '')

    # Google-only users have a raw token as password_hash (not a bcrypt hash)
    is_google_only = bool(current_user.google_id) and not (
        current_user.password_hash and current_user.password_hash.startswith('$2')
    )

    if is_google_only:
        flash('You signed in with Google. Password change is not available.', 'danger')
    elif not current_user.verify_password(current_pw):
        flash('Current password is incorrect.', 'danger')
    elif new_pw != confirm:
        flash('New passwords do not match.', 'danger')
    elif len(new_pw) < 6:
        flash('Password must be at least 6 characters.', 'danger')
    else:
        current_user.password = new_pw
        db.session.commit()
        flash('Password updated successfully!', 'success')

    return redirect(url_for(f'{current_user.role}.profile'))


@auth_bp.route('/google_role/<role>')
def google_role(role):
    if role not in ['client', 'provider']:
        flash('Invalid role selection', 'danger')
        return redirect(url_for('auth.register'))
    
    session['google_role'] = role
    return redirect(url_for('google.login'))



