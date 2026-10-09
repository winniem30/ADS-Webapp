"""IBM HI-Small ingestion, scalable feature extraction, and model training.

This path deliberately keeps the IBM dataset's source columns intact.  The
duplicate source header ``Account`` is parsed by pandas as ``Account`` and
``Account.1`` (destination account) and is validated before processing.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.feature_extraction import FeatureHasher
from sklearn.linear_model import SGDClassifier
from sklearn.metrics import (average_precision_score, confusion_matrix,
                             precision_recall_curve, precision_score,
                             recall_score, f1_score, roc_auc_score)

EXPECTED = ['Timestamp', 'From Bank', 'Account', 'To Bank', 'Account.1',
            'Amount Received', 'Receiving Currency', 'Amount Paid',
            'Payment Currency', 'Payment Format', 'Is Laundering']
VERSION = 'IBM-AML-HI-Small'
CHUNKSIZE = 100_000


def validate_header(path):
    header = list(pd.read_csv(path, nrows=0).columns)
    if header != EXPECTED:
        raise ValueError(f'Unexpected HI-Small schema: {header!r}')
    return header


def _features(frame):
    """Build ID-free, leakage-free features; account IDs are investigation keys only."""
    aliases={'timestamp':'Timestamp','from_bank':'From Bank','from_account':'Account',
             'to_bank':'To Bank','to_account':'Account.1','amount_received':'Amount Received',
             'receiving_currency':'Receiving Currency','amount_paid':'Amount Paid',
             'payment_currency':'Payment Currency','payment_format':'Payment Format'}
    frame=frame.rename(columns={k:v for k,v in aliases.items() if k in frame.columns})
    ts = pd.to_datetime(frame['Timestamp'], errors='coerce')
    # The compact feature dictionary is hashed into a fixed sparse space.
    received=np.log1p(pd.to_numeric(frame['Amount Received'],errors='coerce').clip(lower=0).fillna(0).to_numpy())
    paid=np.log1p(pd.to_numeric(frame['Amount Paid'],errors='coerce').clip(lower=0).fillna(0).to_numpy())
    hours=np.where(ts.notna(),ts.dt.hour.fillna(-1),-1).astype(int)
    weekdays=np.where(ts.notna(),ts.dt.dayofweek.fillna(-1),-1).astype(int)
    from_b=frame['From Bank'].astype(str).to_numpy(); to_b=frame['To Bank'].astype(str).to_numpy()
    rc=frame['Receiving Currency'].astype(str).to_numpy(); pc=frame['Payment Currency'].astype(str).to_numpy(); fmt=frame['Payment Format'].astype(str).to_numpy()
    # zip over already-vectorized arrays avoids pandas row-Series allocation.
    return [{'log_received':float(a),'log_paid':float(b),'hour':int(h),'weekday':int(w),
             'recv_currency='+r:1,'pay_currency='+p:1,'format='+f:1,'same_bank':int(fb==tb)}
            for a,b,h,w,r,p,f,fb,tb in zip(received,paid,hours,weekdays,rc,pc,fmt,from_b,to_b)]


def ingest(path, db_path='data/ibm_hi_small.sqlite3', chunk_size=CHUNKSIZE, force=False):
    """Repeatable chunked import; dataset plus source row is the stable transaction ID."""
    validate_header(path)
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA synchronous=NORMAL')
    conn.execute('PRAGMA wal_autocheckpoint=100000')
    # Bulk load first, build secondary indexes once at the end.
    conn.executescript('DROP INDEX IF EXISTS ix_tx_time; DROP INDEX IF EXISTS ix_tx_from; DROP INDEX IF EXISTS ix_tx_to; DROP INDEX IF EXISTS ix_tx_label_time;')
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS transactions (
      transaction_id TEXT PRIMARY KEY, source_row INTEGER NOT NULL UNIQUE,
      timestamp TEXT NOT NULL, from_bank TEXT NOT NULL, from_account TEXT NOT NULL,
      to_bank TEXT NOT NULL, to_account TEXT NOT NULL,
      amount_received REAL NOT NULL, receiving_currency TEXT NOT NULL,
      amount_paid REAL NOT NULL, payment_currency TEXT NOT NULL,
      payment_format TEXT NOT NULL, actual_label INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS dataset_imports (
      dataset_version TEXT PRIMARY KEY, imported_at TEXT, source_path TEXT,
      source_bytes INTEGER, row_count INTEGER, positive_count INTEGER,
      missing_count INTEGER, header_json TEXT, status TEXT);
    ''')
    count = pos = missing = source_offset = 0
    # Existing complete import is reused; no duplicate ingestion on restart.
    done = conn.execute('SELECT row_count FROM dataset_imports WHERE dataset_version=? AND status=?', (VERSION, 'complete')).fetchone()
    if done and not force and conn.execute('SELECT COUNT(*) FROM transactions').fetchone()[0] == done[0]:
        conn.close()
        return {'status': 'already_imported', 'rows': done[0]}
    conn.execute('DELETE FROM transactions')
    for chunk in pd.read_csv(path, dtype={'From Bank': str, 'To Bank': str, 'Account': str, 'Account.1': str}, chunksize=chunk_size):
        raw_count = len(chunk)
        missing += int(chunk.isna().sum().sum())
        chunk['Timestamp'] = pd.to_datetime(chunk['Timestamp'], errors='coerce').dt.strftime('%Y-%m-%d %H:%M:%S')
        for c in ['Amount Received', 'Amount Paid']:
            chunk[c] = pd.to_numeric(chunk[c], errors='coerce')
        chunk['Is Laundering'] = pd.to_numeric(chunk['Is Laundering'], errors='coerce')
        valid = chunk['Timestamp'].notna() & chunk['Amount Received'].notna() & chunk['Amount Paid'].notna() & chunk['Is Laundering'].isin([0, 1])
        chunk = chunk.loc[valid]
        indices=chunk.index.to_numpy(dtype=np.int64)+source_offset+1
        rows=[(f'HI-Small-{int(i):010d}',int(i),t,str(fb),str(fa),str(tb),str(ta),float(ar),str(rc),float(ap),str(pc),str(pf),int(y))
              for i,t,fb,fa,tb,ta,ar,rc,ap,pc,pf,y in zip(indices,chunk['Timestamp'].to_numpy(),chunk['From Bank'].to_numpy(),chunk['Account'].to_numpy(),chunk['To Bank'].to_numpy(),chunk['Account.1'].to_numpy(),chunk['Amount Received'].to_numpy(),chunk['Receiving Currency'].to_numpy(),chunk['Amount Paid'].to_numpy(),chunk['Payment Currency'].to_numpy(),chunk['Payment Format'].to_numpy(),chunk['Is Laundering'].to_numpy())]
        conn.executemany('INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)', rows)
        count += len(rows)
        source_offset += raw_count
        pos += sum(x[-1] for x in rows)
        conn.commit()
    conn.executescript('''CREATE INDEX IF NOT EXISTS ix_tx_time ON transactions(timestamp);
      CREATE INDEX IF NOT EXISTS ix_tx_from ON transactions(from_bank,from_account);
      CREATE INDEX IF NOT EXISTS ix_tx_to ON transactions(to_bank,to_account);
      CREATE INDEX IF NOT EXISTS ix_tx_label_time ON transactions(actual_label,timestamp);''')
    conn.execute('INSERT OR REPLACE INTO dataset_imports VALUES (?,?,?,?,?,?,?,?,?)',
        (VERSION, datetime.now(timezone.utc).isoformat(), str(Path(path).resolve()), os.path.getsize(path), count, pos, missing, json.dumps(EXPECTED), 'complete'))
    conn.commit(); conn.execute('PRAGMA wal_checkpoint(TRUNCATE)'); conn.close()
    return {'status': 'complete', 'rows': count, 'positive': pos, 'missing_cells': missing, 'dataset_version': VERSION}


def _read_chunks(path, dates, chunk_size=CHUNKSIZE):
    for df in pd.read_csv(path, dtype={'From Bank': str, 'To Bank': str, 'Account': str, 'Account.1': str}, chunksize=chunk_size):
        df['Timestamp'] = pd.to_datetime(df.Timestamp, errors='coerce')
        df = df[df.Timestamp.dt.strftime('%Y-%m-%d').isin(dates)]
        if len(df):
            yield df


def train(path, out='models/ibm_hi_small_sgd.joblib', report='reports/ibm_hi_small_metrics.json'):
    """Train a reproducible chronological SGD baseline, using training rows only."""
    validate_header(path)
    # HI-Small is highly concentrated on Sep 1-10. Reserve a sufficiently large
    # chronological holdout: Sep 1-8 train, Sep 9 validation, Sep 10-18 test.
    train_days = {f'2022-09-{d:02}' for d in range(1, 9)}
    val_days = {'2022-09-09'}
    test_days = {f'2022-09-{d:02}' for d in range(10, 19)}
    hasher = FeatureHasher(n_features=2**18, input_type='dict', alternate_sign=False)
    model = SGDClassifier(loss='log_loss', alpha=1e-6, random_state=42, max_iter=1, tol=None)
    start = time.perf_counter(); seen = False; train_n = 0
    for df in _read_chunks(path, train_days):
        X = hasher.transform(_features(df)); y = df['Is Laundering'].astype(int).to_numpy()
        # Fixed inverse-frequency class weights approximate the full source
        # prevalence (5,177/5,078,345) and avoid batch-dependent weighting.
        model.partial_fit(X, y, classes=np.array([0, 1]), sample_weight=np.where(y == 1, 981.0, 1.0))
        train_n += len(y); seen = True
    if not seen: raise ValueError('No training rows found in chronological training dates.')
    def probabilities(days):
        ys=[]; ps=[]
        for df in _read_chunks(path, days):
            ys.extend(df['Is Laundering'].astype(int).tolist())
            ps.extend(model.predict_proba(hasher.transform(_features(df)))[:,1].tolist())
        return np.asarray(ys), np.asarray(ps)
    vy, vp = probabilities(val_days)
    precision, recall, thresholds = precision_recall_curve(vy, vp)
    fs = 2 * precision[:-1] * recall[:-1] / np.maximum(precision[:-1] + recall[:-1], 1e-12)
    threshold = float(thresholds[int(np.nanargmax(fs))]) if len(thresholds) else 0.5
    ty, tp = probabilities(test_days)
    pred = (tp >= threshold).astype(int)
    metrics = {'dataset_version': VERSION, 'model_version': 'hi-small-sgd-v1', 'feature_count': 8,
        'excluded_features': ['Timestamp raw', 'Account IDs', 'transaction_id', 'Is Laundering'],
        'split': {'train_dates': ['2022-09-01','2022-09-08'], 'validation_dates': sorted(val_days), 'test_dates': ['2022-09-10','2022-09-18']},
        'train_rows': train_n, 'validation_rows': len(vy), 'test_rows': len(ty),
        'positive_prevalence': float(ty.mean()) if len(ty) else None, 'threshold': threshold,
        'precision': float(precision_score(ty,pred,zero_division=0)), 'recall': float(recall_score(ty,pred,zero_division=0)),
        'f1': float(f1_score(ty,pred,zero_division=0)), 'average_precision': float(average_precision_score(ty,tp)) if len(np.unique(ty))>1 else None,
        'roc_auc': float(roc_auc_score(ty,tp)) if len(np.unique(ty))>1 else None,
        'confusion_matrix_tn_fp_fn_tp': confusion_matrix(ty,pred,labels=[0,1]).ravel().tolist(),
        'training_seconds': time.perf_counter()-start}
    Path(out).parent.mkdir(parents=True,exist_ok=True); Path(report).parent.mkdir(parents=True,exist_ok=True)
    joblib.dump({'model':model,'hasher':hasher,'threshold':threshold,'model_version':metrics['model_version'],'features':metrics['excluded_features']},out)
    Path(report).write_text(json.dumps(metrics,indent=2),encoding='utf-8')
    return metrics


def score_rows(rows, artifact='models/ibm_hi_small_sgd.joblib'):
    bundle=joblib.load(artifact); df=pd.DataFrame(rows)
    aliases={'timestamp':'Timestamp','from_bank':'From Bank','from_account':'Account',
             'to_bank':'To Bank','to_account':'Account.1','amount_received':'Amount Received',
             'receiving_currency':'Receiving Currency','amount_paid':'Amount Paid',
             'payment_currency':'Payment Currency','payment_format':'Payment Format'}
    df=df.rename(columns={k:v for k,v in aliases.items() if k in df.columns})
    p=bundle['model'].predict_proba(bundle['hasher'].transform(_features(df)))[:,1]
    return [{'risk_score':float(x),'predicted_class':int(x>=bundle['threshold']),'threshold':bundle['threshold'],'model_version':bundle['model_version']} for x in p]


def compare_thresholds(path, report='reports/ibm_hi_small_metrics.json', artifact='models/ibm_hi_small_sgd.joblib'):
    """Measure false-positive/false-negative tradeoffs on held-out data only."""
    from sklearn.metrics import confusion_matrix
    bundle=joblib.load(artifact); truth=[]; scores=[]
    for df in _read_chunks(path,{f'2022-09-{d:02}' for d in range(10,19)}):
        truth.extend(df['Is Laundering'].astype(int).tolist())
        scores.extend(bundle['model'].predict_proba(bundle['hasher'].transform(_features(df)))[:,1].tolist())
    y=np.asarray(truth); p=np.asarray(scores)
    thresholds=sorted(set([float(bundle['threshold']),0.01,0.5]))
    table=[]
    for threshold in thresholds:
        pred=(p>=threshold).astype(int); tn,fp,fn,tp=confusion_matrix(y,pred,labels=[0,1]).ravel()
        table.append({'threshold':threshold,'precision':float(precision_score(y,pred,zero_division=0)),
            'recall':float(recall_score(y,pred,zero_division=0)),'false_positives':int(fp),
            'false_negatives':int(fn),'true_positives':int(tp),'true_negatives':int(tn)})
    path=Path(report)
    metrics=json.loads(path.read_text(encoding='utf-8')); metrics['threshold_comparison_test']=table
    path.write_text(json.dumps(metrics,indent=2),encoding='utf-8')
    return table


def explain_row(row, artifact='models/ibm_hi_small_sgd.joblib', top=5):
    """Explain a linear hashed prediction with additive feature-bucket contributions."""
    bundle=joblib.load(artifact)
    aliases={'timestamp':'Timestamp','from_bank':'From Bank','from_account':'Account',
             'to_bank':'To Bank','to_account':'Account.1','amount_received':'Amount Received',
             'receiving_currency':'Receiving Currency','amount_paid':'Amount Paid',
             'payment_currency':'Payment Currency','payment_format':'Payment Format'}
    frame=pd.DataFrame([row]).rename(columns={k:v for k,v in aliases.items() if k in row})
    features=_features(frame)[0]; coef=bundle['model'].coef_[0]
    contrib=[]
    for name,value in features.items():
        if not value: continue
        hashed=bundle['hasher'].transform([{name:value}])
        index=int(hashed.indices[0])
        contrib.append({'feature':name,'contribution_log_odds':float(coef[index]*value)})
    full=bundle['hasher'].transform([features]); probability=float(bundle['model'].predict_proba(full)[0,1])
    return {'model_version':bundle['model_version'],'risk_score':probability,'threshold':float(bundle['threshold']),
            'predicted_class':int(probability>=bundle['threshold']),
            'intercept_log_odds':float(bundle['model'].intercept_[0]),
            'positive_contributors':sorted([x for x in contrib if x['contribution_log_odds']>0],key=lambda x:x['contribution_log_odds'],reverse=True)[:top],
            'negative_contributors':sorted([x for x in contrib if x['contribution_log_odds']<0],key=lambda x:x['contribution_log_odds'])[:top],
            'method':'Additive coefficients in the trained FeatureHasher space. Hashed bucket collisions can combine feature effects.'}


def estimate_scoring(db_path='data/ibm_hi_small.sqlite3', artifact='models/ibm_hi_small_sgd.joblib', sample_size=10000):
    """Benchmark one bounded batch and project runtime/storage before a full score."""
    import shutil
    from pathlib import Path
    bundle=joblib.load(artifact); conn=sqlite3.connect(db_path); conn.row_factory=sqlite3.Row
    try:
        total=conn.execute('SELECT COUNT(*) FROM transactions').fetchone()[0]
        rows=conn.execute('SELECT * FROM transactions ORDER BY source_row LIMIT ?', (sample_size,)).fetchall()
    finally: conn.close()
    if not rows: raise ValueError('No transaction rows are available for scoring.')
    frame=pd.DataFrame([dict(x) for x in rows]); started=time.perf_counter()
    bundle['model'].predict_proba(bundle['hasher'].transform(_features(frame)))
    seconds=time.perf_counter()-started; throughput=len(rows)/max(seconds,0.001)
    # SQLite row + primary-key/index overhead usually varies by filesystem; use
    # a conservative 250 bytes/score row for capacity planning.
    estimated_bytes=int(total*250); free=shutil.disk_usage(Path(db_path).resolve().parent).free
    return {'rows':total,'sample_rows':len(rows),'sample_seconds':seconds,'rows_per_second':throughput,
            'estimated_seconds':total/max(throughput,1)*1.25,'estimated_minutes':total/max(throughput,1)*1.25/60,
            'estimated_storage_bytes':estimated_bytes,'free_disk_bytes':free,'storage_available':free>estimated_bytes*1.2}


def score_database(db_path='data/ibm_hi_small.sqlite3', artifact='models/ibm_hi_small_sgd.joblib', chunk_size=10000):
    """Restart-safe, chunked risk scoring. Existing same-version scores are retained."""
    bundle=joblib.load(artifact); version=bundle['model_version']; threshold=float(bundle['threshold'])
    conn=sqlite3.connect(db_path,timeout=60); conn.row_factory=sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL'); conn.execute('PRAGMA busy_timeout=60000')
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS transaction_scores (
        transaction_id TEXT NOT NULL, model_version TEXT NOT NULL, risk_score REAL NOT NULL,
        predicted_class INTEGER NOT NULL, threshold REAL NOT NULL, scored_at TEXT NOT NULL,
        PRIMARY KEY(transaction_id,model_version));
      CREATE INDEX IF NOT EXISTS ix_scores_model_risk ON transaction_scores(model_version,risk_score);
      CREATE INDEX IF NOT EXISTS ix_scores_model_class ON transaction_scores(model_version,predicted_class);
      CREATE TABLE IF NOT EXISTS score_progress (
        model_version TEXT PRIMARY KEY, status TEXT NOT NULL, rows_scored INTEGER NOT NULL,
        total_rows INTEGER NOT NULL, started_at TEXT NOT NULL, updated_at TEXT NOT NULL, last_error TEXT);
    ''')
    now=datetime.now(timezone.utc).isoformat()
    conn.execute('INSERT INTO score_progress VALUES (?,?,?,?,?,?,NULL) ON CONFLICT(model_version) DO UPDATE SET status="running",updated_at=excluded.updated_at,last_error=NULL',
                 (version,'running',0,0,now,now)); conn.commit()
    total=conn.execute('SELECT COUNT(*) FROM transactions').fetchone()[0]
    conn.execute('UPDATE score_progress SET total_rows=?,started_at=CASE WHEN rows_scored=0 THEN ? ELSE started_at END WHERE model_version=?',(total,now,version)); conn.commit()
    try:
        while True:
            rows=conn.execute('''SELECT t.* FROM transactions t LEFT JOIN transaction_scores s
              ON s.transaction_id=t.transaction_id AND s.model_version=? WHERE s.transaction_id IS NULL
              ORDER BY t.source_row LIMIT ?''',(version,chunk_size)).fetchall()
            if not rows: break
            frame=pd.DataFrame([dict(x) for x in rows])
            probs=bundle['model'].predict_proba(bundle['hasher'].transform(_features(frame)))[:,1]
            stamped=datetime.now(timezone.utc).isoformat()
            payload=[(r['transaction_id'],version,float(p),int(p>=threshold),threshold,stamped) for r,p in zip(rows,probs)]
            conn.executemany('INSERT OR IGNORE INTO transaction_scores VALUES (?,?,?,?,?,?)',payload)
            conn.execute('UPDATE score_progress SET rows_scored=rows_scored+?,updated_at=? WHERE model_version=?',(len(payload),stamped,version)); conn.commit()
        stamped=datetime.now(timezone.utc).isoformat()
        conn.execute('UPDATE score_progress SET status="complete",updated_at=? WHERE model_version=?',(stamped,version)); conn.commit()
    except Exception as exc:
        stamped=datetime.now(timezone.utc).isoformat()
        conn.execute('UPDATE score_progress SET status="failed",updated_at=?,last_error=? WHERE model_version=?',(stamped,str(exc)[:1000],version)); conn.commit(); raise
    finally: conn.close()
    return {'model_version':version,'status':'complete','rows':total}
