"""
Upload Blueprint - Robust Dataset-Agnostic Version
Handles dataset upload with proper sklearn Pipeline integration
"""

from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify
from werkzeug.utils import secure_filename
import os
from database import db
from preprocessing.robust_preprocessor import RobustPreprocessor
from utils.robust_detector import RobustDetector
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
            
            # Load dataset
            df = load_dataset(file_path)
            row_count = len(df)
            
            # Validate dataset is not empty
            if len(df) == 0:
                os.remove(file_path)
                return jsonify({'error': 'Uploaded file is empty'}), 400
            
            if len(df.columns) == 0:
                os.remove(file_path)
                return jsonify({'error': 'Uploaded file has no columns'}), 400
            
            # Use robust preprocessor with sklearn Pipeline
            preprocessor = RobustPreprocessor()
            
            try:
                X, analysis_info = preprocessor.fit_transform(df)
            except ValueError as e:
                os.remove(file_path)
                return jsonify({'error': str(e)}), 400
            
            # Use robust detector
            detector = RobustDetector()
            detector.method = detector.select_method(df, analysis_info['column_types'])
            
            try:
                if detector.has_target:
                    # Encode target
                    y = df[detector.target_column].values
                    detector.train_supervised(X, y)
                else:
                    detector.train_unsupervised(X)
            except ValueError as e:
                os.remove(file_path)
                return jsonify({'error': str(e)}), 400
            
            # Generate results
            results = detector.generate_results(X, df)
            
            # Create upload record
            file_size = os.path.getsize(file_path)
            upload_id = db.insert_upload(saved_filename, filename, file_size, 'generic')
            
            # Save predictions to database
            for result in results:
                result['upload_id'] = upload_id
                db.insert_transaction(result)
            
            # Update upload record
            db.update_upload(upload_id, row_count, 'completed', detector.method)
            
            # Return JSON response with comprehensive analysis
            return jsonify({
                'success': True,
                'upload_id': upload_id,
                'row_count': row_count,
                'analysis': analysis_info,
                'method': detector.method,
                'has_target': detector.has_target,
                'metrics': detector.metrics,
                'feature_count': len(preprocessor.feature_names_out)
            })
            
        except Exception as e:
            logger.error(f"Upload error: {str(e)}")
            logger.error(f"Upload error traceback: ", exc_info=True)
            # Clean up file on error
            if 'file_path' in locals() and os.path.exists(file_path):
                os.remove(file_path)
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
        
        # Load and preview data
        df = load_dataset(temp_path)
        
        # Use robust preprocessor to analyze
        preprocessor = RobustPreprocessor()
        column_info = preprocessor.detect_column_types(df)
        
        # Clean up temp file
        os.remove(temp_path)
        
        return jsonify({
            'rows': len(df),
            'columns': list(df.columns),
            'preview': df.head(5).to_dict('records'),
            'column_info': column_info
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
