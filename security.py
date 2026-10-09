"""Authentication helpers shared by Flask routes.

Production requests use Firebase Admin verified session cookies. A server-side
Flask session is accepted only when AUTH_MODE=development.
"""
from __future__ import annotations

from functools import wraps

from flask import current_app, g, jsonify, redirect, request, session, url_for


ALLOWED_ROLES = {'analyst', 'reviewer', 'administrator'}


def _firebase_auth():
    try:
        import firebase_admin
        from firebase_admin import auth
    except ImportError as exc:  # pragma: no cover - depends on deployment extras
        raise RuntimeError('Firebase authentication requires firebase-admin. Install requirements.txt.') from exc

    project_id = current_app.config.get('FIREBASE_PROJECT_ID')
    if not project_id:
        raise RuntimeError('FIREBASE_PROJECT_ID is required when AUTH_MODE=firebase.')
    try:
        app = firebase_admin.get_app()
    except ValueError:
        app = firebase_admin.initialize_app(options={'projectId': project_id})
    return auth, app


def verify_firebase_session(token: str) -> dict:
    auth, _app = _firebase_auth()
    return auth.verify_session_cookie(token, check_revoked=True)


def user_from_claims(claims: dict) -> dict:
    role = claims.get('role', 'analyst')
    if role not in ALLOWED_ROLES:
        role = 'analyst'
    return {
        'id': claims.get('uid') or claims.get('sub'),
        'email': claims.get('email', ''),
        'role': role,
        'auth_provider': 'firebase',
    }


def current_identity() -> dict | None:
    return getattr(g, 'ads_identity', None)


def authenticate_request():
    """Resolve identity for the current request; return an error response on failure."""
    mode = current_app.config.get('AUTH_MODE', 'development')
    if mode == 'development':
        if session.get('user_id'):
            g.ads_identity = {
                'id': str(session['user_id']),
                'email': session.get('username', 'local analyst'),
                'role': session.get('role', 'analyst'),
                'auth_provider': 'development-session',
            }
            return None
        return _unauthorized()

    cookie = request.cookies.get('ads_session', '')
    if not cookie:
        return _unauthorized()
    try:
        claims = verify_firebase_session(cookie)
    except Exception:
        response = _unauthorized()
        response.delete_cookie('ads_session', path='/', secure=True, httponly=True, samesite='Strict')
        return response
    identity = user_from_claims(claims)
    if not identity['id']:
        return _unauthorized()
    g.ads_identity = identity
    return None


def _unauthorized():
    if request.path.startswith('/api/') or request.accept_mimetypes.best == 'application/json':
        return jsonify(error='Authentication required.'), 401
    return redirect(url_for('auth.login', next=request.path))


def require_roles(*roles):
    """Authorize a route using a verified identity and server-asserted role."""
    required = set(roles)

    def decorate(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            identity = current_identity()
            if identity is None:
                response = authenticate_request()
                if response is not None:
                    return response
                identity = current_identity()
            if required and identity.get('role') not in required:
                return jsonify(error='This action requires an authorized reviewer.'), 403
            return view(*args, **kwargs)
        return wrapped
    return decorate
