"""
Robust Dataset-Agnostic Preprocessing Pipeline
Uses sklearn Pipeline and ColumnTransformer for consistent feature handling
"""

import pandas as pd
import numpy as np
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import StandardScaler, OneHotEncoder, OrdinalEncoder
from sklearn.impute import SimpleImputer
from sklearn.feature_selection import VarianceThreshold
import logging

logger = logging.getLogger(__name__)


class RobustPreprocessor:
    """
    Robust preprocessor using sklearn Pipeline for consistent feature handling.
    Ensures the exact same feature schema between fit and transform.
    """
    
    def __init__(self):
        self.pipeline = None
        self.numeric_features = []
        self.categorical_features = []
        self.excluded_features = {}
        self.analysis = None
        self.feature_names_out = None
        
    def detect_column_types(self, df: pd.DataFrame) -> dict:
        """
        Intelligently detect column types without assuming names.
        
        Returns: Dictionary with column type information
        """
        column_info = {}
        
        for col in df.columns:
            series = df[col]
            unique_count = series.nunique()
            total_count = len(series)
            unique_ratio = unique_count / total_count if total_count > 0 else 0
            
            # Check for datetime
            if pd.api.types.is_datetime64_any_dtype(series):
                column_info[col] = 'datetime'
                continue
            
            try:
                pd.to_datetime(series, errors='raise')
                column_info[col] = 'datetime'
                continue
            except:
                pass
            
            # Check for numeric
            if pd.api.types.is_numeric_dtype(series):
                # ID-like: unique values > 95%
                if unique_ratio > 0.95 and unique_count > 10:
                    column_info[col] = 'id'
                # Constant: only 1 unique value
                elif unique_count == 1:
                    column_info[col] = 'constant'
                # Binary with label-like values
                elif unique_count == 2:
                    if set(series.dropna().unique()).issubset({0, 1, True, False}):
                        column_info[col] = 'binary_target'
                    else:
                        column_info[col] = 'numeric'
                else:
                    column_info[col] = 'numeric'
            else:
                # String/object columns
                # High cardinality text
                if unique_count > 100 and unique_ratio > 0.5:
                    column_info[col] = 'id'
                # Text (long strings)
                elif series.dtype == 'object':
                    avg_length = series.astype(str).str.len().mean()
                    if avg_length > 50:
                        column_info[col] = 'text'
                    # Binary categorical
                    elif unique_count == 2:
                        column_info[col] = 'categorical_binary'
                    # Low cardinality categorical
                    elif unique_count < 50:
                        column_info[col] = 'categorical'
                    else:
                        column_info[col] = 'categorical'
                else:
                    column_info[col] = 'categorical'
        
        return column_info
    
    def select_features(self, df: pd.DataFrame, column_info: dict) -> tuple:
        """
        Select features and identify exclusions.
        
        Returns: (numeric_features, categorical_features, excluded_dict)
        """
        numeric = []
        categorical = []
        excluded = {}
        
        for col, col_type in column_info.items():
            # Exclude problematic columns
            if col_type in ['id', 'text', 'constant']:
                if col_type == 'id':
                    excluded[col] = 'ID column (high cardinality, not suitable for ML)'
                elif col_type == 'text':
                    excluded[col] = 'Text column (too complex for basic ML)'
                elif col_type == 'constant':
                    excluded[col] = 'Constant column (no variance)'
                continue
            
            # Check for too many missing values
            missing_ratio = df[col].isnull().sum() / len(df)
            if missing_ratio > 0.5:
                excluded[col] = f'Too many missing values ({missing_ratio:.1%})'
                continue
            
            # Include appropriate columns
            if col_type == 'numeric':
                numeric.append(col)
            elif col_type in ['categorical', 'categorical_binary']:
                categorical.append(col)
            elif col_type == 'binary_target':
                # Will be handled as target, not feature
                excluded[col] = 'Binary target column (will be used as label)'
                continue
            elif col_type == 'datetime':
                # Extract features from datetime
                excluded[col] = 'Datetime column (features extracted separately)'
                continue
        
        return numeric, categorical, excluded
    
    def build_pipeline(self, numeric_features: list, categorical_features: list):
        """
        Build a sklearn Pipeline with ColumnTransformer for consistent preprocessing.
        
        This ensures the exact same feature schema between fit and transform.
        """
        numeric_transformer = Pipeline(steps=[
            ('imputer', SimpleImputer(strategy='median')),
            ('scaler', StandardScaler())
        ])
        
        categorical_transformer = Pipeline(steps=[
            ('imputer', SimpleImputer(strategy='most_frequent')),
            ('onehot', OneHotEncoder(handle_unknown='ignore', sparse_output=False))
        ])
        
        preprocessor = ColumnTransformer(
            transformers=[
                ('num', numeric_transformer, numeric_features),
                ('cat', categorical_transformer, categorical_features)
            ],
            remainder='drop'  # Drop any columns not explicitly handled
        )
        
        self.pipeline = Pipeline(steps=[
            ('preprocessor', preprocessor),
            ('variance_threshold', VarianceThreshold(threshold=0.01))  # Remove near-constant features
        ])
        
        logger.info(f"Built pipeline with {len(numeric_features)} numeric and {len(categorical_features)} categorical features")
    
    def fit(self, df: pd.DataFrame) -> dict:
        """
        Fit the preprocessing pipeline on the dataset.
        
        Returns: Analysis information
        """
        # Detect column types
        column_info = self.detect_column_types(df)
        
        # Select features
        numeric, categorical, excluded = self.select_features(df, column_info)
        
        # Store feature lists
        self.numeric_features = numeric
        self.categorical_features = categorical
        self.excluded_features = excluded
        
        # Validate we have features
        if not numeric and not categorical:
            raise ValueError(
                "No suitable features found for analysis. "
                "The dataset appears to contain only identifiers, text, or constant columns. "
                "Please upload a dataset with measurable attributes."
            )
        
        # Build pipeline
        self.build_pipeline(numeric, categorical)
        
        # Fit pipeline
        self.pipeline.fit(df)
        
        # Store feature names (for consistency)
        # Try to get feature names from ColumnTransformer
        try:
            if hasattr(self.pipeline.named_steps['preprocessor'], 'get_feature_names_out'):
                self.feature_names_out = self.pipeline.named_steps['preprocessor'].get_feature_names_out()
            else:
                # Fallback: use numeric + categorical feature names
                self.feature_names_out = numeric + categorical
        except:
            self.feature_names_out = numeric + categorical
        
        # Store analysis (convert numpy types to native Python)
        self.analysis = {
            'original_shape': [int(df.shape[0]), int(df.shape[1])],
            'numeric_features': int(len(numeric)),
            'categorical_features': int(len(categorical)),
            'excluded_features': excluded,
            'column_types': column_info,
            'feature_names': list(self.feature_names_out) if self.feature_names_out is not None else []
        }
        
        logger.info(f"Fitted pipeline with {len(self.feature_names_out)} output features")
        return self.analysis
    
    def transform(self, df: pd.DataFrame) -> np.ndarray:
        """
        Transform data using the fitted pipeline.
        
        This will ALWAYS produce the same feature schema as fit.
        """
        if self.pipeline is None:
            raise ValueError("Pipeline not fitted. Call fit() first.")
        
        X = self.pipeline.transform(df)
        
        # Validate output
        if X.shape[0] == 0:
            raise ValueError("Transform produced empty feature matrix.")
        
        if X.shape[1] == 0:
            raise ValueError(
                "Transform produced zero features. "
                "All features were filtered out as constant or near-constant."
            )
        
        return X
    
    def fit_transform(self, df: pd.DataFrame) -> tuple:
        """
        Fit and transform in one step.
        
        Returns: (X_transformed, analysis_info)
        """
        analysis = self.fit(df)
        X = self.transform(df)
        return X, analysis
