"""
Money Laundering Detection & Risk Intelligence Platform
Main Flask application with blueprints and configuration
"""

import os
from flask import Flask
from config import config

# Initialize Flask app
def create_app(config_name=None):
    """Application factory pattern"""
    app = Flask(__name__)
    
    # Load configuration
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'default')
    app.config.from_object(config[config_name])
    
    # Create necessary directories
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['REPORTS_FOLDER'], exist_ok=True)
    os.makedirs(app.config['CHARTS_FOLDER'], exist_ok=True)
    os.makedirs('static/css', exist_ok=True)
    os.makedirs('static/js', exist_ok=True)
    os.makedirs('static/images', exist_ok=True)
    
    # Register blueprints
    from routes import auth_bp, dashboard_bp, upload_bp, analysis_bp, report_bp, admin_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(upload_bp)
    app.register_blueprint(analysis_bp)
    app.register_blueprint(report_bp)
    app.register_blueprint(admin_bp)
    
    # Root route - show landing page (blue page) for everyone
    @app.route('/')
    def index():
        from flask import session, redirect, url_for, render_template
        # Always show landing page - the upload form will handle auth check
        return render_template('landing.html', session=session)
    
    # Initialize database
    from database import db
    db.init_database()
    
    # Create default admin user if not exists
    try:
        if not db.get_user('admin'):
            db.insert_user('admin', 'admin123', 'admin@aml.com', 'admin')
    except:
        pass
    
    return app


# Create app instance
app = create_app()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
