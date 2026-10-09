"""
Money Laundering Detection & Risk Intelligence Platform
Main Flask application with blueprints and configuration
"""

import os
import secrets
import sqlite3
from datetime import timedelta
from urllib.parse import urlsplit
from flask import Flask, jsonify, render_template, redirect, url_for, request, make_response, g, session
from config import config

# Initialize Flask app
def create_app(config_name=None):
    """Application factory pattern"""
    app = Flask(__name__)
    
    # Load configuration
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'default')
    app.config.from_object(config[config_name])
    secret = os.environ.get('SECRET_KEY')
    if app.config.get('ENV') == 'production' or config_name == 'production':
        if not secret or secret in {'your-secret-key-here', 'change-me'}:
            raise RuntimeError('SECRET_KEY must be configured for production.')
        required_firebase = ('FIREBASE_PROJECT_ID', 'FIREBASE_WEB_API_KEY', 'FIREBASE_AUTH_DOMAIN', 'FIREBASE_WEB_APP_ID')
        missing_firebase = [name for name in required_firebase if not os.environ.get(name)]
        if app.config.get('AUTH_MODE') != 'firebase' or missing_firebase:
            raise RuntimeError('Production requires AUTH_MODE=firebase and Firebase configuration: ' + ', '.join(missing_firebase or ['AUTH_MODE=firebase']))
    if secret in {'your-secret-key-here', 'change-me'} and config_name != 'production':
        secret = None
    app.config['SECRET_KEY'] = secret or secrets.token_hex(32)
    
    # Create necessary directories
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['REPORTS_FOLDER'], exist_ok=True)
    os.makedirs(app.config['CHARTS_FOLDER'], exist_ok=True)
    os.makedirs('static/css', exist_ok=True)
    os.makedirs('static/js', exist_ok=True)
    os.makedirs('static/images', exist_ok=True)
    
    # Register blueprints
    from routes import auth_bp, dashboard_bp, upload_bp, analysis_bp, report_bp, admin_bp, ibm_bp, cases_bp, analyses_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(upload_bp)
    app.register_blueprint(analysis_bp)
    app.register_blueprint(report_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(ibm_bp)
    app.register_blueprint(cases_bp)
    app.register_blueprint(analyses_bp)

    @app.before_request
    def enforce_authentication():
        public_paths = {
            '/', '/health', '/auth/login', '/auth/logout', '/auth/session', '/auth/session/logout',
            '/auth/dev-session', '/api/ibm/health',
        }
        if request.endpoint == 'static':
            return None
        if (app.config.get('AUTH_MODE') == 'firebase' and request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}
                and request.path != '/auth/session'):
            origin = request.headers.get('Origin')
            forwarded_proto = request.headers.get('X-Forwarded-Proto', '').split(',')[0].strip()
            expected_scheme = forwarded_proto or request.scheme
            parsed_origin = urlsplit(origin or '')
            if not origin or parsed_origin.netloc != request.host or parsed_origin.scheme != expected_scheme:
                return jsonify(error='Cross-origin state-changing requests are not allowed.'), 403
        if request.path in public_paths:
            return None
        from security import authenticate_request
        response = authenticate_request()
        if response is not None:
            return response
    
    # Serve the IBM HI-Small investigation desk as the application home page.
    @app.route('/')
    def index():
        return render_template('landing.html', auth_mode=app.config.get('AUTH_MODE'))

    @app.get('/dashboard')
    def ibm_dashboard():
        identity = getattr(g, 'ads_identity', {})
        return render_template('ibm_dashboard.html', identity=identity,
                               firebase_config=app.config.get('FIREBASE_WEB_CONFIG', {}),
                               auth_mode=app.config.get('AUTH_MODE'))

    @app.post('/auth/session')
    def create_firebase_session():
        if app.config.get('AUTH_MODE') != 'firebase':
            return jsonify(error='Firebase sessions are disabled in development mode.'), 404
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify(error='A Firebase ID token is required.'), 401
        try:
            import firebase_admin
            from firebase_admin import auth
            from security import _firebase_auth
            firebase_auth, firebase_app = _firebase_auth()
            id_token = auth_header[7:].strip()
            claims = firebase_auth.verify_id_token(id_token, check_revoked=True, app=firebase_app)
            if not claims.get('uid'):
                return jsonify(error='Firebase token has no user identity.'), 401
            session_cookie = auth.create_session_cookie(id_token, expires_in=timedelta(hours=1), app=firebase_app)
        except Exception:
            return jsonify(error='Firebase sign-in could not be verified.'), 401
        response = make_response(jsonify(ok=True))
        response.set_cookie('ads_session', session_cookie, max_age=3600, httponly=True,
                            secure=not app.config.get('DEBUG', False), samesite='Strict', path='/')
        return response

    @app.post('/auth/session/logout')
    def clear_firebase_session():
        session.clear()
        response = make_response(jsonify(ok=True))
        response.delete_cookie('ads_session', path='/', secure=not app.config.get('DEBUG', False),
                               httponly=True, samesite='Strict')
        return response

    @app.post('/auth/dev-session')
    def create_development_session():
        if app.config.get('AUTH_MODE') != 'development':
            return jsonify(error='Development sign-in is disabled.'), 404
        session.clear()
        session['user_id'] = 'local-dev-analyst'
        session['username'] = 'Local development analyst'
        session['role'] = 'analyst'
        return jsonify(ok=True)

    @app.get('/health')
    def health():
        from routes.ibm import DB, MODEL
        db_state = 'missing'
        if os.path.exists(DB):
            conn = None
            try:
                conn = sqlite3.connect(f'file:{DB}?mode=ro', uri=True, timeout=2)
                conn.execute('SELECT 1 FROM transactions LIMIT 1').fetchone()
                db_state = 'ready'
            except sqlite3.Error:
                db_state = 'unavailable'
            finally:
                if conn is not None: conn.close()
        model_state = 'ready' if os.path.isfile(MODEL) else 'missing'
        return jsonify(service='ok', database=db_state, model=model_state), 200

    @app.after_request
    def security_headers(response):
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('X-Frame-Options', 'DENY')
        response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        response.headers.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
        return response
    
    # Initialize database
    from database import db
    db.init_database()
    from case_store import init_case_schema
    os.makedirs(os.path.dirname(app.config['DATABASE_PATH']), exist_ok=True)
    init_case_schema(app.config['DATABASE_PATH'])
    
    return app


# Create app instance
app = create_app()

if __name__ == '__main__':
    app.run(debug=app.config['DEBUG'], host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
