"""
Intelligent Dataset-Agnostic Preprocessor
Handles any CSV/Excel file with automatic column type detection and preprocessing
"""

import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler, LabelEncoder, MinMaxScaler
from sklearn.impute import SimpleImputer
from sklearn.feature_selection import VarianceThreshold
import joblib
import os
from typing import Dict, List, Tuple, Optional
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class IntelligentPreprocessor:
    """
    Intelligent preprocessor that can handle ANY dataset without assuming column names.
    Automatically detects column types and applies appropriate preprocessing.
    """
    
    def __init__(self):
        self.scaler = StandardScaler()
        self.label_encoders = {}
        self.column_types = {}  # Maps column names to their detected types
        self.feature_columns = []
        self.excluded_columns = []
        self.imputer_numeric = SimpleImputer(strategy='median')
        self.imputer_categorical = SimpleImputer(strategy='most_frequent')
        self.target_column = None
        self.has_target = False
        
    def detect_column_type(self, col: str, series: pd.Series) -> str:
        """
        Intelligently detect the type of a column.
        
        Returns: 'numeric', 'categorical', 'datetime', 'id', 'target', 'text'
        """
        # Check for datetime
        if pd.api.types.is_datetime64_any_dtype(series):
            return 'datetime'
        
        # Try to parse as datetime
        try:
            pd.to_datetime(series, errors='raise')
            return 'datetime'
        except:
            pass
        
        # Check for numeric
        if pd.api.types.is_numeric_dtype(series):
            # Check if it's an ID column (unique values, high cardinality)
            unique_ratio = series.nunique() / len(series)
            if unique_ratio > 0.95 and series.nunique() > 10:
                return 'id'
            return 'numeric'
        
        # Check for categorical
        unique_count = series.nunique()
        total_count = len(series)
        
        # Binary column (potential target)
        if unique_count == 2:
            # Check if values look like labels
            if set(series.dropna().unique()).issubset({0, 1, '0', '1', True, False, 'Yes', 'No', 'Y', 'N', 'yes', 'no', 'y', 'n'}):
                return 'target'
            return 'categorical'
        
        # High cardinality categorical (might be ID)
        if unique_count > 100 and unique_count / total_count > 0.5:
            # Check if values are mostly unique strings
            if series.dtype == 'object':
                return 'id'
            return 'categorical'
        
        # Low cardinality categorical
        if unique_count < 50:
            return 'categorical'
        
        # Text column (long strings)
        if series.dtype == 'object':
            avg_length = series.astype(str).str.len().mean()
            if avg_length > 50:
                return 'text'
            return 'categorical'
        
        return 'categorical'
    
    def analyze_dataset(self, df: pd.DataFrame) -> Dict:
        """
        Analyze the dataset and return comprehensive information.
        
        Returns:
            Dictionary with dataset analysis results
        """
        analysis = {
            'shape': df.shape,
            'columns': list(df.columns),
            'dtypes': df.dtypes.astype(str).to_dict(),
            'missing_values': df.isnull().sum().to_dict(),
            'column_types': {},
            'numeric_columns': [],
            'categorical_columns': [],
            'datetime_columns': [],
            'id_columns': [],
            'text_columns': [],
            'potential_targets': [],
            'duplicate_rows': df.duplicated().sum(),
            'memory_usage': df.memory_usage(deep=True).sum() / 1024**2  # MB
        }
        
        for col in df.columns:
            col_type = self.detect_column_type(col, df[col])
            analysis['column_types'][col] = col_type
            
            if col_type == 'numeric':
                analysis['numeric_columns'].append(col)
            elif col_type == 'categorical':
                analysis['categorical_columns'].append(col)
            elif col_type == 'datetime':
                analysis['datetime_columns'].append(col)
            elif col_type == 'id':
                analysis['id_columns'].append(col)
            elif col_type == 'target':
                analysis['potential_targets'].append(col)
            elif col_type == 'text':
                analysis['text_columns'].append(col)
        
        logger.info(f"Dataset analysis: {len(analysis['numeric_columns'])} numeric, "
                   f"{len(analysis['categorical_columns'])} categorical, "
                   f"{len(analysis['datetime_columns'])} datetime, "
                   f"{len(analysis['id_columns'])} IDs, "
                   f"{len(analysis['potential_targets'])} potential targets")
        
        return analysis
    
    def select_features(self, df: pd.DataFrame, analysis: Dict) -> Tuple[List[str], List[str]]:
        """
        Select which columns to use as features and which to exclude.
        
        Returns:
            Tuple of (feature_columns, excluded_columns_with_reason)
        """
        feature_columns = []
        excluded = {}
        
        for col in df.columns:
            col_type = analysis['column_types'][col]
            
            # Exclude ID columns
            if col_type == 'id':
                excluded[col] = 'ID column (high cardinality, likely identifier)'
                continue
            
            # Exclude text columns (too complex for basic ML)
            if col_type == 'text':
                excluded[col] = 'Text column (not suitable for basic ML)'
                continue
            
            # Check for constant columns
            if df[col].nunique() <= 1:
                excluded[col] = 'Constant column (no variance)'
                continue
            
            # Check for columns with too many missing values (>50%)
            missing_ratio = df[col].isnull().sum() / len(df)
            if missing_ratio > 0.5:
                excluded[col] = f'Too many missing values ({missing_ratio:.1%})'
                continue
            
            # Include everything else
            feature_columns.append(col)
        
        logger.info(f"Selected {len(feature_columns)} features, excluded {len(excluded)} columns")
        return feature_columns, excluded
    
    def engineer_features(self, df: pd.DataFrame, feature_columns: List[str]) -> pd.DataFrame:
        """
        Generate new features from existing columns dynamically.
        
        Args:
            df: Input dataframe
            feature_columns: List of columns to use for feature engineering
            
        Returns:
            Dataframe with engineered features
        """
        df = df.copy()
        
        # Work only with feature columns
        df_features = df[feature_columns].copy()
        
        # Feature engineering for numeric columns
        numeric_cols = df_features.select_dtypes(include=[np.number]).columns.tolist()
        
        for col in numeric_cols:
            # Log transform for skewed positive values
            if (df_features[col] > 0).all():
                df_features[f'{col}_log'] = np.log1p(df_features[col])
            
            # Z-score normalization
            if df_features[col].std() > 0:
                df_features[f'{col}_zscore'] = (df_features[col] - df_features[col].mean()) / df_features[col].std()
        
        # Feature engineering for categorical columns
        categorical_cols = df_features.select_dtypes(include=['object']).columns.tolist()
        
        for col in categorical_cols:
            # Frequency encoding
            freq_map = df_features[col].value_counts(normalize=True).to_dict()
            df_features[f'{col}_freq'] = df_features[col].map(freq_map).fillna(0)
        
        # Interaction features (limited to avoid explosion)
        if len(numeric_cols) >= 2:
            for i in range(min(2, len(numeric_cols))):
                for j in range(i+1, min(i+2, len(numeric_cols))):
                    col1, col2 = numeric_cols[i], numeric_cols[j]
                    if df_features[col2].std() > 0:
                        df_features[f'{col1}_div_{col2}'] = df_features[col1] / (df_features[col2].abs() + 1e-6)
        
        return df_features
    
    def fit(self, df: pd.DataFrame):
        """
        Fit the preprocessor on the dataset without assuming any column names.
        
        Args:
            df: Input dataframe
        """
        # Analyze dataset
        self.analysis = self.analyze_dataset(df)
        
        # Select features
        self.feature_columns, self.excluded_columns = self.select_features(df, self.analysis)
        
        # Store column types
        self.column_types = self.analysis['column_types']
        
        # Engineer features
        df_engineered = self.engineer_features(df, self.feature_columns)
        
        # Get all numeric columns after engineering
        self.numeric_features = df_engineered.select_dtypes(include=[np.number]).columns.tolist()
        self.categorical_features = df_engineered.select_dtypes(include=['object']).columns.tolist()
        
        # Fit imputers
        if self.numeric_features:
            self.imputer_numeric.fit(df_engineered[self.numeric_features])
        
        if self.categorical_features:
            self.imputer_categorical.fit(df_engineered[self.categorical_features])
        
        # Fit label encoders for categorical features
        for col in self.categorical_features:
            le = LabelEncoder()
            le.fit(df_engineered[col].astype(str).fillna('missing'))
            self.label_encoders[col] = le
        
        # Fit scaler on all numeric features
        if self.numeric_features:
            self.scaler.fit(df_engineered[self.numeric_features])
        
        logger.info(f"Fitted intelligent preprocessor with {len(self.numeric_features)} numeric features")
    
    def transform(self, df: pd.DataFrame) -> np.ndarray:
        """
        Transform the dataset using fitted preprocessor.
        
        Args:
            df: Input dataframe
            
        Returns:
            Transformed numpy array
        """
        df = df.copy()
        
        # Select only feature columns
        df_features = df[self.feature_columns].copy()
        
        # Engineer features
        df_engineered = self.engineer_features(df_features, self.feature_columns)
        
        # Impute missing values
        if self.numeric_features:
            # Ensure columns exist
            for col in self.numeric_features:
                if col not in df_engineered.columns:
                    df_engineered[col] = 0
            df_engineered[self.numeric_features] = self.imputer_numeric.transform(df_engineered[self.numeric_features])
        
        if self.categorical_features:
            for col in self.categorical_features:
                if col not in df_engineered.columns:
                    df_engineered[col] = 'missing'
            df_engineered[self.categorical_features] = self.imputer_categorical.transform(df_engineered[self.categorical_features])
        
        # Encode categorical columns
        for col in self.categorical_features:
            if col in df_engineered.columns and col in self.label_encoders:
                # Handle unseen categories
                df_engineered[col] = df_engineered[col].astype(str).fillna('missing')
                unseen_mask = ~df_engineered[col].isin(self.label_encoders[col].classes_)
                df_engineered.loc[unseen_mask, col] = self.label_encoders[col].classes_[0] if len(self.label_encoders[col].classes_) > 0 else 'missing'
                df_engineered[col] = self.label_encoders[col].transform(df_engineered[col])
        
        # Get final numeric features
        final_numeric = df_engineered.select_dtypes(include=[np.number])
        
        # Scale features
        if not final_numeric.empty:
            df_scaled = self.scaler.transform(final_numeric)
            return df_scaled
        
        return final_numeric.values
    
    def fit_transform(self, df: pd.DataFrame) -> Tuple[np.ndarray, Dict]:
        """
        Fit and transform in one step.
        
        Args:
            df: Input dataframe
            
        Returns:
            Tuple of (transformed_data, analysis_info)
        """
        self.fit(df)
        transformed = self.transform(df)
        
        analysis_info = {
            'original_shape': df.shape,
            'feature_count': len(self.feature_columns),
            'excluded_columns': self.excluded_columns,
            'numeric_features': len(self.numeric_features),
            'categorical_features': len(self.categorical_features),
            'column_types': self.column_types
        }
        
        return transformed, analysis_info
