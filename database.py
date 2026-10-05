"""
Database module for Money Laundering Detection Platform
Handles SQLite database operations, schema creation, and data management
"""

import sqlite3
import json
from datetime import datetime
from contextlib import contextmanager
from config import Config


class DatabaseManager:
    """Manages all database operations for the AML platform"""
    
    def __init__(self, db_path=None):
        """Initialize database manager with path"""
        self.db_path = db_path or Config.DATABASE_PATH
        self.init_database()
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def init_database(self):
        """Initialize database with all required tables"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Users table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    email TEXT,
                    role TEXT DEFAULT 'analyst',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP
                )
            """)
            
            # Transactions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    transaction_id TEXT,
                    timestamp TEXT,
                    sender TEXT,
                    receiver TEXT,
                    amount REAL,
                    bank TEXT,
                    state TEXT,
                    merchant TEXT,
                    device TEXT,
                    location TEXT,
                    prediction INTEGER,
                    probability REAL,
                    risk_score REAL,
                    risk_level TEXT,
                    model_used TEXT,
                    confidence_score REAL,
                    execution_time REAL,
                    features_json TEXT,
                    upload_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (upload_id) REFERENCES uploads(id)
                )
            """)
            
            # Uploads table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS uploads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL,
                    original_filename TEXT NOT NULL,
                    file_size INTEGER,
                    row_count INTEGER,
                    dataset_type TEXT,
                    status TEXT DEFAULT 'processing',
                    model_used TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP
                )
            """)
            
            # Add dataset_type column if it doesn't exist (migration)
            try:
                cursor.execute("ALTER TABLE uploads ADD COLUMN dataset_type TEXT")
            except sqlite3.OperationalError:
                # Column already exists, ignore error
                pass
            
            # Alerts table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    transaction_id INTEGER,
                    alert_type TEXT NOT NULL,
                    severity TEXT,
                    message TEXT,
                    is_read BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (transaction_id) REFERENCES transactions(id)
                )
            """)
            
            # Model performance table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS model_performance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_name TEXT NOT NULL,
                    accuracy REAL,
                    precision REAL,
                    recall REAL,
                    f1_score REAL,
                    prediction_time REAL,
                    memory_usage REAL,
                    test_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # System logs table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS system_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    level TEXT NOT NULL,
                    module TEXT,
                    message TEXT,
                    details TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Network analysis table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS network_analysis (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    upload_id INTEGER,
                    node_count INTEGER,
                    edge_count INTEGER,
                    suspicious_paths INTEGER,
                    analysis_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (upload_id) REFERENCES uploads(id)
                )
            """)
            
            # Create indexes for better performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_risk ON transactions(risk_level)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_prediction ON transactions(prediction)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_read ON alerts(is_read)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_uploads_status ON uploads(status)")
    
    def insert_user(self, username, password_hash, email=None, role='analyst'):
        """Insert a new user into the database"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO users (username, password_hash, email, role)
                VALUES (?, ?, ?, ?)
            """, (username, password_hash, email, role))
            return cursor.lastrowid
    
    def get_user(self, username):
        """Retrieve user by username"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
            return cursor.fetchone()
    
    def update_last_login(self, user_id):
        """Update user's last login timestamp"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?
            """, (user_id,))
    
    def insert_upload(self, filename, original_filename, file_size, dataset_type=None):
        """Insert a new upload record"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO uploads (filename, original_filename, file_size, dataset_type)
                VALUES (?, ?, ?, ?)
            """, (filename, original_filename, file_size, dataset_type))
            return cursor.lastrowid
    
    def update_upload(self, upload_id, row_count, status, model_used=None):
        """Update upload record with processing results"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE uploads 
                SET row_count = ?, status = ?, model_used = ?, completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (row_count, status, model_used, upload_id))
    
    def insert_transaction(self, transaction_data):
        """Insert a transaction record"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO transactions (
                    transaction_id, timestamp, sender, receiver, amount, bank, state,
                    merchant, device, location, prediction, probability, risk_score,
                    risk_level, model_used, confidence_score, execution_time,
                    features_json, upload_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                transaction_data.get('transaction_id'),
                transaction_data.get('timestamp'),
                transaction_data.get('sender'),
                transaction_data.get('receiver'),
                transaction_data.get('amount'),
                transaction_data.get('bank'),
                transaction_data.get('state'),
                transaction_data.get('merchant'),
                transaction_data.get('device'),
                transaction_data.get('location'),
                transaction_data.get('prediction'),
                transaction_data.get('probability'),
                transaction_data.get('risk_score'),
                transaction_data.get('risk_level'),
                transaction_data.get('model_used'),
                transaction_data.get('confidence_score'),
                transaction_data.get('execution_time'),
                json.dumps(transaction_data.get('features', {})),
                transaction_data.get('upload_id')
            ))
            return cursor.lastrowid
    
    def get_transaction(self, transaction_id):
        """Retrieve transaction by ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,))
            return cursor.fetchone()
    
    def get_transactions(self, limit=20, offset=0, filters=None):
        """Retrieve transactions with optional filters"""
        query = "SELECT * FROM transactions WHERE 1=1"
        params = []
        
        if filters:
            if filters.get('risk_level'):
                query += " AND risk_level = ?"
                params.append(filters['risk_level'])
            if filters.get('prediction'):
                query += " AND prediction = ?"
                params.append(filters['prediction'])
            if filters.get('model_used'):
                query += " AND model_used = ?"
                params.append(filters['model_used'])
            if filters.get('min_amount'):
                query += " AND amount >= ?"
                params.append(filters['min_amount'])
            if filters.get('max_amount'):
                query += " AND amount <= ?"
                params.append(filters['max_amount'])
        
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchall()
    
    def get_dashboard_stats(self):
        """Get statistics for dashboard"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Total transactions
            cursor.execute("SELECT COUNT(*) FROM transactions")
            total_transactions = cursor.fetchone()[0]
            
            # Risk distribution
            cursor.execute("""
                SELECT risk_level, COUNT(*) as count 
                FROM transactions 
                GROUP BY risk_level
            """)
            risk_distribution = {row['risk_level']: row['count'] for row in cursor.fetchall()}
            
            # Prediction distribution
            cursor.execute("""
                SELECT prediction, COUNT(*) as count 
                FROM transactions 
                GROUP BY prediction
            """)
            prediction_distribution = {row['prediction']: row['count'] for row in cursor.fetchall()}
            
            # Recent uploads
            cursor.execute("""
                SELECT * FROM uploads 
                ORDER BY created_at DESC 
                LIMIT 5
            """)
            recent_uploads = cursor.fetchall()
            
            # Model performance
            cursor.execute("""
                SELECT model_name, accuracy, precision, recall, f1_score 
                FROM model_performance 
                ORDER BY test_date DESC 
                LIMIT 3
            """)
            model_performance = cursor.fetchall()
            
            return {
                'total_transactions': total_transactions,
                'risk_distribution': risk_distribution,
                'prediction_distribution': prediction_distribution,
                'recent_uploads': recent_uploads,
                'model_performance': model_performance
            }
    
    def insert_alert(self, transaction_id, alert_type, severity, message):
        """Insert a new alert"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO alerts (transaction_id, alert_type, severity, message)
                VALUES (?, ?, ?, ?)
            """, (transaction_id, alert_type, severity, message))
            return cursor.lastrowid
    
    def get_alerts(self, unread_only=False, limit=10):
        """Retrieve alerts"""
        query = "SELECT * FROM alerts"
        params = []
        
        if unread_only:
            query += " WHERE is_read = 0"
        
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchall()
    
    def mark_alert_read(self, alert_id):
        """Mark alert as read"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE alerts SET is_read = 1 WHERE id = ?", (alert_id,))
    
    def log_system_event(self, level, module, message, details=None):
        """Log a system event"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO system_logs (level, module, message, details)
                VALUES (?, ?, ?, ?)
            """, (level, module, message, json.dumps(details) if details else None))
    
    def search_transactions(self, search_term, field='all'):
        """Search transactions by various fields"""
        if field == 'all':
            query = """
                SELECT * FROM transactions 
                WHERE transaction_id LIKE ? 
                OR sender LIKE ? 
                OR receiver LIKE ? 
                OR bank LIKE ? 
                OR state LIKE ? 
                OR merchant LIKE ?
            """
            params = [f'%{search_term}%'] * 6
        else:
            query = f"SELECT * FROM transactions WHERE {field} LIKE ?"
            params = [f'%{search_term}%']
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchall()
    
    def get_model_performance(self, model_name=None):
        """Get model performance metrics"""
        query = "SELECT * FROM model_performance"
        params = []
        
        if model_name:
            query += " WHERE model_name = ?"
            params.append(model_name)
        
        query += " ORDER BY test_date DESC"
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchall()


# Global database instance
db = DatabaseManager()
