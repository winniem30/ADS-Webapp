"""
Upload Blueprint
Handles dataset upload with automatic dataset detection
"""

from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify
from werkzeug.utils import secure_filename
import os
from database import db
from utils.dataset_detector import DatasetDetector
from prediction import PredictionEngine
import pandas as pd
import logging

logger = logging.getLogger(__name__)

upload_bp = Blueprint('upload', __name__, url_prefix='/upload')


@upload_bp.route('/upload', methods=['GET', 'POST'])
def upload():
    """Handle dataset upload page"""
    if request.method == 'POST':
        # Check if user is authenticated
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated', 'redirect': '/auth/login'}), 401
        
        # Check if file was uploaded
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Validate file extension
        if not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file type. Use CSV or Excel.'}), 400
        
        try:
            # Save file
            filename = secure_filename(file.filename)
            timestamp = pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')
            saved_filename = f"{timestamp}_{filename}"
            file_path = os.path.join('uploads', saved_filename)
            file.save(file_path)
            
            # Detect dataset type
            dataset_type, error = DatasetDetector.detect_dataset(file_path)
            
            if dataset_type == 'unknown':
                # Delete unsupported file
                os.remove(file_path)
                return jsonify({'error': error}), 400
            
            # Create upload record
            file_size = os.path.getsize(file_path)
            upload_id = db.insert_upload(saved_filename, filename, file_size, dataset_type)
            
            # Load and process data
            df = load_dataset(file_path)
            row_count = len(df)
            
            # Initialize prediction engine for detected dataset
            pred_engine = PredictionEngine(dataset_type)
            
            # For generic datasets, fit preprocessor on the data first
            if dataset_type == 'generic':
                pred_engine.preprocessor.fit(df)
            
            # Preprocess data
            X = pred_engine.preprocess_data(df)
            
            # Get selected model
            model_name = request.form.get('model', 'random_forest')
            
            # Map model names for simple datasets
            if dataset_type == 'generic':
                model_mapping = {
                    'random_forest': 'random_forest',
                    'xgboost': 'xgboost',
                    'isolation_forest': 'random_forest',  # Use RF as fallback
                    'svm': 'svm',
                    'logistic_regression': 'random_forest'  # Use RF as fallback
                }
                model_name = model_mapping.get(model_name, 'random_forest')
            
            # Run predictions
            results = pred_engine.generate_prediction_results(X, df, model_name)
            
            # Save predictions to database
            for result in results:
                result['upload_id'] = upload_id
                db.insert_transaction(result)
            
            # Update upload record
            db.update_upload(upload_id, row_count, 'completed', model_name)
            
            # Return JSON response
            return jsonify({'success': True, 'upload_id': upload_id, 'row_count': row_count})
            
        except Exception as e:
            logger.error(f"Upload error: {str(e)}")
            logger.error(f"Upload error traceback: ", exc_info=True)
            return jsonify({'error': f'Error processing file: {str(e)}'}), 500
    
    # GET request - if not authenticated, redirect to login
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    return render_template('upload.html')


@upload_bp.route('/upload/preview', methods=['POST'])
def preview():
    """Preview uploaded data before processing"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    try:
        # Save temporary file
        filename = secure_filename(file.filename)
        temp_path = os.path.join('uploads', f"temp_{filename}")
        file.save(temp_path)
        
        # Detect dataset type
        dataset_type, error = DatasetDetector.detect_dataset(temp_path)
        
        if dataset_type == 'unknown':
            os.remove(temp_path)
            return jsonify({'error': error}), 400
        
        # Load and preview data
        df = load_dataset(temp_path)
        
        # Clean up temp file
        os.remove(temp_path)
        
        return jsonify({
            'dataset_type': dataset_type,
            'rows': len(df),
            'columns': list(df.columns),
            'preview': df.head(5).to_dict('records')
        })
        
    except Exception as e:
        logger.error(f"Preview error: {str(e)}")
        return jsonify({'error': str(e)}), 500


def allowed_file(filename):
    """Check if file has allowed extension"""
    from config import Config
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in Config.ALLOWED_EXTENSIONS


def load_dataset(file_path):
    """Load dataset from CSV or Excel"""
    if file_path.endswith('.csv'):
        return pd.read_csv(file_path)
    elif file_path.endswith(('.xlsx', '.xls')):
        return pd.read_excel(file_path)
    else:
        raise ValueError('Unsupported file format')
