"""
Flask blueprint for Telegram integration:
  /telegram/webhook           — receives bot updates from Telegram
  /telegram/login_callback    — Telegram Login Widget callback
  /telegram/complete_registration — role/email form for new Telegram users
  /telegram/link              — link existing account to Telegram
"""
import logging
import secrets
from flask import (
    Blueprint, request, jsonify, current_app,
    redirect, url_for, flash, session, render_template,
)
from flask_login import login_user, login_required, current_user
from app.extensions import db
from app.models import User
from .security import verify_telegram_login, verify_webhook_secret
from .handlers import dispatch_update

logger = logging.getLogger(__name__)

telegram_bp = Blueprint('telegram', __name__, url_prefix='/telegram')


# ── Webhook (receives updates from Telegram servers) ──────────────

@telegram_bp.route('/webhook', methods=['POST'])
def webhook():
    bot_token = current_app.config.get('TELEGRAM_BOT_TOKEN')
    if not bot_token:
        return '', 503

    secret_header = request.headers.get('X-Telegram-Bot-Api-Secret-Token', '')
    if not verify_webhook_secret(secret_header, bot_token):
        logger.warning("Webhook request with invalid secret token")
        return '', 403

    update = request.get_json(force=True)
    try:
        dispatch_update(update, bot_token)
    except Exception:
        logger.exception("Error dispatching webhook update_id=%s", update.get('update_id'))
    return '', 200


# ── Login Widget callback ─────────────────────────────────────────

@telegram_bp.route('/login_callback')
def login_callback():
    """Called by Telegram Login Widget with auth data in query params."""
    bot_token = current_app.config.get('TELEGRAM_BOT_TOKEN')
    if not bot_token:
        flash('Telegram not configured.', 'danger')
        return redirect(url_for('auth.login'))

    data = dict(request.args)
    if not verify_telegram_login(dict(data), bot_token):  # copy — verify pops 'hash'
        flash('Telegram authentication failed.', 'danger')
        return redirect(url_for('auth.login'))

    telegram_id = int(data['id'])

    # Already linked?
    user = User.query.filter_by(telegram_id=telegram_id).first()
    if user:
        if not user.is_active:
            flash('Your account has been deactivated.', 'danger')
            return redirect(url_for('auth.login'))
        login_user(user)
        flash('Logged in via Telegram!', 'success')
        if user.is_owner:
            return redirect(url_for('owner.dashboard'))
        return redirect(url_for(f'{user.role}.dashboard'))

    # New user — store data in session, ask for role + email
    session['telegram_pending'] = {
        'telegram_id': telegram_id,
        'first_name': data.get('first_name', ''),
        'last_name': data.get('last_name', ''),
        'username': data.get('username', ''),
    }
    return redirect(url_for('telegram.complete_registration'))


# ── Complete registration (new Telegram user) ─────────────────────

@telegram_bp.route('/complete_registration', methods=['GET', 'POST'])
def complete_registration():
    pending = session.get('telegram_pending')
    if not pending:
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        role = request.form.get('role')
        email = request.form.get('email', '').strip()

        if role not in ('client', 'provider'):
            flash('Please select a role.', 'danger')
            return render_template('auth/telegram_complete.html', pending=pending)

        # If email matches an existing account — link it
        if email:
            existing = User.query.filter_by(email=email).first()
            if existing:
                existing.telegram_id = pending['telegram_id']
                existing.telegram_notifications = True
                existing.phone_verified = True  # Telegram requires phone → auto-verify
                db.session.commit()
                login_user(existing)
                session.pop('telegram_pending', None)
                flash('Telegram linked to your existing account!', 'success')
                if existing.is_owner:
                    return redirect(url_for('owner.dashboard'))
                return redirect(url_for(f'{existing.role}.dashboard'))

        # Generate unique username
        base = pending.get('username') or pending.get('first_name') or 'user'
        username = base
        counter = 1
        while User.query.filter_by(user_name=username).first():
            username = f"{base}{counter}"
            counter += 1

        full_name = f"{pending.get('first_name', '')} {pending.get('last_name', '')}".strip()

        user = User(
            user_name=username,
            email=email or f"tg_{pending['telegram_id']}@telegram.placeholder",
            role=role,
            full_name=full_name or username,
            telegram_id=pending['telegram_id'],
            telegram_notifications=True,
            phone_verified=True,  # Telegram requires phone → auto-verify
            password_hash=secrets.token_urlsafe(32),
            referral_code=secrets.token_urlsafe(6)[:8],
            terms_accepted=True,
        )
        db.session.add(user)
        db.session.commit()
        login_user(user)
        session.pop('telegram_pending', None)
        flash('Account created via Telegram!', 'success')
        return redirect(url_for(f'{user.role}.dashboard'))

    return render_template('auth/telegram_complete.html', pending=pending)


# ── Link existing account to Telegram ─────────────────────────────

@telegram_bp.route('/link')
@login_required
def link_telegram():
    """User clicked a link from the bot to connect their Telegram."""
    tg_id = request.args.get('tg_id', type=int)
    if not tg_id:
        flash('Invalid link.', 'danger')
        return redirect(url_for('main.home'))

    # Check if this telegram_id is already linked to another account
    existing = User.query.filter_by(telegram_id=tg_id).first()
    if existing and existing.id != current_user.id:
        flash('This Telegram account is already linked to another user.', 'danger')
        return redirect(url_for('main.home'))

    current_user.telegram_id = tg_id
    current_user.telegram_notifications = True
    current_user.phone_verified = True  # Telegram requires phone → auto-verify
    db.session.commit()
    flash('Telegram linked successfully! Go back to the bot and type /start.', 'success')

    if current_user.is_owner:
        return redirect(url_for('owner.dashboard'))
    return redirect(url_for(f'{current_user.role}.dashboard'))
