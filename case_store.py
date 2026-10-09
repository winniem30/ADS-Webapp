"""SQLite storage for analyst cases and append-only review history."""
import sqlite3


def init_case_schema(path):
    connection = sqlite3.connect(path, timeout=20)
    try:
        connection.executescript('''
        PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS investigation_cases (
            case_id TEXT PRIMARY KEY,
            transaction_id TEXT NOT NULL UNIQUE,
            owner_uid TEXT NOT NULL,
            assignee_uid TEXT,
            status TEXT NOT NULL CHECK(status IN ('new_alert','in_review','information_required','marked_for_reporting','cleared','closed')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_cases_owner_updated ON investigation_cases(owner_uid,updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cases_assignee_updated ON investigation_cases(assignee_uid,updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cases_status_updated ON investigation_cases(status,updated_at DESC);
        CREATE TABLE IF NOT EXISTS case_notes (
            note_id TEXT PRIMARY KEY,
            case_id TEXT NOT NULL REFERENCES investigation_cases(case_id),
            author_uid TEXT NOT NULL,
            author_label TEXT NOT NULL,
            note TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS case_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id TEXT NOT NULL REFERENCES investigation_cases(case_id),
            actor_uid TEXT NOT NULL,
            actor_label TEXT NOT NULL,
            action TEXT NOT NULL,
            prior_status TEXT,
            new_status TEXT,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_case_events_case ON case_events(case_id,event_id);
        CREATE INDEX IF NOT EXISTS idx_case_notes_case ON case_notes(case_id,created_at);
        CREATE TRIGGER IF NOT EXISTS case_events_no_update BEFORE UPDATE ON case_events
        BEGIN SELECT RAISE(ABORT,'case audit events are immutable'); END;
        CREATE TRIGGER IF NOT EXISTS case_events_no_delete BEFORE DELETE ON case_events
        BEGIN SELECT RAISE(ABORT,'case audit events are immutable'); END;
        CREATE TRIGGER IF NOT EXISTS case_notes_no_update BEFORE UPDATE ON case_notes
        BEGIN SELECT RAISE(ABORT,'case notes are append-only'); END;
        CREATE TRIGGER IF NOT EXISTS case_notes_no_delete BEFORE DELETE ON case_notes
        BEGIN SELECT RAISE(ABORT,'case notes are append-only'); END;
        CREATE TABLE IF NOT EXISTS analysis_runs (
            run_id TEXT PRIMARY KEY,
            owner_uid TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            upload_path TEXT NOT NULL,
            file_size INTEGER NOT NULL,
            mapping_json TEXT NOT NULL,
            schema_json TEXT NOT NULL,
            row_count INTEGER,
            mode TEXT,
            status TEXT NOT NULL CHECK(status IN ('uploaded','queued','processing','complete','failed','cancelled')),
            model_version TEXT,
            threshold REAL,
            metrics_json TEXT,
            summary_json TEXT,
            error TEXT,
            uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_analysis_owner_date ON analysis_runs(owner_uid,uploaded_at DESC);
        CREATE TABLE IF NOT EXISTS analysis_transactions (
            run_id TEXT NOT NULL REFERENCES analysis_runs(run_id) ON DELETE CASCADE,
            owner_uid TEXT NOT NULL,
            transaction_id TEXT NOT NULL,
            source_row INTEGER NOT NULL,
            timestamp TEXT NOT NULL,
            from_bank TEXT NOT NULL,
            from_account TEXT NOT NULL,
            to_bank TEXT NOT NULL,
            to_account TEXT NOT NULL,
            amount_received REAL NOT NULL,
            receiving_currency TEXT NOT NULL,
            amount_paid REAL NOT NULL,
            payment_currency TEXT NOT NULL,
            payment_format TEXT NOT NULL,
            actual_label INTEGER,
            risk_score REAL NOT NULL,
            predicted_class INTEGER NOT NULL,
            threshold REAL NOT NULL,
            model_version TEXT NOT NULL,
            PRIMARY KEY(run_id,transaction_id)
        );
        CREATE INDEX IF NOT EXISTS idx_analysis_tx_owner_date ON analysis_transactions(owner_uid,run_id,timestamp);
        CREATE INDEX IF NOT EXISTS idx_analysis_tx_risk ON analysis_transactions(run_id,risk_score DESC);
        ''')
        connection.commit()
    finally:
        connection.close()


def connect_case_db(path):
    connection = sqlite3.connect(path, timeout=20)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys=ON')
    connection.execute('PRAGMA busy_timeout=20000')
    return connection
