"""IBM HI-Small read APIs, dashboard, and bounded investigation operations."""
from __future__ import annotations

import csv
from contextlib import contextmanager
import io
import json
import os
import re
import sqlite3
from functools import lru_cache
from pathlib import Path

from flask import Blueprint, Response, jsonify, render_template, request

ibm_bp = Blueprint('ibm', __name__, url_prefix='/api/ibm')
ROOT = Path(__file__).resolve().parents[1]
DB = os.environ.get('IBM_AML_DB', str(ROOT / 'data' / 'ibm_hi_small.sqlite3'))
MODEL = os.environ.get('IBM_AML_MODEL', str(ROOT / 'models' / 'ibm_hi_small_sgd.joblib'))
METRICS = os.environ.get('IBM_AML_METRICS', str(ROOT / 'reports' / 'ibm_hi_small_metrics.json'))
MAX_PAGE = 200
MAX_GRAPH_EDGES = 300


def _open_connection():
    if not os.path.exists(DB):
        raise FileNotFoundError('IBM HI-Small database is not installed.')
    c = sqlite3.connect(DB, timeout=20)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA busy_timeout=20000')
    return c


@contextmanager
def connect():
    c = _open_connection()
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def table_exists(conn, table):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


@lru_cache(maxsize=4)
def model_version():
    if not os.path.exists(MODEL):
        return None
    try:
        import joblib
        return joblib.load(MODEL, mmap_mode='r').get('model_version')
    except Exception:
        return None


def _filters(args, scored=False, version=None):
    clauses, values = [], []
    q = (args.get('q') or '').strip()
    if q:
        if q.startswith('HI-Small-'):
            clauses.append('t.transaction_id=?'); values.append(q)
        else:
            clauses.append('(t.from_account=? OR t.to_account=? OR t.from_bank=? OR t.to_bank=?)')
            values.extend([q, q, q, q])
    for key, col in [('account', None), ('bank', None), ('payment_format', 't.payment_format'), ('label', 't.actual_label')]:
        val = args.get(key)
        if val is not None and val != '':
            if key == 'account':
                clauses.append('(t.from_account=? OR t.to_account=?)'); values.extend([val, val])
            elif key == 'bank':
                clauses.append('(t.from_bank=? OR t.to_bank=?)'); values.extend([val, val])
            else:
                clauses.append(col + '=?'); values.append(val)
    currency = args.get('currency')
    if currency:
        clauses.append('(t.receiving_currency=? OR t.payment_currency=?)'); values.extend([currency, currency])
    for key, col, op in [('start', 't.timestamp', '>='), ('end', 't.timestamp', '<=')]:
        val = args.get(key)
        if val:
            val=val.replace('T',' ')
            if key=='end' and len(val)==10: val+=' 23:59:59'
            clauses.append(col + op + '?'); values.append(val)
    if args.get('min_risk') not in (None, ''):
        if not scored: raise ValueError('Risk filters require persisted batch scores. Run the score command first.')
        clauses.append('s.risk_score>=?'); values.append(max(0.0, min(1.0, float(args['min_risk']))))
    if args.get('max_risk') not in (None, ''):
        if not scored: raise ValueError('Risk filters require persisted batch scores. Run the score command first.')
        clauses.append('s.risk_score<=?'); values.append(max(0.0, min(1.0, float(args['max_risk']))))
    where = (' WHERE ' + ' AND '.join(clauses)) if clauses else ''
    join = ' LEFT JOIN transaction_scores s ON s.transaction_id=t.transaction_id AND s.model_version=?' if scored else ''
    if scored: values.insert(0, version)
    return join, where, values


@ibm_bp.get('/dashboard')
def dashboard():
    return render_template('ibm_dashboard.html')


@ibm_bp.get('/health')
def ibm_health():
    db_ready = False
    if os.path.exists(DB):
        try:
            with connect() as c:
                db_ready = c.execute('SELECT 1 FROM transactions LIMIT 1').fetchone() is not None
        except sqlite3.Error: pass
    progress=None
    if db_ready:
        try: progress=score_progress()
        except sqlite3.Error: pass
    return jsonify(service='ok', database='ready' if db_ready else 'missing_or_unavailable',
                   model='ready' if model_version() else 'missing_or_unavailable',
                   scoring=progress.get('status') if progress else 'not_started',score_progress=progress), 200


@ibm_bp.get('/summary')
def summary():
    try:
        with connect() as c:
            n, pos, lo, hi = c.execute('SELECT COUNT(*),SUM(actual_label),MIN(timestamp),MAX(timestamp) FROM transactions').fetchone()
            imports = c.execute('SELECT dataset_version,imported_at,source_bytes,missing_count FROM dataset_imports LIMIT 1').fetchone()
            scored = c.execute('SELECT COUNT(*) FROM transaction_scores WHERE model_version=?', (model_version(),)).fetchone()[0] if table_exists(c, 'transaction_scores') and model_version() else 0
            flagged = c.execute('SELECT COUNT(*) FROM transaction_scores WHERE model_version=? AND predicted_class=1', (model_version(),)).fetchone()[0] if table_exists(c, 'transaction_scores') and model_version() else 0
            # The indexed DISTINCT/UNION query is expensive on the first call; retain the
            # actual result in a small metadata table for subsequent dashboard requests.
            c.execute('CREATE TABLE IF NOT EXISTS ibm_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            account_row = c.execute("SELECT value FROM ibm_metadata WHERE key='unique_accounts'").fetchone()
            if account_row:
                accounts = int(account_row[0])
            else:
                accounts = c.execute('SELECT COUNT(*) FROM (SELECT from_bank,from_account FROM transactions UNION SELECT to_bank,to_account FROM transactions)').fetchone()[0]
                c.execute("INSERT OR REPLACE INTO ibm_metadata VALUES ('unique_accounts',?)", (str(accounts),)); c.commit()
        metrics = json.loads(Path(METRICS).read_text(encoding='utf-8')) if Path(METRICS).exists() else {}
        return jsonify(dataset_version=imports['dataset_version'], imported_at=imports['imported_at'],
                       transactions=n, accounts=accounts, actual_laundering=pos or 0,
                       actual_non_laundering=n-(pos or 0), positive_prevalence=(pos or 0)/n if n else 0,
                       timestamp_range=[lo, hi], missing_cells=imports['missing_count'],
                       model_metrics=metrics, model_version=metrics.get('model_version'),
                       scored_transactions=scored, flagged_transactions=flagged,
                       scoring_progress=score_progress(c=None))
    except FileNotFoundError as e: return jsonify(error=str(e)), 404
    except (sqlite3.Error, OSError, ValueError) as e: return jsonify(error=str(e)), 503


def score_progress(c=None):
    own = c is None
    if own:
        try: c = _open_connection()
        except OSError: return None
    try:
        if not table_exists(c, 'score_progress'): return None
        row = c.execute('SELECT * FROM score_progress ORDER BY updated_at DESC LIMIT 1').fetchone()
        return dict(row) if row else None
    finally:
        if own: c.close()


@ibm_bp.get('/analytics')
def analytics():
    try:
        with connect() as c:
            activity = [dict(x) for x in c.execute("SELECT substr(timestamp,1,10) day,COUNT(*) transactions,SUM(actual_label) laundering FROM transactions GROUP BY day ORDER BY day")]
            formats = [dict(x) for x in c.execute('SELECT payment_format,COUNT(*) count FROM transactions GROUP BY payment_format ORDER BY count DESC LIMIT 12')]
            currencies = [dict(x) for x in c.execute('SELECT receiving_currency currency,COUNT(*) count,SUM(amount_received) received_total FROM transactions GROUP BY receiving_currency ORDER BY count DESC LIMIT 12')]
            risks = []
            version = model_version()
            if version and table_exists(c, 'transaction_scores'):
                risks = [dict(x) for x in c.execute('SELECT predicted_class,COUNT(*) count FROM transaction_scores WHERE model_version=? GROUP BY predicted_class', (version,))]
        return jsonify(activity=activity, payment_formats=formats, currencies=currencies, risk_distribution=risks)
    except FileNotFoundError as e: return jsonify(error=str(e)), 404
    except sqlite3.Error as e: return jsonify(error=str(e)), 503


@ibm_bp.get('/transactions')
def transactions():
    try:
        limit = min(max(request.args.get('limit', 25, type=int), 1), MAX_PAGE)
        offset = min(max(request.args.get('offset', 0, type=int), 0), 10_000_000)
        version = model_version()
        with connect() as c:
            scored = bool(version and table_exists(c, 'transaction_scores'))
            join, where, vals = _filters(request.args, scored, version)
            total = c.execute('SELECT COUNT(*) FROM transactions t'+join+where, vals).fetchone()[0]
            cols = ',s.risk_score,s.predicted_class,s.threshold,s.model_version,s.scored_at' if scored else ',NULL risk_score,NULL predicted_class,NULL threshold,NULL model_version,NULL scored_at'
            rows = c.execute('SELECT t.*'+cols+' FROM transactions t'+join+where+' ORDER BY t.timestamp,t.source_row LIMIT ? OFFSET ?', vals+[limit, offset]).fetchall()
        return jsonify(total=total, limit=limit, offset=offset, transactions=[dict(x) for x in rows], scores_ready=scored)
    except FileNotFoundError as e: return jsonify(error=str(e)), 404
    except (sqlite3.Error, ValueError) as e: return jsonify(error=str(e)), 400


@ibm_bp.get('/transactions/<transaction_id>')
def transaction_detail(transaction_id):
    try:
        with connect() as c:
            row = c.execute('SELECT * FROM transactions WHERE transaction_id=?', (transaction_id,)).fetchone()
            if not row: return jsonify(error='Transaction not found.'), 404
            result = dict(row)
            if table_exists(c, 'transaction_scores'):
                s = c.execute('SELECT risk_score,predicted_class,threshold,model_version,scored_at FROM transaction_scores WHERE transaction_id=? ORDER BY scored_at DESC LIMIT 1', (transaction_id,)).fetchone()
                result.update(dict(s) if s else {})
        return jsonify(transaction=result)
    except FileNotFoundError as e: return jsonify(error=str(e)), 404


@ibm_bp.get('/transactions/<transaction_id>/explanation')
def transaction_explanation(transaction_id):
    """Additive linear-model contributions in the actual hashed feature space."""
    try:
        with connect() as c:
            row = c.execute('SELECT * FROM transactions WHERE transaction_id=?', (transaction_id,)).fetchone()
            if not row: return jsonify(error='Transaction not found.'), 404
            tx = dict(row)
        from ibm_aml import explain_row
        explanation = explain_row(tx, MODEL)
        return jsonify(transaction_id=transaction_id, explanation=explanation,
                       caveat='These are additive model contributions, not causal explanations or evidence of wrongdoing.')
    except FileNotFoundError as e: return jsonify(error=str(e)), 404
    except (ValueError, OSError) as e: return jsonify(error=str(e)), 503


@ibm_bp.get('/graph')
def graph():
    account, bank = request.args.get('account'), request.args.get('bank')
    if not account or not bank: return jsonify(error='Provide account and bank.'), 400
    depth = min(max(request.args.get('depth', 1, type=int), 1), 2)
    limit = min(max(request.args.get('limit', 100, type=int), 1), MAX_GRAPH_EDGES)
    try:
        with connect() as c:
            frontier, visited, edges, seen = {(bank, account)}, set(), [], set()
            for _ in range(depth):
                nxt = set()
                for b, a in frontier:
                    rows = c.execute('''SELECT transaction_id,from_bank,from_account,to_bank,to_account,timestamp,
                        amount_received,receiving_currency,amount_paid,payment_currency,payment_format,actual_label
                        FROM transactions WHERE (from_bank=? AND from_account=?) OR (to_bank=? AND to_account=?)
                        ORDER BY timestamp LIMIT ?''', (b, a, b, a, limit)).fetchall()
                    for r in rows:
                        e = dict(r)
                        if e['transaction_id'] in seen: continue
                        seen.add(e['transaction_id']); edges.append(e)
                        src=(e['from_bank'],e['from_account']); dst=(e['to_bank'],e['to_account'])
                        nxt.add(dst if src==(b,a) else src)
                visited.update(frontier); frontier=nxt-visited
                if not frontier or len(edges)>=limit: break
            edges = edges[:limit]
        ids = {(x['from_bank'],x['from_account']) for x in edges} | {(x['to_bank'],x['to_account']) for x in edges}
        nodes = [{'id':f'{b}:{a}','bank':b,'account':a} for b,a in sorted(ids)]
        return jsonify(nodes=nodes,edges=edges,limit=limit,depth=depth)
    except FileNotFoundError as e: return jsonify(error=str(e)), 404
    except sqlite3.Error as e: return jsonify(error=str(e)), 503


@ibm_bp.get('/export/transactions.csv')
def export_transactions():
    try:
        limit=min(max(request.args.get('limit',10000,type=int),1),100000)
        version=model_version()
        with connect() as c:
            scored=bool(version and table_exists(c,'transaction_scores'))
            join,where,vals=_filters(request.args,scored,version)
            cols=',s.risk_score,s.predicted_class,s.threshold,s.model_version,s.scored_at' if scored else ''
            rows=[dict(x) for x in c.execute('SELECT t.*'+cols+' FROM transactions t'+join+where+' ORDER BY t.source_row LIMIT ?', vals+[limit]).fetchall()]
        fields=list(rows[0]) if rows else ['transaction_id','timestamp','from_bank','from_account','to_bank','to_account','amount_received','receiving_currency','amount_paid','payment_currency','payment_format','actual_label']
        stream=io.StringIO(); writer=csv.DictWriter(stream,fieldnames=fields); writer.writeheader(); writer.writerows(rows)
        return Response(stream.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename=ibm_hi_small_transactions.csv','X-Export-Row-Limit':str(limit)})
    except FileNotFoundError as e: return jsonify(error=str(e)), 404
    except (sqlite3.Error, ValueError) as e: return jsonify(error=str(e)), 400


@ibm_bp.get('/export/network.csv')
def export_network():
    # Export exactly the bounded subgraph requested; no client-generated edges.
    response=graph()
    if not isinstance(response, tuple): payload=response.get_json()
    else: return response
    stream=io.StringIO(); writer=csv.DictWriter(stream,fieldnames=['source_bank','source_account','destination_bank','destination_account','transaction_id','timestamp','amount_received','currency','actual_label']); writer.writeheader()
    for e in payload['edges']:
        writer.writerow({'source_bank':e['from_bank'],'source_account':e['from_account'],'destination_bank':e['to_bank'],'destination_account':e['to_account'],'transaction_id':e['transaction_id'],'timestamp':e['timestamp'],'amount_received':e['amount_received'],'currency':e['receiving_currency'],'actual_label':e['actual_label']})
    return Response(stream.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename=ibm_network_edges.csv'})


@ibm_bp.get('/export/accounts.csv')
def export_accounts():
    """Currency-separated account flows; incoming and outgoing amounts are never combined."""
    try:
        limit=min(max(request.args.get('limit',50000,type=int),1),100000)
        version=model_version()
        with connect() as c:
            scored=bool(version and table_exists(c,'transaction_scores'))
            score_join=' LEFT JOIN transaction_scores s ON s.transaction_id=t.transaction_id AND s.model_version=?' if scored else ''
            incoming_flag='COALESCE(SUM(CASE WHEN s.predicted_class=1 THEN 1 ELSE 0 END),0)' if scored else '0'
            outgoing_flag='COALESCE(SUM(CASE WHEN s.predicted_class=1 THEN 1 ELSE 0 END),0)' if scored else '0'
            params=([version] if scored else [])*2
            sql=f'''WITH flows AS (
              SELECT t.from_bank bank,t.from_account account,t.payment_currency currency,0 incoming_count,
                COUNT(*) outgoing_count,0 incoming_amount,SUM(t.amount_paid) outgoing_amount,
                0 incoming_flagged,{outgoing_flag} outgoing_flagged
              FROM transactions t{score_join} GROUP BY bank,account,currency
              UNION ALL
              SELECT t.to_bank,t.to_account,t.receiving_currency,COUNT(*),0,SUM(t.amount_received),0,
                {incoming_flag},0 FROM transactions t{score_join} GROUP BY t.to_bank,t.to_account,t.receiving_currency
            ) SELECT bank,account,currency,SUM(incoming_count) incoming_count,SUM(outgoing_count) outgoing_count,
              SUM(incoming_amount) incoming_amount,SUM(outgoing_amount) outgoing_amount,
              SUM(incoming_flagged) incoming_flagged,SUM(outgoing_flagged) outgoing_flagged
              FROM flows GROUP BY bank,account,currency ORDER BY bank,account,currency LIMIT ?'''
            rows=[dict(x) for x in c.execute(sql,params+[limit]).fetchall()]
        cols=['bank','account','currency','incoming_count','outgoing_count','incoming_amount','outgoing_amount','incoming_flagged','outgoing_flagged']
        stream=io.StringIO(); writer=csv.DictWriter(stream,fieldnames=cols); writer.writeheader(); writer.writerows(rows)
        return Response(stream.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename=ibm_account_activity.csv','X-Export-Row-Limit':str(limit)})
    except (sqlite3.Error,ValueError) as e: return jsonify(error=str(e)),400


@ibm_bp.get('/scoring/progress')
def scoring_status():
    try:
        with connect() as c: return jsonify(progress=score_progress(c),scores_ready=table_exists(c,'transaction_scores'))
    except FileNotFoundError as e: return jsonify(error=str(e)), 404


@ibm_bp.get('/assistant')
def assistant():
    """Deterministic, bounded answer functions; never executes user-supplied SQL."""
    question=(request.args.get('q') or '').strip()
    if not question: return jsonify(error='Enter a question.'),400
    q=question.casefold()
    try:
        if 'compare' in q and 'actual' in q and 'model' in q:
            with connect() as c:
                version=model_version()
                if not version or not table_exists(c,'transaction_scores'):
                    return jsonify(answer='Persisted model predictions are not available yet.',evidence=[])
                rows=[dict(x) for x in c.execute('''SELECT t.actual_label,s.predicted_class,COUNT(*) count
                  FROM transactions t JOIN transaction_scores s USING(transaction_id)
                  WHERE s.model_version=? GROUP BY t.actual_label,s.predicted_class ORDER BY t.actual_label,s.predicted_class''',(version,))]
            return jsonify(answer=f'Compared saved {version} predictions with the separate ground-truth label over {nfmt(sum(x["count"] for x in rows))} scored rows.',evidence=rows)
        if any(x in q for x in ('model','precision','recall','auc','performance','f1')) and not any(x in q for x in ('how many','count','flagged','highest')):
            m=json.loads(Path(METRICS).read_text(encoding='utf-8')) if Path(METRICS).exists() else None
            if not m: return jsonify(answer='The saved evaluation metrics are not available.',evidence=[])
            return jsonify(answer=f"Held-out metrics for {m['model_version']}: average precision {m['average_precision']:.4f}, ROC-AUC {m['roc_auc']:.4f}, precision {m['precision']:.4f}, recall {m['recall']:.4f}, F1 {m['f1']:.4f}. Predictions are investigation leads, not proof.",evidence=[{'type':'evaluation','test_rows':m['test_rows'],'split':m['split'],'confusion_matrix_tn_fp_fn_tp':m['confusion_matrix_tn_fp_fn_tp']}])
        txmatch=re.search(r'HI-Small-\d{10}',question,re.I)
        if txmatch:
            with connect() as c:
                row=c.execute('SELECT * FROM transactions WHERE transaction_id=?',(txmatch.group(0),)).fetchone()
                if not row: return jsonify(answer='No transaction with that ID exists in the imported HI-Small records.',evidence=[])
                tx=dict(row); score=c.execute('SELECT risk_score,predicted_class,threshold,model_version FROM transaction_scores WHERE transaction_id=? ORDER BY scored_at DESC LIMIT 1',(tx['transaction_id'],)).fetchone() if table_exists(c,'transaction_scores') else None
            if score: tx.update(dict(score))
            return jsonify(answer=f"Record {tx['transaction_id']} is ground-truth {'positive' if tx['actual_label'] else 'negative'} at {tx['timestamp']}. Model score: {tx.get('risk_score','not yet scored')}. A score is not a criminal finding.",evidence=[tx])
        if 'highest risk' in q or 'highest-risk' in q or ('flagged' in q and 'how many' not in q and 'count' not in q):
            with connect() as c:
                version=model_version()
                if not version or not table_exists(c,'transaction_scores'):
                    return jsonify(answer='Batch scores are not available yet. Run the score command after reviewing its preflight estimate.',evidence=[])
                rows=[dict(x) for x in c.execute('''SELECT t.transaction_id,t.timestamp,t.from_bank,t.from_account,t.to_bank,t.to_account,t.actual_label,s.risk_score,s.predicted_class,s.threshold,s.model_version FROM transaction_scores s JOIN transactions t USING(transaction_id) WHERE s.model_version=? ORDER BY s.risk_score DESC LIMIT 10''',(version,))]
            return jsonify(answer=f'Showing the 10 highest-scored transactions for {version}. These are model-ranked leads; actual labels are included separately.',evidence=rows)
        acct_hint=re.search(r'(?:account\s+)([A-Za-z0-9]+)',question,re.I)
        bank_hint=re.search(r'bank\s+([A-Za-z0-9]+)',question,re.I)
        if acct_hint and not bank_hint:
            return jsonify(answer='That account string may exist at more than one bank. Include both bank and account, for example “transactions connected to bank 010 account 8000EBD30”.',evidence=[])
        if 'how many' in q or 'count' in q:
            dates=re.findall(r'20\d{2}-\d{2}-\d{2}',question)
            predicted=('flag' in q or 'model' in q)
            actual_positive=('laundering' in q or 'positive' in q) and not predicted
            with connect() as c:
                if predicted:
                    if not table_exists(c,'transaction_scores') or not model_version():
                        return jsonify(answer='Persisted model scores are not available yet.',evidence=[])
                    sql='SELECT COUNT(*) FROM transaction_scores s JOIN transactions t USING(transaction_id) WHERE s.model_version=? AND s.predicted_class=1'; values=[model_version()]
                else:
                    sql='SELECT COUNT(*) FROM transactions WHERE '+('actual_label=1' if actual_positive else '1=1'); values=[]
                if len(dates)>=1:
                    sql+=(' AND t.timestamp>=?' if 'model' in q or 'flag' in q else ' AND timestamp>=?'); values.append(dates[0]+' 00:00:00')
                if len(dates)>=2:
                    sql+=(' AND t.timestamp<=?' if 'model' in q or 'flag' in q else ' AND timestamp<=?'); values.append(dates[1]+' 23:59:59')
                count=c.execute(sql,values).fetchone()[0]
            measure='model-flagged' if predicted else 'ground-truth positive' if actual_positive else 'all transactions'
            return jsonify(answer=f'{nfmt(count)} {measure} transactions match the requested count. Date bounds were applied when YYYY-MM-DD dates were provided.',evidence=[{'count':count,'date_range':dates[:2],'measure':measure}])
        acct=re.search(r'(?:account\s+)([A-Za-z0-9]+)',question,re.I)
        bank=re.search(r'bank\s+([A-Za-z0-9]+)',question,re.I)
        if acct and not bank:
            return jsonify(answer='That account string may exist at more than one bank. Include both bank and account, for example “transactions connected to bank 010 account 8000EBD30”.',evidence=[])
        if acct and bank:
            with connect() as c:
                rows=[dict(x) for x in c.execute('''SELECT transaction_id,timestamp,from_bank,from_account,to_bank,to_account,amount_received,receiving_currency,actual_label FROM transactions WHERE (from_bank=? AND from_account=?) OR (to_bank=? AND to_account=?) ORDER BY timestamp DESC LIMIT 10''',(bank.group(1),acct.group(1),bank.group(1),acct.group(1))).fetchall()]
            return jsonify(answer=f'Found {len(rows)} recent connection records in the evidence preview for bank {bank.group(1)}, account {acct.group(1)}. The preview is capped at 10 rows.',evidence=rows)
        return jsonify(answer='I can look up a HI-Small transaction ID, retrieve the highest model scores, count transactions (optionally with YYYY-MM-DD bounds), inspect an account when you provide both bank and account, or report saved model metrics.',evidence=[])
    except (sqlite3.Error, OSError, ValueError, KeyError) as e:
        return jsonify(error=str(e)),503


def nfmt(value):
    return f'{int(value):,}'
