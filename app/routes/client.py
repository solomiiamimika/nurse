from flask import render_template, redirect, url_for, flash, request,abort
from flask_login import login_user, logout_user, current_user, login_required
from app. extensions import db, bcrypt
from app.models import User
from . import client_bp


@client_bp.route('/dashboard')
@login_required
def dashboard():
    if current_user.role!='client':
        return redirect(url_for('auth.login'))
    return render_template('client/dashboard.html')


    