"""
Configuration file for Money Laundering Detection Platform
Contains all application settings, paths, and constants
"""

import os
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Base directory
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Application settings
class Config:
    """Main configuration class"""
    
    # Flask settings
    SECRET_KEY = os.environ.get('SECRET_KEY', 'aml-detection-secret-key-2024')
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    TESTING = False
    
    # Upload settings
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    ALLOWED_EXTENSIONS = {'csv', 'xlsx', 'xls'}
    
    # Database settings
    DATABASE_PATH = os.path.join(BASE_DIR, 'aml_database.db')
    
    # Model settings
    MODELS_FOLDER = os.path.join(BASE_DIR, 'models')
    
    # Dataset 1 (Daily Transactions Dataset) model files
    DATASET1_MODELS = {
        'random_forest': 'dataset1_rf.pkl',
        'svm': 'dataset1_svm.pkl',
        'xgboost': 'dataset1_xgb.pkl'
    }
    
    # Dataset 2 (Bank Transaction Fraud Detection) model files
    DATASET2_MODELS = {
        'random_forest': 'dataset2_rf.pkl',
        'svm': 'dataset2_svm.pkl',
        'xgboost': 'dataset2_xgb.pkl'
    }
    
    # Simple dataset model files (for testing with synthetic data)
    SIMPLE_MODELS = {
        'random_forest': 'simple_rf.pkl',
        'svm': 'simple_svm.pkl',
        'xgboost': 'simple_xgb.pkl'
    }
    
    # Synthetic Money Laundering dataset model files
    SYNTHETIC_ML_MODELS = {
        'random_forest': 'synthetic_ml_rf.pkl',
        'svm': 'synthetic_ml_svm.pkl',
        'xgboost': 'synthetic_ml_xgb.pkl'
    }
    
    # Dataset 1 preprocessing files
    DATASET1_PREPROCESSING = {
        'label_encoders': 'dataset1_label_encoders.pkl',
        'scaler': 'dataset1_scaler.pkl',
        'feature_columns': 'dataset1_feature_columns.pkl',
        'categorical_columns': 'dataset1_categorical_columns.pkl',
        'numerical_columns': 'dataset1_numerical_columns.pkl'
    }
    
    # Dataset 2 preprocessing files
    DATASET2_PREPROCESSING = {
        'label_encoders': 'dataset2_label_encoders.pkl',
        'scaler': 'dataset2_scaler.pkl',
        'feature_columns': 'dataset2_feature_columns.pkl',
        'categorical_columns': 'dataset2_categorical_columns.pkl',
        'numerical_columns': 'dataset2_numerical_columns.pkl'
    }
    
    # Simple dataset preprocessing files
    SIMPLE_PREPROCESSING = {
        'label_encoders': 'simple_location_encoder.pkl',
        'scaler': 'simple_scaler.pkl',
        'feature_columns': 'simple_feature_columns.pkl'
    }
    
    # Synthetic ML dataset preprocessing files
    SYNTHETIC_ML_PREPROCESSING = {
        'label_encoders': 'synthetic_ml_label_encoders.pkl',
        'scaler': 'synthetic_ml_scaler.pkl',
        'feature_columns': 'synthetic_ml_feature_columns.pkl'
    }
    
    # Spider chart axes for simple dataset
    SIMPLE_SPIDER_AXES = [
        'Amount', 'Location Risk', 'Time Risk', 
        'Business Account', 'Large Amount', 'Risk Score'
    ]
    
    # Spider chart axes for synthetic ML dataset
    SYNTHETIC_ML_SPIDER_AXES = [
        'Amount', 'Risk Score', 'Payment Channel', 'City', 
        'Country', 'Merchant Category', 'Transaction Type', 'Fraud Probability'
    ]
    
    # Report settings
    REPORTS_FOLDER = os.path.join(BASE_DIR, 'reports')
    CHARTS_FOLDER = os.path.join(BASE_DIR, 'charts')
    
    # Risk classification thresholds
    RISK_THRESHOLDS = {
        'safe': 0.2,
        'low': 0.4,
        'medium': 0.6,
        'high': 0.8,
        'critical': 1.0
    }
    
    # Risk colors
    RISK_COLORS = {
        'safe': '#28a745',
        'low': '#17a2b8',
        'medium': '#fd7e14',
        'high': '#dc3545',
        'critical': '#6f0a0a'
    }
    
    # Session settings
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() == 'true'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = 3600  # 1 hour
    
    # Pagination
    ITEMS_PER_PAGE = 20
    
    # Logging
    LOG_LEVEL = 'INFO'
    LOG_FILE = os.path.join(BASE_DIR, 'aml_system.log')
    
    # Spider chart axes for Dataset 1
    DATASET1_SPIDER_AXES = [
        'Amount', 'Mode', 'Category', 'Subcategory', 
        'Income/Expense', 'Frequency', 'Time', 
        'Risk Score', 'Behavior Score', 'Transaction Pattern'
    ]
    
    # Spider chart axes for Dataset 2
    DATASET2_SPIDER_AXES = [
        'Transaction Amount', 'Customer Risk', 'Transaction Type',
        'Device Risk', 'Merchant Risk', 'Location Risk',
        'Frequency', 'Time Risk', 'Network Risk',
        'Historical Behaviour', 'Velocity', 'AML Score'
    ]


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    # Force secure cookies in production unless explicitly disabled
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'True').lower() == 'true'


# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
