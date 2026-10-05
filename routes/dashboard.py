"""
Dashboard Blueprint
Handles main dashboard with statistics and visualizations
"""

from flask import Blueprint, render_template, session, jsonify
from database import db
from prediction import PredictionEngine
from utils.dataset_detector import DatasetDetector
import logging

logger = logging.getLogger(__name__)

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')


@dashboard_bp.route('/dashboard')
def dashboard():
    """Main dashboard page"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    try:
        # Get dashboard statistics
        stats = db.get_dashboard_stats()
        
        # Get recent alerts
        alerts = db.get_alerts(unread_only=True, limit=5)
        
        # Get model status for all available datasets
        model_status = {}
        for dataset_type in ['dataset1', 'dataset2', 'simple', 'synthetic_ml']:
            try:
                pred_engine = PredictionEngine(dataset_type)
                model_status[f"{dataset_type}_rf"] = {
                    'available': 'random_forest' in pred_engine.models and pred_engine.models['random_forest'] is not None
                }
                model_status[f"{dataset_type}_svm"] = {
                    'available': 'svm' in pred_engine.models and pred_engine.models['svm'] is not None
                }
                model_status[f"{dataset_type}_xgb"] = {
                    'available': 'xgboost' in pred_engine.models and pred_engine.models['xgboost'] is not None
                }
            except Exception as e:
                logger.error(f"Error loading models for {dataset_type}: {str(e)}")
                model_status[f"{dataset_type}_rf"] = {'available': False}
                model_status[f"{dataset_type}_svm"] = {'available': False}
                model_status[f"{dataset_type}_xgb"] = {'available': False}
        
        return render_template('new_dashboard.html', 
                              stats=stats, 
                              alerts=alerts, 
                              model_status=model_status)
    except Exception as e:
        logger.error(f"Dashboard error: {str(e)}")
        return render_template('error.html', error=str(e))


@dashboard_bp.route('/api/dashboard-stats')
def dashboard_stats_api():
    """API endpoint for dashboard statistics"""
    try:
        stats = db.get_dashboard_stats()
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Dashboard stats API error: {str(e)}")
        return jsonify({'error': str(e)}), 500


@dashboard_bp.route('/api/alerts')
def alerts_api():
    """API endpoint for alerts"""
    try:
        alerts = db.get_alerts(unread_only=True, limit=10)
        return jsonify([dict(alert) for alert in alerts])
    except Exception as e:
        logger.error(f"Alerts API error: {str(e)}")
        return jsonify({'error': str(e)}), 500
