"""
Dataset Detection Utility
Automatically identifies which Kaggle dataset has been uploaded based on column names.
"""

import pandas as pd
from typing import Tuple, Optional


class DatasetDetector:
    """
    Detects the type of dataset based on column names.
    Supports two Kaggle datasets:
    1. Daily Transactions Dataset (prasad22)
    2. Bank Transaction Dataset for Fraud Detection (valakhorasani)
    """
    
    # Dataset 1: Daily Transactions Dataset (prasad22)
    DATASET1_COLUMNS = {
        'date', 'mode', 'category', 'subcategory', 
        'note', 'amount', 'income/expense', 'currency'
    }
    
    # Dataset 2: Bank Transaction Dataset for Fraud Detection (valakhorasani)
    DATASET2_COLUMNS = {
        'transactionid', 'accountid', 'transactionamount', 
        'transactiondate', 'previoustransactiondate', 'transactiontype',
        'location', 'deviceid', 'ip address', 'merchantid',
        'accountbalance', 'channel', 'customerage', 
        'customeroccupation', 'transactionduration', 'loginattempts'
    }
    
    # Simple dataset (synthetic data for testing)
    SIMPLE_COLUMNS = {
        'transaction_id', 'amount', 'location', 'timestamp',
        'business_account', 'label', 'location_flag', 'odd_time', 'large_amount'
    }
    
    # Synthetic Money Laundering dataset
    SYNTHETIC_ML_COLUMNS = {
        'transaction_id', 'timestamp', 'sender_id', 'receiver_id', 'amount', 'currency',
        'payment_channel', 'city', 'country', 'merchant_category', 'transaction_type',
        'risk_score', 'is_structured', 'rapid_movement_flag', 'suspicious_flag', 'ml_label'
    }
    
    @staticmethod
    def normalize_column_name(col: str) -> str:
        """
        Normalize column name to lowercase for comparison.
        """
        return col.strip().lower()
    
    @classmethod
    def detect_dataset(cls, file_path: str) -> Tuple[str, Optional[str]]:
        """
        Detect which dataset the uploaded file belongs to.
        If no known dataset is matched, returns 'generic' to allow processing any CSV/Excel.
        
        Args:
            file_path: Path to the uploaded CSV or Excel file
            
        Returns:
            Tuple of (dataset_type, error_message)
            dataset_type: 'dataset1', 'dataset2', 'simple', 'synthetic_ml', or 'generic'
            error_message: None if successful, error message if unsupported
        """
        try:
            # Read the file
            if file_path.endswith('.csv'):
                df = pd.read_csv(file_path, nrows=1)
            elif file_path.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(file_path, nrows=1)
            else:
                return 'unknown', "Unsupported file format. Please upload CSV or Excel."
            
            # Get column names (normalized to lowercase)
            columns = set(cls.normalize_column_name(col) for col in df.columns)
            
            # Check for Dataset 1 (Daily Transactions)
            dataset1_match = len(columns.intersection(cls.DATASET1_COLUMNS))
            dataset1_threshold = len(cls.DATASET1_COLUMNS) * 0.6  # 60% match threshold
            
            if dataset1_match >= dataset1_threshold:
                return 'dataset1', None
            
            # Check for Dataset 2 (Bank Transaction Fraud Detection)
            dataset2_match = len(columns.intersection(cls.DATASET2_COLUMNS))
            dataset2_threshold = len(cls.DATASET2_COLUMNS) * 0.6  # 60% match threshold
            
            if dataset2_match >= dataset2_threshold:
                return 'dataset2', None
            
            # Check for Simple dataset (synthetic data for testing)
            simple_match = len(columns.intersection(cls.SIMPLE_COLUMNS))
            simple_threshold = len(cls.SIMPLE_COLUMNS) * 0.5  # 50% match threshold
            
            if simple_match >= simple_threshold:
                return 'simple', None
            
            # Check for Synthetic Money Laundering dataset
            synthetic_ml_match = len(columns.intersection(cls.SYNTHETIC_ML_COLUMNS))
            synthetic_ml_threshold = len(cls.SYNTHETIC_ML_COLUMNS) * 0.6  # 60% match threshold
            
            if synthetic_ml_match >= synthetic_ml_threshold:
                return 'synthetic_ml', None
            
            # No match found - return 'generic' to allow processing any dataset
            return 'generic', None
            
        except Exception as e:
            return 'unknown', f"Error reading file: {str(e)}"
    
    @classmethod
    def get_dataset_info(cls, dataset_type: str) -> dict:
        """
        Get information about a specific dataset type.
        
        Args:
            dataset_type: 'dataset1' or 'dataset2'
            
        Returns:
            Dictionary with dataset information
        """
        if dataset_type == 'dataset1':
            return {
                'name': 'Daily Transactions Dataset',
                'source': 'prasad22',
                'columns': list(cls.DATASET1_COLUMNS),
                'spider_chart_axes': [
                    'Amount', 'Mode', 'Category', 'Subcategory', 
                    'Income/Expense', 'Frequency', 'Time', 
                    'Risk Score', 'Behavior Score', 'Transaction Pattern'
                ]
            }
        elif dataset_type == 'dataset2':
            return {
                'name': 'Bank Transaction Dataset for Fraud Detection',
                'source': 'valakhorasani',
                'columns': list(cls.DATASET2_COLUMNS),
                'spider_chart_axes': [
                    'Transaction Amount', 'Customer Risk', 'Transaction Type',
                    'Device Risk', 'Merchant Risk', 'Location Risk',
                    'Frequency', 'Time Risk', 'Network Risk',
                    'Historical Behaviour', 'Velocity', 'AML Score'
                ]
            }
        elif dataset_type == 'simple':
            return {
                'name': 'Simple Synthetic Dataset',
                'source': 'Generated for testing',
                'columns': list(cls.SIMPLE_COLUMNS),
                'spider_chart_axes': [
                    'Amount', 'Location Risk', 'Time Risk', 
                    'Business Account', 'Large Amount', 'Risk Score'
                ]
            }
        else:
            return {
                'name': 'Unknown Dataset',
                'source': 'unknown',
                'columns': [],
                'spider_chart_axes': []
            }


# Convenience function
def detect_dataset(file_path: str) -> Tuple[str, Optional[str]]:
    """
    Convenience function to detect dataset type.
    
    Args:
        file_path: Path to the uploaded file
        
    Returns:
        Tuple of (dataset_type, error_message)
    """
    return DatasetDetector.detect_dataset(file_path)
