from flask import render_template, redirect, url_for, flash, request, abort, Blueprint, session, jsonify, current_app
from flask_login import login_user, logout_user, current_user, login_required
from app.extensions import db, bcrypt, mail
from app.models import User, Review, Appointment, Message, Payment, ClientSelfCreatedAppointment, InvitationToken, RequestOfferResponse, ServiceHistory, Favorite, FavoriteShareToken, DeletedAccount
from app.models.appointment import NoShowRecord, Dispute
from app.models.feedback import Feedback

from app.extensions import google_blueprint
from app.supabase_storage import delete_from_supabase
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from flask_mail import Message as MailMessage
from threading import Thread
import json
import os
import secrets
from datetime import datetime, date, timedelta

auth_bp = Blueprint('auth', __name__, template_folder='templates/auth')


# ── Token helpers (password reset & email verification) ───────────

def _get_serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'])


def _generate_token(user_id, salt='password-reset'):
    return _get_serializer().dumps(user_id, salt=salt)


def _verify_token(token, salt='password-reset', max_age=3600):
    try:
        return _get_serializer().loads(token, salt=salt, max_age=max_age)
    except (SignatureExpired, BadSignature):
        return None


def _send_async_email(app, msg):
    with app.app_context():
        try:
            mail.send(msg)
        except Exception as e:
            app.logger.error(f"Email send error: {e}")

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
        dob_str = request.form.get('date_of_birth')
        parent_email = request.form.get('parent_email', '').strip()

        errors = []
        if not username or len(username) < 2:
            errors.append('Username must be at least 2 characters long')
        if not email or '@' not in email:
            errors.append('Invalid email address')
        if not password or len(password) < 8:
            errors.append('Password must be at least 8 characters long')
        if password and password != confirm_password:
            errors.append('Passwords do not match')
        if role not in ['client', 'provider']:
            errors.append('Invalid role')

        # Age validation
        user_dob = None
        user_age = None
        is_young = False
        if dob_str:
            try:
                user_dob = date.fromisoformat(dob_str)
                today = date.today()
                user_age = today.year - user_dob.year - (
                    (today.month, today.day) < (user_dob.month, user_dob.day)
                )
            except ValueError:
                errors.append('Invalid date of birth')

        if user_age is not None and user_age < 13:
            errors.append('You must be at least 13 years old to register.')
        elif user_age is not None and user_age < 18:
            is_young = True
            if not parent_email or '@' not in parent_email:
                errors.append('Parent/guardian email is required for users under 18.')
            if parent_email and parent_email.lower() == email.lower():
                errors.append('Parent email must be different from your email.')

        if User.query.filter_by(user_name=username).first():
            errors.append('User already exists')
        if User.query.filter_by(email=email).first():
            errors.append('Email already exists')

        # Scam protection: check if email was previously deleted as provider
        if role == 'provider':
            prev_deleted = DeletedAccount.query.filter_by(email=email, role='provider').first()
            if prev_deleted:
                errors.append('This email was previously used by a deleted provider account. Please contact support.')

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
                roles=json.dumps([role]),
                full_name=fullname,
                date_birth=user_dob,
                referral_code=_generate_referral_code(),
                referred_by=referred_by,
                terms_accepted=True,
            )

            if is_young:
                consent_token = secrets.token_urlsafe(48)
                user.is_young_helper = True
                user.parent_email = parent_email
                user.parent_consent_status = 'pending'
                user.parent_consent_token = consent_token

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

            # Send email verification
            try:
                token = _generate_token(user.id, salt='email-verify')
                verify_url = url_for('auth.verify_email', token=token, _external=True)
                msg = MailMessage(
                    subject='Verify your email — Human-me',
                    sender=os.getenv('MAIL_DEFAULT_SENDER'),
                    recipients=[user.email],
                    body=(
                        f"Hi {user.full_name or user.user_name},\n\n"
                        f"Please verify your email by clicking:\n{verify_url}\n\n"
                        f"This link expires in 24 hours.\n\n"
                        f"— The Human-me Team"
                    )
                )
                app_obj = current_app._get_current_object()
                Thread(target=_send_async_email, args=(app_obj, msg)).start()
            except Exception:
                pass

            # Send parental consent email for young helpers
            if is_young and parent_email:
                try:
                    consent_url = url_for('auth.parent_consent', token=user.parent_consent_token, _external=True)
                    consent_msg = MailMessage(
                        subject='Parental Consent Required — Human-me',
                        sender=os.getenv('MAIL_DEFAULT_SENDER'),
                        recipients=[parent_email],
                        body=(
                            f"Hello,\n\n"
                            f"{user.full_name or user.user_name} (age {user_age}) has registered on Human-me "
                            f"as a Young Helper.\n\n"
                            f"Under German youth labour law (JArbSchG), minors aged 13-17 need parental consent "
                            f"to offer services on our platform.\n\n"
                            f"If you approve, please click the link below:\n"
                            f"{consent_url}\n\n"
                            f"Restrictions for Young Helpers:\n"
                            f"- Age 13-14: max 2 hours/day, light work only\n"
                            f"- Age 15-17: max 8 hours/day, not during school hours\n"
                            f"- Limited to safe categories (pet care, errands, tutoring, etc.)\n"
                            f"- Payments go to parent/guardian IBAN\n\n"
                            f"If you did not expect this email, you can safely ignore it.\n\n"
                            f"— The Human-me Team"
                        )
                    )
                    app_obj = current_app._get_current_object()
                    Thread(target=_send_async_email, args=(app_obj, consent_msg)).start()
                except Exception:
                    pass

            flash('Registration successful! Check your email to verify your account.', 'success')
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
        
        if user and user.verify_password(password):
            if user.is_active is False:
                flash('Your account has been deactivated. Contact support.', 'danger')
                return redirect(url_for('auth.login'))
            login_user(user)
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
            user.email_verified = True  # Google confirms email
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
                roles=json.dumps([role]),
                online=True,
                password_hash=bcrypt.generate_password_hash(password).decode('utf-8'),
                full_name=google_data.get("name", ""),
                email_verified=True,  # Google confirms email
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
        user_role = current_user.role

        # Block deletion if provider has active/in-progress appointments
        active_statuses = ['scheduled', 'confirmed', 'confirmed_paid', 'in_progress', 'work_submitted', 'authorized']
        if user_role == 'provider':
            active_appts = Appointment.query.filter(
                Appointment.provider_id == user_id,
                Appointment.status.in_(active_statuses)
            ).count()
            active_reqs = ClientSelfCreatedAppointment.query.filter(
                ClientSelfCreatedAppointment.provider_id == user_id,
                ClientSelfCreatedAppointment.status.in_(active_statuses)
            ).count()
            if active_appts + active_reqs > 0:
                flash('Cannot delete account while you have active appointments. Please complete or cancel them first.', 'danger')
                return redirect(url_for('provider.profile'))

        # Save record for scam protection (re-registration detection)
        deleted_record = DeletedAccount(
            email=current_user.email,
            phone=current_user.phone_number,
            telegram_id=str(current_user.telegram_id) if current_user.telegram_id else None,
            role=user_role,
        )
        db.session.add(deleted_record)

        # 1. Delete Supabase Files (Photo)
        if current_user.photo:
            try:
                delete_from_supabase(current_user.photo, 'profile_pictures')
            except Exception as e:
                    pass  # Supabase photo cleanup failed

        # 2. Delete Supabase Files (Documents)
        if current_user.documents:
            try:
                documents = json.loads(current_user.documents)
                for i in documents:
                    delete_from_supabase(i, 'documents')
            except Exception as e:
                    pass  # Supabase doc cleanup failed

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

        # F. Delete Favorites and Share Tokens
        Favorite.query.filter_by(user_id=user_id).delete(synchronize_session=False)
        FavoriteShareToken.query.filter_by(user_id=user_id).delete(synchronize_session=False)

        # G. Delete ServiceHistory
        ServiceHistory.query.filter(
            (ServiceHistory.provider_id == user_id) | (ServiceHistory.client_id == user_id)
        ).delete(synchronize_session=False)

        # H. Delete RequestOfferResponses
        RequestOfferResponse.query.filter_by(provider_id=user_id).delete(synchronize_session=False)

        # I. Delete NoShowRecords
        NoShowRecord.query.filter(
            (NoShowRecord.reporter_id == user_id) | (NoShowRecord.reported_user_id == user_id)
        ).delete(synchronize_session=False)

        # J. Delete Disputes
        Dispute.query.filter(
            (Dispute.filed_by_user_id == user_id)
        ).delete(synchronize_session=False)

        # K. Delete Feedback
        Feedback.query.filter_by(user_id=user_id).delete(synchronize_session=False)

        # L. Delete InvitationTokens
        InvitationToken.query.filter_by(created_by=user_id).delete(synchronize_session=False)

        # 4. Finally, Delete the User
        db.session.delete(current_user)
        db.session.commit()
        
        # 5. Logout
        logout_user()
        
        flash('Your account has been successfully deleted.', 'success')
        return redirect(url_for('auth.register')) # or main.index
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Delete Error: {e}")
        flash('An error occurred while deleting your account. Please try again.', 'danger')
        if current_user.is_authenticated and current_user.role == 'provider':
            return redirect(url_for('provider.profile'))
        return redirect(url_for('client.profile'))
    
@auth_bp.route('/set_language/<lang_code>')    
def set_language(lang_code):
        # set language
        session['lang'] = lang_code
        return redirect(request.referrer or url_for('main.home'))

@auth_bp.route('/change_password', methods=['POST'])
@login_required
def change_password():
    current_pw = request.form.get('current_password', '')
    new_pw = request.form.get('new_password', '')
    confirm = request.form.get('confirm_password', '')
    set_new = request.form.get('set_new')  # "1" when user has no bcrypt password yet

    has_bcrypt = current_user.password_hash and current_user.password_hash.startswith('$2')

    if new_pw != confirm:
        flash('New passwords do not match.', 'danger')
    elif len(new_pw) < 8:
        flash('Password must be at least 8 characters.', 'danger')
    elif set_new and not has_bcrypt:
        # User registered via Telegram/Google — setting password for the first time
        current_user.password = new_pw
        db.session.commit()
        flash('Password set successfully! You can now log in with your username and password.', 'success')
    elif not has_bcrypt:
        flash('Use the "Set Password" form to create your password.', 'danger')
    elif not current_user.verify_password(current_pw):
        flash('Current password is incorrect.', 'danger')
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


# ── Password Recovery ─────────────────────────────────────────────

@auth_bp.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for(f'{current_user.role}.dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        if not email:
            flash('Please enter your email address.', 'danger')
            return redirect(url_for('auth.forgot_password'))

        user = User.query.filter((User.email == email) | (User.user_name == email)).first()
        if user:
            token = _generate_token(user.id, salt='password-reset')
            reset_url = url_for('auth.reset_password', token=token, _external=True)
            msg = MailMessage(
                subject='Password Reset — Human-me',
                sender=os.getenv('MAIL_DEFAULT_SENDER'),
                recipients=[user.email],
                body=(
                    f"Hi {user.full_name or user.user_name},\n\n"
                    f"You requested a password reset. Click the link below:\n\n"
                    f"{reset_url}\n\n"
                    f"This link expires in 1 hour.\n\n"
                    f"If you did not request this, please ignore this email.\n\n"
                    f"— The Human-me Team"
                )
            )
            app_obj = current_app._get_current_object()
            Thread(target=_send_async_email, args=(app_obj, msg)).start()

        flash('If an account with that email exists, a reset link has been sent.', 'info')
        return redirect(url_for('auth.login'))

    return render_template('auth/forgot_password.html')


@auth_bp.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for(f'{current_user.role}.dashboard'))

    user_id = _verify_token(token, salt='password-reset', max_age=3600)
    if not user_id:
        flash('Invalid or expired reset link. Please request a new one.', 'danger')
        return redirect(url_for('auth.forgot_password'))

    user = User.query.get(user_id)
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        new_pw = request.form.get('new_password', '')
        confirm = request.form.get('confirm_password', '')

        if len(new_pw) < 8:
            flash('Password must be at least 8 characters.', 'danger')
            return render_template('auth/reset_password.html')
        if new_pw != confirm:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/reset_password.html')

        user.password = new_pw
        db.session.commit()
        flash('Password has been reset! Please log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/reset_password.html')


# ── Account Setup (owner-created accounts) ───────────────────────

@auth_bp.route('/setup/<token>', methods=['GET', 'POST'])
def setup_account(token):
    if current_user.is_authenticated:
        return redirect(url_for(f'{current_user.role}.dashboard'))

    user_id = _verify_token(token, salt='account-setup', max_age=604800)  # 7 days
    if not user_id:
        flash('Invalid or expired setup link. Please contact support.', 'danger')
        return redirect(url_for('auth.login'))

    user = User.query.get(user_id)
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        new_email = request.form.get('new_email', '').strip()
        new_pw    = request.form.get('new_password', '')
        confirm   = request.form.get('confirm_password', '')

        if new_email and new_email != user.email:
            existing = User.query.filter(User.email == new_email, User.id != user.id).first()
            if existing:
                flash('This email is already in use.', 'danger')
                return render_template('auth/setup_account.html', user=user)
            user.email = new_email

        if new_pw:
            if len(new_pw) < 8:
                flash('Password must be at least 8 characters.', 'danger')
                return render_template('auth/setup_account.html', user=user)
            if new_pw != confirm:
                flash('Passwords do not match.', 'danger')
                return render_template('auth/setup_account.html', user=user)
            user.password = new_pw

        db.session.commit()
        flash('Account set up successfully! Please log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/setup_account.html', user=user)


@auth_bp.route('/verification_status')
@login_required
def verification_status():
    """Return current user's verification status."""
    return jsonify({
        'phone_verified': current_user.phone_verified,
        'email_verified': current_user.email_verified,
        'id_verified': current_user.id_verified,
        'is_verified': current_user.is_verified,
        'telegram_linked': current_user.telegram_id is not None,
    })


# ── Email Verification ───────────────────────────────────────────

@auth_bp.route('/verify_email/<token>')
def verify_email(token):
    """Verify email address from link in email."""
    user_id = _verify_token(token, salt='email-verify', max_age=86400)  # 24 hours
    if not user_id:
        flash('Invalid or expired verification link.', 'danger')
        return redirect(url_for('auth.login'))

    user = User.query.get(user_id)
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('auth.login'))

    user.email_verified = True
    db.session.commit()
    flash('Email verified successfully!', 'success')

    if current_user.is_authenticated:
        return redirect(url_for(f'{current_user.role}.profile'))
    return redirect(url_for('auth.login'))


@auth_bp.route('/parent_consent/<token>')
def parent_consent(token):
    """Parent confirms consent for a young helper account."""
    user = User.query.filter_by(parent_consent_token=token).first()
    if not user:
        flash('Invalid or expired consent link.', 'danger')
        return redirect(url_for('main.home'))

    if user.parent_consent_status == 'confirmed':
        flash('Consent has already been confirmed.', 'info')
        return redirect(url_for('main.home'))

    user.parent_consent_status = 'confirmed'
    user.parent_consent_token = None
    db.session.commit()

    # Notify user via Telegram if linked
    try:
        from app.telegram.notifications import send_user_telegram
        if user.telegram_id and user.telegram_notifications:
            send_user_telegram(user.id,
                "Your parent/guardian has confirmed consent! You can now offer services as a Young Helper.")
    except Exception:
        pass

    flash('Parental consent confirmed! The Young Helper account is now active.', 'success')
    return redirect(url_for('main.home'))


@auth_bp.route('/resend_verification_email', methods=['POST'])
@login_required
def resend_verification_email():
    """Resend email verification link."""
    if current_user.email_verified:
        return jsonify({'success': False, 'message': 'Email already verified'})

    # Don't send to placeholder Telegram emails
    if current_user.email and '@telegram.placeholder' in current_user.email:
        return jsonify({'success': False, 'message': 'Please set a real email address first'})

    token = _generate_token(current_user.id, salt='email-verify')
    verify_url = url_for('auth.verify_email', token=token, _external=True)

    msg = MailMessage(
        subject='Verify your email — Human-me',
        sender=os.getenv('MAIL_DEFAULT_SENDER'),
        recipients=[current_user.email],
        body=(
            f"Hi {current_user.full_name or current_user.user_name},\n\n"
            f"Please verify your email by clicking:\n{verify_url}\n\n"
            f"This link expires in 24 hours.\n\n"
            f"— The Human-me Team"
        )
    )
    app_obj = current_app._get_current_object()
    Thread(target=_send_async_email, args=(app_obj, msg)).start()

    return jsonify({'success': True, 'message': 'Verification email sent!'})


# ── Dual-Role: Switch & Activate ──────────────────────────────────

@auth_bp.route('/switch_role', methods=['POST'])
@login_required
def switch_role():
    """Switch between client/provider if user has both roles."""
    target = request.form.get('target_role')
    if target not in ('client', 'provider'):
        flash('Invalid role.', 'danger')
        return redirect(request.referrer or url_for('main.home'))

    if target == current_user.role:
        return redirect(url_for(f'{target}.dashboard'))

    if current_user.has_role(target):
        current_user.role = target
        db.session.commit()
        return redirect(url_for(f'{target}.dashboard'))
    else:
        return redirect(url_for('auth.activate_role', target_role=target))


@auth_bp.route('/activate_role/<target_role>', methods=['GET', 'POST'])
@login_required
def activate_role(target_role):
    """Activate a second role for the current user."""
    if target_role not in ('client', 'provider'):
        flash('Invalid role.', 'danger')
        return redirect(url_for(f'{current_user.role}.dashboard'))

    if current_user.has_role(target_role):
        current_user.role = target_role
        db.session.commit()
        return redirect(url_for(f'{target_role}.dashboard'))

    if request.method == 'POST':
        current_user.add_role(target_role)
        current_user.role = target_role
        db.session.commit()
        flash(f'You are now also a {target_role}! Welcome.', 'success')
        return redirect(url_for(f'{target_role}.dashboard'))

    return render_template('auth/activate_role.html', target_role=target_role)

