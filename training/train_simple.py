"""
Simple training script for the generated synthetic dataset
Trains Random Forest, SVM, and XGBoost models
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.svm import SVC
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.metrics import classification_report, accuracy_score
import xgboost as xgb
import joblib
import os

def train_models():
    """Train models on the synthetic dataset"""
    
    # Load the dataset
    print("Loading dataset...")
    df = pd.read_csv('processed_transactions.csv')
    
    # Features and target
    feature_cols = ['amount', 'location_flag', 'odd_time', 'large_amount', 'business_account']
    X = df[feature_cols]
    y = df['label']
    
    # Encode location if needed
    if 'location' in df.columns:
        le = LabelEncoder()
        df['location_encoded'] = le.fit_transform(df['location'])
        feature_cols.append('location_encoded')
        X = df[feature_cols]
        joblib.dump(le, 'models/simple_location_encoder.pkl')
    
    # Split data
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42)
    
    # Scale features
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    
    # Save scaler and feature columns
    joblib.dump(scaler, 'models/simple_scaler.pkl')
    joblib.dump(feature_cols, 'models/simple_feature_columns.pkl')
    
    print(f"Training with {len(X_train)} samples, testing with {len(X_test)} samples")
    
    # Train Random Forest
    print("\nTraining Random Forest...")
    rf_model = RandomForestClassifier(n_estimators=100, random_state=42)
    rf_model.fit(X_train, y_train)
    rf_pred = rf_model.predict(X_test)
    rf_accuracy = accuracy_score(y_test, rf_pred)
    print(f"Random Forest Accuracy: {rf_accuracy:.4f}")
    joblib.dump(rf_model, 'models/simple_rf.pkl')
    
    # Train SVM
    print("\nTraining SVM...")
    svm_model = SVC(probability=True, random_state=42)
    svm_model.fit(X_train_scaled, y_train)
    svm_pred = svm_model.predict(X_test_scaled)
    svm_accuracy = accuracy_score(y_test, svm_pred)
    print(f"SVM Accuracy: {svm_accuracy:.4f}")
    joblib.dump(svm_model, 'models/simple_svm.pkl')
    
    # Train XGBoost
    print("\nTraining XGBoost...")
    xgb_model = xgb.XGBClassifier(n_estimators=100, random_state=42)
    xgb_model.fit(X_train, y_train)
    xgb_pred = xgb_model.predict(X_test)
    xgb_accuracy = accuracy_score(y_test, xgb_pred)
    print(f"XGBoost Accuracy: {xgb_accuracy:.4f}")
    joblib.dump(xgb_model, 'models/simple_xgb.pkl')
    
    print("\n✅ All models trained and saved successfully!")
    print("\nModel files:")
    print("- models/simple_rf.pkl")
    print("- models/simple_svm.pkl")
    print("- models/simple_xgb.pkl")
    print("- models/simple_scaler.pkl")
    print("- models/simple_feature_columns.pkl")
    
    return {
        'random_forest': rf_accuracy,
        'svm': svm_accuracy,
        'xgboost': xgb_accuracy
    }

if __name__ == '__main__':
    # Create models directory if it doesn't exist
    os.makedirs('models', exist_ok=True)
    
    # Train models
    accuracies = train_models()
    
    print("\n" + "="*50)
    print("Training Complete!")
    print("="*50)
    print(f"Random Forest: {accuracies['random_forest']:.4f}")
    print(f"SVM: {accuracies['svm']:.4f}")
    print(f"XGBoost: {accuracies['xgboost']:.4f}")
