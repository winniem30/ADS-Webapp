"""
Prediction module for Money Laundering Detection Platform
Handles ML model loading, prediction, and result generation with dual dataset support
"""

import joblib
import pickle
import numpy as np
import pandas as pd
import time
import os
from config import Config
import logging
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent))

from preprocessing.dataset1_preprocessor import Dataset1Preprocessor
from preprocessing.dataset2_preprocessor import Dataset2Preprocessor
from preprocessing.generic_preprocessor import GenericPreprocessor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PredictionEngine:
    """Manages ML model loading and predictions with auto-dataset detection"""
    
    def __init__(self, dataset_type=None):
        """
        Initialize prediction engine for specific dataset type
        
        Args:
            dataset_type: 'dataset1', 'dataset2', or None (auto-detect)
        """
        self.dataset_type = dataset_type
        self.models = {}
        self.model_metadata = {}
        self.preprocessor = None
        
        if dataset_type:
            self.load_dataset_models(dataset_type)
    
    def load_dataset_models(self, dataset_type):
        """
        Load models and preprocessing pipeline for specific dataset
        
        Args:
            dataset_type: 'dataset1' or 'dataset2'
        """
        self.dataset_type = dataset_type
        
        # Select appropriate model files
        if dataset_type == 'dataset1':
            model_files = Config.DATASET1_MODELS
            preprocessor_class = Dataset1Preprocessor
        elif dataset_type == 'dataset2':
            model_files = Config.DATASET2_MODELS
            preprocessor_class = Dataset2Preprocessor
        elif dataset_type == 'simple':
            model_files = Config.SIMPLE_MODELS
            preprocessor_class = None  # Simple dataset uses direct preprocessing
        elif dataset_type == 'synthetic_ml':
            model_files = Config.SYNTHETIC_ML_MODELS
            preprocessor_class = None  # Synthetic ML uses direct preprocessing
        elif dataset_type == 'generic':
            # For generic datasets, use generic preprocessor and simple models
            model_files = Config.SIMPLE_MODELS
            preprocessor_class = GenericPreprocessor
        else:
            raise ValueError(f"Invalid dataset_type: {dataset_type}")
        
        # Load preprocessing pipeline
        try:
            if preprocessor_class:
                self.preprocessor = preprocessor_class()
                # For generic preprocessor, don't load from disk - will fit on data
                if dataset_type != 'generic':
                    self.preprocessor.load_pipeline(Config.MODELS_FOLDER)
                logger.info(f"Loaded preprocessing pipeline for {dataset_type}")
            elif dataset_type == 'simple':
                # For simple dataset, load preprocessing artifacts directly
                self.preprocessor = self.load_simple_preprocessing()
                logger.info(f"Loaded simple preprocessing for {dataset_type}")
            elif dataset_type == 'synthetic_ml':
                # For synthetic ML dataset, load preprocessing artifacts directly
                self.preprocessor = self.load_synthetic_ml_preprocessing()
                logger.info(f"Loaded synthetic ML preprocessing for {dataset_type}")
        except Exception as e:
            logger.error(f"Error loading preprocessing pipeline for {dataset_type}: {str(e)}")
            # For generic datasets, this is expected - will fit on data
            if dataset_type != 'generic':
                raise
        
        # Load models
        for model_name, filename in model_files.items():
            model_path = os.path.join(Config.MODELS_FOLDER, filename)
            
            if os.path.exists(model_path):
                try:
                    self.models[model_name] = joblib.load(model_path)
                    logger.info(f"Loaded {model_name} model for {dataset_type} from {model_path}")
                    
                    self.model_metadata[model_name] = {
                        'loaded': True,
                        'path': model_path,
                        'type': model_name,
                        'dataset_type': dataset_type
                    }
                except Exception as e:
                    logger.error(f"Error loading {model_name} model for {dataset_type}: {str(e)}")
                    self.model_metadata[model_name] = {
                        'loaded': False,
                        'error': str(e),
                        'dataset_type': dataset_type
                    }
            else:
                logger.warning(f"Model file not found for {dataset_type}: {model_path}")
                self.model_metadata[model_name] = {
                    'loaded': False,
                    'error': 'File not found',
                    'dataset_type': dataset_type
                }
    
    def load_simple_preprocessing(self):
        """
        Load preprocessing artifacts for simple dataset
        
        Returns:
            Dictionary with preprocessing artifacts
        """
        preprocessing = {}
        
        # Load scaler
        scaler_path = os.path.join(Config.MODELS_FOLDER, Config.SIMPLE_PREPROCESSING['scaler'])
        if os.path.exists(scaler_path):
            preprocessing['scaler'] = joblib.load(scaler_path)
        else:
            logger.warning(f"Scaler not found: {scaler_path}")
        
        # Load feature columns
        feature_cols_path = os.path.join(Config.MODELS_FOLDER, Config.SIMPLE_PREPROCESSING['feature_columns'])
        if os.path.exists(feature_cols_path):
            preprocessing['feature_columns'] = joblib.load(feature_cols_path)
        else:
            logger.warning(f"Feature columns not found: {feature_cols_path}")
        
        # Load label encoder if exists
        encoder_path = os.path.join(Config.MODELS_FOLDER, Config.SIMPLE_PREPROCESSING['label_encoders'])
        if os.path.exists(encoder_path):
            preprocessing['label_encoder'] = joblib.load(encoder_path)
        
        return preprocessing
    
    def load_synthetic_ml_preprocessing(self):
        """
        Load preprocessing artifacts for synthetic ML dataset
        
        Returns:
            Dictionary with preprocessing artifacts
        """
        preprocessing = {}
        
        # Load scaler
        scaler_path = os.path.join(Config.MODELS_FOLDER, Config.SYNTHETIC_ML_PREPROCESSING['scaler'])
        if os.path.exists(scaler_path):
            preprocessing['scaler'] = joblib.load(scaler_path)
        else:
            logger.warning(f"Scaler not found: {scaler_path}")
        
        # Load feature columns
        feature_cols_path = os.path.join(Config.MODELS_FOLDER, Config.SYNTHETIC_ML_PREPROCESSING['feature_columns'])
        if os.path.exists(feature_cols_path):
            preprocessing['feature_columns'] = joblib.load(feature_cols_path)
        else:
            logger.warning(f"Feature columns not found: {feature_cols_path}")
        
        # Load label encoders
        encoder_path = os.path.join(Config.MODELS_FOLDER, Config.SYNTHETIC_ML_PREPROCESSING['label_encoders'])
        if os.path.exists(encoder_path):
            preprocessing['label_encoders'] = joblib.load(encoder_path)
        else:
            logger.warning(f"Label encoders not found: {encoder_path}")
        
        return preprocessing
    
    def preprocess_data(self, df):
        """
        Preprocess data using the appropriate preprocessing pipeline
        
        Args:
            df: Raw DataFrame
            
        Returns:
            Preprocessed DataFrame
        """
        if not self.preprocessor:
            raise ValueError("No preprocessing pipeline loaded. Set dataset_type first.")
        
        # Handle simple dataset preprocessing (dictionary-based)
        if self.dataset_type == 'simple' and isinstance(self.preprocessor, dict):
            feature_columns = self.preprocessor.get('feature_columns', [])
            scaler = self.preprocessor.get('scaler')
            
            # Select and order features
            X = df[feature_columns].copy()
            
            # Apply scaling if available
            if scaler:
                X = scaler.transform(X)
            
            return X
        
        # Handle synthetic ML dataset preprocessing (dictionary-based with label encoding)
        if self.dataset_type == 'synthetic_ml' and isinstance(self.preprocessor, dict):
            feature_columns = self.preprocessor.get('feature_columns', [])
            label_encoders = self.preprocessor.get('label_encoders', {})
            scaler = self.preprocessor.get('scaler')
            
            # Select and order features
            X = df[feature_columns].copy()
            
            # Apply label encoding for categorical features
            for col, encoder in label_encoders.items():
                if col in X.columns:
                    # Handle unseen categories
                    X[col] = X[col].astype(str)
                    unseen_mask = ~X[col].isin(encoder.classes_)
                    X.loc[unseen_mask, col] = encoder.classes_[0] if len(encoder.classes_) > 0 else 'unknown'
                    X[col] = encoder.transform(X[col])
            
            # Handle missing values
            X = X.fillna(0)
            
            # Apply scaling if available
            if scaler:
                X = scaler.transform(X)
            
            return X
        
        # Handle generic dataset preprocessing (class-based, fit on data)
        if self.dataset_type == 'generic':
            return self.preprocessor.transform(df)
        
        # Handle standard preprocessing (class-based)
        return self.preprocessor.transform(df)
    
    def predict(self, df, model_name='random_forest'):
        """
        Make predictions using specified model
        
        Args:
            df: Preprocessed DataFrame
            model_name: Name of the model to use
            
        Returns:
            tuple: (predictions, probabilities, execution_time)
        """
        if model_name not in self.models or not self.models[model_name]:
            raise ValueError(f"Model {model_name} not available for dataset {self.dataset_type}")
        
        model = self.models[model_name]
        
        start_time = time.time()
        
        try:
            # Get predictions
            predictions = model.predict(df)
            
            # Get probabilities if available
            if hasattr(model, 'predict_proba'):
                probabilities = model.predict_proba(df)[:, 1]
            else:
                # For models without predict_proba, use decision function or predictions
                if hasattr(model, 'decision_function'):
                    probabilities = model.decision_function(df)
                    # Normalize to 0-1 range
                    probabilities = (probabilities - probabilities.min()) / (probabilities.max() - probabilities.min() + 1e-10)
                else:
                    probabilities = predictions.astype(float)
            
            execution_time = time.time() - start_time
            
            logger.info(f"Prediction complete using {model_name} for {self.dataset_type}. Time: {execution_time:.4f}s")
            
            return predictions, probabilities, execution_time
            
        except Exception as e:
            logger.error(f"Prediction error: {str(e)}")
            raise
    
    def predict_single(self, features, model_name='random_forest'):
        """
        Make prediction for a single transaction
        
        Args:
            features: Feature array or dict
            model_name: Name of the model to use
            
        Returns:
            dict: Prediction results
        """
        if isinstance(features, dict):
            features = list(features.values())
        
        features = np.array(features).reshape(1, -1)
        
        prediction, probability, execution_time = self.predict(features, model_name)
        
        return {
            'prediction': int(prediction[0]),
            'probability': float(probability[0]),
            'execution_time': execution_time,
            'model_used': model_name,
            'dataset_type': self.dataset_type
        }
    
    def compare_models(self, df):
        """
        Compare predictions from all available models for current dataset
        
        Args:
            df: Preprocessed DataFrame
            
        Returns:
            dict: Comparison results from all models
        """
        comparison_results = {}
        
        for model_name in self.models:
            if self.models[model_name]:
                try:
                    predictions, probabilities, execution_time = self.predict(df, model_name)
                    
                    comparison_results[model_name] = {
                        'predictions': predictions.tolist(),
                        'probabilities': probabilities.tolist(),
                        'execution_time': execution_time,
                        'avg_probability': float(np.mean(probabilities)),
                        'high_risk_count': int(np.sum(probabilities > 0.7)),
                        'medium_risk_count': int(np.sum((probabilities > 0.4) & (probabilities <= 0.7))),
                        'low_risk_count': int(np.sum(probabilities <= 0.4))
                    }
                    
                    logger.info(f"Comparison complete for {model_name} on {self.dataset_type}")
                    
                except Exception as e:
                    logger.error(f"Error comparing {model_name}: {str(e)}")
                    comparison_results[model_name] = {
                        'error': str(e)
                    }
        
        return comparison_results
    
    def get_model_status(self):
        """
        Get status of all loaded models for current dataset
        
        Returns:
            dict: Model status information
        """
        status = {}
        
        for model_name, metadata in self.model_metadata.items():
            status[model_name] = {
                'loaded': metadata.get('loaded', False),
                'available': model_name in self.models and self.models[model_name] is not None,
                'dataset_type': metadata.get('dataset_type', self.dataset_type)
            }
        
        return status
    
    def calculate_risk_level(self, probability):
        """
        Calculate risk level based on probability
        
        Args:
            probability: Fraud probability (0-1)
            
        Returns:
            str: Risk level (safe, low, medium, high, critical)
        """
        if probability <= Config.RISK_THRESHOLDS['safe']:
            return 'safe'
        elif probability <= Config.RISK_THRESHOLDS['low']:
            return 'low'
        elif probability <= Config.RISK_THRESHOLDS['medium']:
            return 'medium'
        elif probability <= Config.RISK_THRESHOLDS['high']:
            return 'high'
        else:
            return 'critical'
    
    def calculate_confidence_score(self, probability):
        """
        Calculate confidence score based on probability
        
        Args:
            probability: Fraud probability (0-1)
            
        Returns:
            float: Confidence score (0-100)
        """
        # Confidence is higher when probability is closer to 0 or 1
        distance_from_threshold = min(probability, 1 - probability)
        confidence = (1 - distance_from_threshold) * 100
        return round(confidence, 2)
    
    def generate_prediction_results(self, df, original_df, model_name='random_forest'):
        """
        Generate complete prediction results with all metadata
        
        Args:
            df: Preprocessed DataFrame
            original_df: Original DataFrame with raw data
            model_name: Name of the model used
            
        Returns:
            list: List of prediction result dictionaries
        """
        predictions, probabilities, execution_time = self.predict(df, model_name)
        
        results = []
        
        for idx, (pred, prob) in enumerate(zip(predictions, probabilities)):
            risk_level = self.calculate_risk_level(prob)
            confidence_score = self.calculate_confidence_score(prob)
            
            result = {
                'prediction': int(pred),
                'probability': float(prob),
                'risk_score': float(prob * 100),
                'risk_level': risk_level,
                'model_used': model_name,
                'confidence_score': confidence_score,
                'execution_time': execution_time,
                'index': idx,
                'dataset_type': self.dataset_type
            }
            
            # Add original data if available
            if idx < len(original_df):
                for col in original_df.columns:
                    result[col] = original_df.iloc[idx][col]
            
            results.append(result)
        
        logger.info(f"Generated {len(results)} prediction results for {self.dataset_type}")
        return results
    
    def batch_predict(self, df, model_name='random_forest', batch_size=1000):
        """
        Make predictions in batches for large datasets
        
        Args:
            df: Preprocessed DataFrame
            model_name: Name of the model to use
            batch_size: Number of samples per batch
            
        Returns:
            tuple: (predictions, probabilities, execution_time)
        """
        if model_name not in self.models or not self.models[model_name]:
            raise ValueError(f"Model {model_name} not available for dataset {self.dataset_type}")
        
        model = self.models[model_name]
        
        start_time = time.time()
        
        all_predictions = []
        all_probabilities = []
        
        for i in range(0, len(df), batch_size):
            batch = df.iloc[i:i + batch_size]
            
            batch_predictions = model.predict(batch)
            all_predictions.extend(batch_predictions)
            
            if hasattr(model, 'predict_proba'):
                batch_probabilities = model.predict_proba(batch)[:, 1]
            elif hasattr(model, 'decision_function'):
                batch_probabilities = model.decision_function(batch)
                batch_probabilities = (batch_probabilities - batch_probabilities.min()) / (batch_probabilities.max() - batch_probabilities.min() + 1e-10)
            else:
                batch_probabilities = batch_predictions.astype(float)
            
            all_probabilities.extend(batch_probabilities)
            
            logger.info(f"Processed batch {i//batch_size + 1}/{(len(df) + batch_size - 1)//batch_size} for {self.dataset_type}")
        
        execution_time = time.time() - start_time
        
        return np.array(all_predictions), np.array(all_probabilities), execution_time


class ModelComparator:
    """Handles model comparison and performance metrics"""
    
    def __init__(self, prediction_engine):
        """Initialize model comparator"""
        self.prediction_engine = prediction_engine
    
    def compare_all_models(self, df):
        """
        Compare all available models on the same dataset
        
        Args:
            df: Preprocessed DataFrame
            
        Returns:
            dict: Detailed comparison results
        """
        comparison = {}
        
        for model_name in self.prediction_engine.models:
            if self.prediction_engine.models[model_name]:
                try:
                    predictions, probabilities, exec_time = self.prediction_engine.predict(df, model_name)
                    
                    comparison[model_name] = {
                        'predictions': predictions.tolist(),
                        'probabilities': probabilities.tolist(),
                        'execution_time': exec_time,
                        'mean_probability': float(np.mean(probabilities)),
                        'std_probability': float(np.std(probabilities)),
                        'max_probability': float(np.max(probabilities)),
                        'min_probability': float(np.min(probabilities)),
                        'fraud_count': int(np.sum(predictions)),
                        'fraud_rate': float(np.mean(predictions)),
                        'dataset_type': self.prediction_engine.dataset_type
                    }
                    
                except Exception as e:
                    comparison[model_name] = {'error': str(e)}
        
        return comparison
    
    def ensemble_prediction(self, df, voting='soft'):
        """
        Make ensemble prediction using all available models
        
        Args:
            df: Preprocessed DataFrame
            voting: Voting strategy ('soft' or 'hard')
            
        Returns:
            tuple: (predictions, probabilities)
        """
        all_probabilities = []
        all_predictions = []
        
        for model_name in self.prediction_engine.models:
            if self.prediction_engine.models[model_name]:
                try:
                    predictions, probabilities, _ = self.prediction_engine.predict(df, model_name)
                    all_predictions.append(predictions)
                    all_probabilities.append(probabilities)
                except Exception as e:
                    logger.warning(f"Skipping {model_name} in ensemble: {str(e)}")
        
        if not all_probabilities:
            raise ValueError("No models available for ensemble")
        
        if voting == 'soft':
            # Average probabilities
            avg_probabilities = np.mean(all_probabilities, axis=0)
            predictions = (avg_probabilities > 0.5).astype(int)
            return predictions, avg_probabilities
        else:
            # Majority voting
            all_predictions = np.array(all_predictions)
            predictions = np.apply_along_axis(lambda x: np.bincount(x).argmax(), axis=0, arr=all_predictions)
            return predictions, predictions.astype(float)
