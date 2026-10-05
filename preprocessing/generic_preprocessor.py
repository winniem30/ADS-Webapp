"""
Generic Preprocessor for Unknown Datasets
Handles any CSV/Excel file with automatic feature engineering
"""

import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.impute import SimpleImputer
import joblib
import os
from typing import Dict, List, Tuple
import logging

logger = logging.getLogger(__name__)


class GenericPreprocessor:
    """
    Generic preprocessor that can handle any dataset.
    Automatically detects column types and applies appropriate preprocessing.
    """
    
    def __init__(self):
        self.scaler = StandardScaler()
        self.label_encoders = {}
        self.numeric_columns = []
        self.categorical_columns = []
        self.feature_columns = []
        self.imputer = SimpleImputer(strategy='median')
        
    def detect_column_types(self, df: pd.DataFrame) -> Tuple[List[str], List[str]]:
        """
        Automatically detect numeric and categorical columns.
        
        Args:
            df: Input dataframe
            
        Returns:
            Tuple of (numeric_columns, categorical_columns)
        """
        numeric_cols = []
        categorical_cols = []
        
        for col in df.columns:
            # Check if column is numeric
            if pd.api.types.is_numeric_dtype(df[col]):
                numeric_cols.append(col)
            else:
                categorical_cols.append(col)
        
        logger.info(f"Detected {len(numeric_cols)} numeric and {len(categorical_cols)} categorical columns")
        return numeric_cols, categorical_cols
    
    def engineer_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Generate new features from existing columns.
        
        Args:
            df: Input dataframe
            
        Returns:
            Dataframe with engineered features
        """
        df = df.copy()
        
        # Create numeric features from categorical columns
        for col in df.select_dtypes(include=['object']).columns:
            # Create frequency encoding
            freq_map = df[col].value_counts(normalize=True).to_dict()
            df[f'{col}_freq'] = df[col].map(freq_map).fillna(0)
        
        # Create interaction features for numeric columns
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        if len(numeric_cols) >= 2:
            # Create pairwise ratios
            for i in range(min(3, len(numeric_cols))):
                for j in range(i+1, min(i+3, len(numeric_cols))):
                    if df[numeric_cols[j]].std() > 0:
                        df[f'{numeric_cols[i]}_div_{numeric_cols[j]}'] = (
                            df[numeric_cols[i]] / (df[numeric_cols[j]] + 1e-6)
                        )
        
        # Create statistical features
        for col in numeric_cols:
            if df[col].std() > 0:
                df[f'{col}_zscore'] = (df[col] - df[col].mean()) / df[col].std()
                df[f'{col}_log'] = np.log1p(np.abs(df[col]))
        
        return df
    
    def fit(self, df: pd.DataFrame):
        """
        Fit the preprocessor on the dataset.
        
        Args:
            df: Input dataframe
        """
        # Detect column types
        self.numeric_columns, self.categorical_columns = self.detect_column_types(df)
        
        # Engineer features
        df_engineered = self.engineer_features(df)
        
        # Update feature columns
        self.feature_columns = [col for col in df_engineered.columns if col in df_engineered.select_dtypes(include=[np.number]).columns]
        
        # Fit imputer on numeric columns
        numeric_data = df_engineered[self.numeric_columns].select_dtypes(include=[np.number])
        if not numeric_data.empty:
            self.imputer.fit(numeric_data)
        
        # Fit label encoders for categorical columns
        for col in self.categorical_columns:
            if col in df_engineered.columns:
                le = LabelEncoder()
                # Handle unseen values by fitting on all unique values
                le.fit(df_engineered[col].astype(str).fillna('missing'))
                self.label_encoders[col] = le
        
        # Fit scaler on all numeric features
        all_numeric = df_engineered[self.feature_columns].select_dtypes(include=[np.number])
        if not all_numeric.empty:
            self.scaler.fit(all_numeric)
        
        logger.info(f"Fitted generic preprocessor with {len(self.feature_columns)} features")
    
    def transform(self, df: pd.DataFrame) -> np.ndarray:
        """
        Transform the dataset using fitted preprocessor.
        
        Args:
            df: Input dataframe
            
        Returns:
            Transformed numpy array
        """
        df = df.copy()
        
        # Engineer features
        df_engineered = self.engineer_features(df)
        
        # Ensure all feature columns exist
        for col in self.feature_columns:
            if col not in df_engineered.columns:
                df_engineered[col] = 0
        
        # Select only feature columns
        df_features = df_engineered[self.feature_columns]
        
        # Impute missing values
        numeric_cols = df_features.select_dtypes(include=[np.number]).columns.tolist()
        if numeric_cols:
            df_features[numeric_cols] = self.imputer.transform(df_features[numeric_cols])
        
        # Encode categorical columns
        for col in self.categorical_columns:
            if col in df_features.columns and col in self.label_encoders:
                df_features[col] = self.label_encoders[col].transform(
                    df_features[col].astype(str).fillna('missing')
                )
        
        # Scale features
        df_numeric = df_features.select_dtypes(include=[np.number])
        if not df_numeric.empty:
            df_scaled = self.scaler.transform(df_numeric)
            return df_scaled
        
        return df_features.values
    
    def fit_transform(self, df: pd.DataFrame) -> np.ndarray:
        """
        Fit and transform in one step.
        
        Args:
            df: Input dataframe
            
        Returns:
            Transformed numpy array
        """
        self.fit(df)
        return self.transform(df)
    
    def save_pipeline(self, save_dir: str):
        """
        Save the preprocessing pipeline.
        
        Args:
            save_dir: Directory to save the pipeline
        """
        os.makedirs(save_dir, exist_ok=True)
        
        pipeline = {
            'scaler': self.scaler,
            'label_encoders': self.label_encoders,
            'numeric_columns': self.numeric_columns,
            'categorical_columns': self.categorical_columns,
            'feature_columns': self.feature_columns,
            'imputer': self.imputer
        }
        
        joblib.dump(pipeline, os.path.join(save_dir, 'generic_preprocessor.pkl'))
        logger.info(f"Saved generic preprocessor to {save_dir}")
    
    def load_pipeline(self, save_dir: str):
        """
        Load the preprocessing pipeline.
        
        Args:
            save_dir: Directory to load the pipeline from
        """
        pipeline_path = os.path.join(save_dir, 'generic_preprocessor.pkl')
        
        if os.path.exists(pipeline_path):
            pipeline = joblib.load(pipeline_path)
            self.scaler = pipeline['scaler']
            self.label_encoders = pipeline['label_encoders']
            self.numeric_columns = pipeline['numeric_columns']
            self.categorical_columns = pipeline['categorical_columns']
            self.feature_columns = pipeline['feature_columns']
            self.imputer = pipeline['imputer']
            logger.info(f"Loaded generic preprocessor from {save_dir}")
        else:
            logger.warning(f"Generic preprocessor not found at {pipeline_path}")
