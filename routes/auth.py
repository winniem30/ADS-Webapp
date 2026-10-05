"""
Authentication Blueprint
Handles user login, logout, and registration
"""

from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from database import db

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = db.get_user(username)
        
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            db.update_last_login(user['id'])
            return redirect(url_for('dashboard.dashboard'))  # Will show landing page due to app.py logic
        else:
            flash('Invalid username or password', 'error')
            return render_template('login.html', error='Invalid username or password')
    
    return render_template('login.html')


@auth_bp.route('/ Register', methods=['GET', 'POST'])
def register():
    """Handle user registration"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        email = request.form.get('email')
        
        # Check if user already exists
        existing_user = db.get_user(username)
        if existing_user:
            flash('Username already exists', 'error')
            return render_template('register.html', error='Username already exists')
        
        # Create new user
        password_hash = generate_password_hash(password)
        db.insert_user(username, password_hash, email, role='analyst')
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('register.html')


@auth_bp.route('/logout')
def logout():
    """Handle user logout"""
    session.clear()
    return redirect(url_for('auth.login'))
