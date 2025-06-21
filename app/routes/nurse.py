from flask import render_template, redirect, url_for, flash, request,abort
from flask_login import login_user, logout_user, current_user, login_required
from app. extensions import db, bcrypt
from app.models import User
from . import nurse_bp


@nurse_bp.route('/dashboard')
@login_required
def dashboard():
    if current_user.role!='nurse':
        return redirect(url_for('auth.login'))
    return render_template('nurse/dashboard.html')
    
