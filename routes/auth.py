"""Firebase sign-in UI and explicit local-only development authentication."""
from urllib.parse import urljoin, urlparse

from flask import Blueprint, current_app, make_response, redirect, render_template, request, session, url_for

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


def _safe_next(value):
    if not value:
        return '/dashboard'
    target = urlparse(urljoin(request.host_url, value))
    if target.scheme not in {'http', 'https'} or target.netloc != request.host:
        return '/dashboard'
    return target.path + (('?' + target.query) if target.query else '')


@auth_bp.get('/login')
def login():
    return render_template('firebase_login.html',
                           auth_mode=current_app.config.get('AUTH_MODE'),
                           firebase_config=current_app.config.get('FIREBASE_WEB_CONFIG', {}),
                           next_url=_safe_next(request.args.get('next')))


@auth_bp.get('/register')
def register():
    # Account creation is managed in the configured Firebase project; never accept
    # browser-selected roles or provision privileged accounts through this app.
    return redirect(url_for('auth.login'))


@auth_bp.get('/logout')
def logout():
    session.clear()
    response = make_response(redirect(url_for('index')))
    response.delete_cookie('ads_session', path='/', secure=not current_app.config.get('DEBUG', False),
                           httponly=True, samesite='Strict')
    return response
