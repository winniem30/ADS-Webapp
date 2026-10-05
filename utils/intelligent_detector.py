"""
Intelligent Anomaly Detection Engine
Automatically selects and applies appropriate detection methods based on dataset characteristics
"""

import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.svm import OneClassSVM
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score
import logging

logger = logging.getLogger(__name__)


class IntelligentDetector:
    """
    Intelligent anomaly detection that automatically selects the best method
    based on dataset characteristics (supervised vs unsupervised).
    """
    
    def __init__(self):
        self.method = None
        self.model = None
        self.has_target = False
        self.target_column = None
        self.label_encoder = None
        self.metrics = {}
        
    def detect_method(self, df: pd.DataFrame, analysis: dict) -> str:
        """
        Automatically determine whether to use supervised or unsupervised learning.
        
        Returns: 'supervised' or 'unsupervised'
        """
        # Check for potential target columns
        potential_targets = analysis.get('potential_targets', [])
        
        if potential_targets:
            # Check if target column has balanced classes
            for col in potential_targets:
                if col in df.columns:
                    unique_vals = df[col].dropna().unique()
                    if len(unique_vals) == 2:
                        self.target_column = col
                        self.has_target = True
                        return 'supervised'
        
        # Check for any binary column that could be a target
        for col in df.columns:
            if df[col].nunique() == 2 and pd.api.types.is_numeric_dtype(df[col]):
                self.target_column = col
                self.has_target = True
                return 'supervised'
        
        # Default to unsupervised
        self.has_target = False
        return 'unsupervised'
    
    def train_supervised(self, X: np.ndarray, y: np.ndarray) -> dict:
        """
        Train a supervised model for anomaly/fraud detection.
        
        Returns: Model metrics
        """
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )
        
        # Train Random Forest
        self.model = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            random_state=42,
            n_jobs=-1
        )
        self.model.fit(X_train, y_train)
        
        # Make predictions
        y_pred = self.model.predict(X_test)
        y_pred_proba = self.model.predict_proba(X_test)[:, 1]
        
        # Calculate metrics
        self.metrics = {
            'accuracy': accuracy_score(y_test, y_pred),
            'precision': precision_score(y_test, y_pred, zero_division=0),
            'recall': recall_score(y_test, y_pred, zero_division=0),
            'f1': f1_score(y_test, y_pred, zero_division=0),
            'roc_auc': roc_auc_score(y_test, y_pred_proba) if len(np.unique(y)) > 1 else 0
        }
        
        logger.info(f"Supervised model trained: {self.metrics}")
        return self.metrics
    
    def train_unsupervised(self, X: np.ndarray) -> dict:
        """
        Train an unsupervised model for anomaly detection.
        
        Returns: Model info
        """
        # Use Isolation Forest for unsupervised anomaly detection
        self.model = IsolationForest(
            n_estimators=100,
            contamination=0.1,  # Assume 10% anomalies
            random_state=42,
            n_jobs=-1
        )
        self.model.fit(X)
        
        self.metrics = {
            'method': 'Isolation Forest',
            'contamination': 0.1,
            'n_estimators': 100
        }
        
        logger.info(f"Unsupervised model trained: {self.metrics}")
        return self.metrics
    
    def predict(self, X: np.ndarray) -> tuple:
        """
        Make predictions on the data.
        
        Returns: (predictions, anomaly_scores)
        """
        if self.has_target:
            # Supervised prediction
            predictions = self.model.predict(X)
            anomaly_scores = self.model.predict_proba(X)[:, 1]
        else:
            # Unsupervised prediction
            predictions = self.model.predict(X)
            # Convert -1 (anomaly) to 1, 1 (normal) to 0
            predictions = np.where(predictions == -1, 1, 0)
            anomaly_scores = self.model.score_samples(X)
            # Normalize scores to 0-1 range
            anomaly_scores = (anomaly_scores - anomaly_scores.min()) / (anomaly_scores.max() - anomaly_scores.min() + 1e-10)
            anomaly_scores = 1 - anomaly_scores  # Higher score = more anomalous
        
        return predictions, anomaly_scores
    
    def generate_results(self, X: np.ndarray, original_df: pd.DataFrame) -> list:
        """
        Generate comprehensive results for each record.
        
        Returns: List of result dictionaries
        """
        predictions, anomaly_scores = self.predict(X)
        
        results = []
        for idx, (pred, score) in enumerate(zip(predictions, anomaly_scores)):
            risk_score = float(score * 100)
            
            # Determine risk level
            if risk_score >= 80:
                risk_level = 'critical'
            elif risk_score >= 60:
                risk_level = 'high'
            elif risk_score >= 40:
                risk_level = 'medium'
            elif risk_score >= 20:
                risk_level = 'low'
            else:
                risk_level = 'safe'
            
            result = {
                'index': idx,
                'prediction': int(pred),
                'probability': float(score),
                'risk_score': risk_score,
                'risk_level': risk_level,
                'method': self.method,
                'has_target': self.has_target
            }
            
            # Add original data
            if idx < len(original_df):
                for col in original_df.columns:
                    result[col] = original_df.iloc[idx][col]
            
            results.append(result)
        
        return results
    
    def get_feature_importance(self, X: np.ndarray, feature_names: list) -> dict:
        """
        Get feature importance if available.
        
        Returns: Dictionary of feature importance
        """
        if self.has_target and hasattr(self.model, 'feature_importances_'):
            importance = dict(zip(feature_names, self.model.feature_importances_))
            # Sort by importance
            importance = dict(sorted(importance.items(), key=lambda x: x[1], reverse=True))
            return importance
        return {}
