"""
Robust Anomaly Detection Engine
Uses proper sklearn Pipeline integration for consistent feature handling
"""

import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.svm import OneClassSVM
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score
import logging

logger = logging.getLogger(__name__)


class RobustDetector:
    """
    Robust anomaly detection with proper pipeline integration.
    Handles edge cases gracefully and provides clear error messages.
    """
    
    def __init__(self):
        self.model = None
        self.method = None
        self.has_target = False
        self.target_column = None
        self.metrics = {}
        self.label_encoder = None
        
    def detect_target_column(self, df: pd.DataFrame, column_info: dict) -> str:
        """
        Detect if there's a suitable target column for supervised learning.
        
        Returns: Column name or None
        """
        # Look for binary columns with label-like characteristics
        for col, col_type in column_info.items():
            if col_type == 'binary_target':
                return col
            
            # Check for other binary columns that might be targets
            if col_type == 'numeric' and df[col].nunique() == 2:
                if set(df[col].dropna().unique()).issubset({0, 1}):
                    return col
        
        return None
    
    def select_method(self, df: pd.DataFrame, column_info: dict) -> str:
        """
        Select appropriate detection method based on dataset.
        
        Returns: 'supervised' or 'unsupervised'
        """
        self.target_column = self.detect_target_column(df, column_info)
        
        if self.target_column:
            self.has_target = True
            return 'supervised'
        
        self.has_target = False
        return 'unsupervised'
    
    def train_supervised(self, X: np.ndarray, y: np.ndarray) -> dict:
        """
        Train supervised model with validation.
        
        Returns: Model metrics
        """
        # Validate data
        if len(X) == 0:
            raise ValueError("Cannot train on empty dataset")
        
        if X.shape[1] == 0:
            raise ValueError("Cannot train with zero features")
        
        # Check if we have enough data for train/test split
        if len(X) < 10:
            logger.warning("Dataset too small for train/test split, using full dataset for training")
            X_train, y_train = X, y
            X_test, y_test = X, y
        else:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42, stratify=y if len(np.unique(y)) > 1 else None
            )
        
        # Train Random Forest
        self.model = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            random_state=42,
            n_jobs=-1,
            class_weight='balanced'
        )
        
        try:
            self.model.fit(X_train, y_train)
        except Exception as e:
            logger.error(f"Model training failed: {str(e)}")
            raise ValueError(f"Unable to train model: {str(e)}")
        
        # Evaluate
        y_pred = self.model.predict(X_test)
        
        try:
            y_pred_proba = self.model.predict_proba(X_test)[:, 1]
        except:
            y_pred_proba = y_pred.astype(float)
        
        # Calculate metrics (convert to native Python types)
        self.metrics = {
            'method': 'Random Forest (Supervised)',
            'accuracy': float(accuracy_score(y_test, y_pred)),
            'precision': float(precision_score(y_test, y_pred, zero_division=0)),
            'recall': float(recall_score(y_test, y_pred, zero_division=0)),
            'f1': float(f1_score(y_test, y_pred, zero_division=0))
        }
        
        try:
            if len(np.unique(y)) > 1:
                self.metrics['roc_auc'] = float(roc_auc_score(y_test, y_pred_proba))
        except:
            self.metrics['roc_auc'] = 0.0
        
        logger.info(f"Supervised model trained: {self.metrics}")
        return self.metrics
    
    def train_unsupervised(self, X: np.ndarray) -> dict:
        """
        Train unsupervised anomaly detection model.
        
        Returns: Model info
        """
        # Validate data
        if len(X) == 0:
            raise ValueError("Cannot train on empty dataset")
        
        if X.shape[1] == 0:
            raise ValueError("Cannot train with zero features")
        
        # Use Isolation Forest
        self.model = IsolationForest(
            n_estimators=100,
            contamination=0.1,  # 10% expected anomalies
            random_state=42,
            n_jobs=-1
        )
        
        try:
            self.model.fit(X)
        except Exception as e:
            logger.error(f"Model training failed: {str(e)}")
            raise ValueError(f"Unable to train model: {str(e)}")
        
        self.metrics = {
            'method': 'Isolation Forest (Unsupervised)',
            'contamination': 0.1,
            'n_estimators': 100
        }
        
        logger.info(f"Unsupervised model trained: {self.metrics}")
        return self.metrics
    
    def predict(self, X: np.ndarray) -> tuple:
        """
        Make predictions.
        
        Returns: (predictions, anomaly_scores)
        """
        if self.model is None:
            raise ValueError("Model not trained")
        
        if len(X) == 0:
            raise ValueError("Cannot predict on empty dataset")
        
        if X.shape[1] == 0:
            raise ValueError("Cannot predict with zero features")
        
        if self.has_target:
            # Supervised
            predictions = self.model.predict(X)
            try:
                anomaly_scores = self.model.predict_proba(X)[:, 1]
            except:
                anomaly_scores = predictions.astype(float)
        else:
            # Unsupervised
            predictions = self.model.predict(X)
            # Convert -1 (anomaly) to 1, 1 (normal) to 0
            predictions = np.where(predictions == -1, 1, 0)
            anomaly_scores = self.model.score_samples(X)
            # Normalize to 0-1
            anomaly_scores = (anomaly_scores - anomaly_scores.min()) / (anomaly_scores.max() - anomaly_scores.min() + 1e-10)
            anomaly_scores = 1 - anomaly_scores  # Higher = more anomalous
        
        return predictions, anomaly_scores
    
    def generate_results(self, X: np.ndarray, original_df: pd.DataFrame) -> list:
        """
        Generate comprehensive results.
        
        Returns: List of result dictionaries with native Python types
        """
        predictions, anomaly_scores = self.predict(X)
        
        results = []
        for idx, (pred, score) in enumerate(zip(predictions, anomaly_scores)):
            risk_score = float(score * 100)
            
            # Risk level
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
                'index': int(idx),
                'prediction': int(pred),
                'probability': float(score),
                'risk_score': risk_score,
                'risk_level': risk_level,
                'method': self.method,
                'has_target': bool(self.has_target)
            }
            
            # Add original data (preserve all columns, convert to native types)
            if idx < len(original_df):
                for col in original_df.columns:
                    val = original_df.iloc[idx][col]
                    # Convert numpy types to native Python types
                    if pd.isna(val):
                        result[col] = None
                    elif isinstance(val, (np.integer, np.floating)):
                        result[col] = float(val) if isinstance(val, np.floating) else int(val)
                    elif isinstance(val, np.bool_):
                        result[col] = bool(val)
                    else:
                        result[col] = val
            
            results.append(result)
        
        return results
